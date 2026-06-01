import gzip
import os
import re
import uuid
import io
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.models import (
    Project,
    Sample,
    SampleFile,
    Metadata,
    SRADownload,
    BVBRCFetch,
    PairType,
    SequencingPlatform,
    FileSource,
    SRADownloadStatus,
    InputType,
    SampleStatus,
    AnalysisJob,
    JobStatus,
)
import shutil

from app.schemas.schemas import (
    FileManagerResponse,
    FileManagerSample,
    FileSlot,
    ServerPathRequest,
    SRARequest,
    SRADownloadRead,
    BVBRCRequest,
    BVBRCFetchRead,
    MetadataTSVResult,
)
from app.celery_app import celery_app

router = APIRouter(tags=["file-manager"])


def _build_file_slot(sf: SampleFile) -> FileSlot:
    filename = os.path.basename(sf.file_path) if sf.file_path else sf.original_filename
    return FileSlot(
        id=sf.id,
        filename=filename,
        size=sf.file_size,
    )


def _build_sample_entry(sample: Sample, db: Session, project_name: str | None = None) -> FileManagerSample:
    files = sample.files or []
    illumina_r1: Optional[FileSlot] = None
    illumina_r2: Optional[FileSlot] = None
    long_read: Optional[FileSlot] = None
    long_read_platform: Optional[str] = None
    assembly: Optional[FileSlot] = None
    source = "upload"

    for sf in files:
        if sf.pair == PairType.R1:
            illumina_r1 = _build_file_slot(sf)
        elif sf.pair == PairType.R2:
            illumina_r2 = _build_file_slot(sf)
        elif sf.pair == PairType.long_read:
            long_read = _build_file_slot(sf)
            if sf.platform:
                long_read_platform = sf.platform.value
        elif sf.pair == PairType.assembly:
            assembly = _build_file_slot(sf)
        if sf.source:
            source = sf.source.value

    has_metadata = sample.metadata_record is not None

    # Pipeline status from latest preprocessing/pipeline job
    pipeline_status = "not_started"
    pipeline_job_id = None
    pipeline_progress = 0
    latest_job = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.sample_id == sample.id,
            AnalysisJob.tool.in_(["preprocessing", "pipeline"]),
        )
        .order_by(AnalysisJob.started_at.desc().nullslast())
        .first()
    )
    if latest_job:
        pipeline_job_id = str(latest_job.id)
        if latest_job.status == JobStatus.complete:
            pipeline_status = "complete"
            pipeline_progress = 100
        elif latest_job.status in (JobStatus.running, JobStatus.pending):
            pipeline_status = "running"
            pipeline_progress = _estimate_progress(latest_job.log or "")
        elif latest_job.status == JobStatus.failed:
            pipeline_status = "failed"
            pipeline_progress = _estimate_progress(latest_job.log or "")

    # BUSCO completeness (if pipeline completed)
    busco_complete = None
    if pipeline_status == "complete":
        import re
        busco_dir = os.path.join(settings.RESULTS_DIR, str(sample.id), "assembly", "busco", "busco_result")
        if os.path.isdir(busco_dir):
            for root, dirs, files in os.walk(busco_dir):
                for fname in files:
                    if fname.startswith("short_summary"):
                        with open(os.path.join(root, fname)) as bf:
                            m = re.search(r"C:([\d.]+)%", bf.read())
                            if m:
                                busco_complete = float(m.group(1))
                        break
                if busco_complete is not None:
                    break

    return FileManagerSample(
        sample_id=sample.id,
        name=sample.name,
        status=sample.status.value if sample.status else "pending",
        input_type=sample.input_type.value if sample.input_type else "fastq",
        illumina_r1=illumina_r1,
        illumina_r2=illumina_r2,
        long_read=long_read,
        long_read_platform=long_read_platform,
        assembly=assembly,
        source=source,
        has_metadata=has_metadata,
        project_id=sample.project_id,
        project_name=project_name,
        pipeline_status=pipeline_status,
        pipeline_job_id=pipeline_job_id,
        pipeline_progress=pipeline_progress,
        busco_complete=busco_complete,
    )


def _estimate_progress(log: str) -> int:
    """Estimate pipeline progress (0-100) from job log text."""
    # Map log markers to progress percentages (ordered by pipeline stage)
    markers = [
        ("Pipeline started", 2),
        ("Phase 1", 3),
        ("fastp", 5),
        ("Filtlong", 8),
        ("Genome assembly", 10),
        ("Assembly complete", 30),
        ("Assembly — skipped", 30),
        ("QUAST", 33),
        ("BUSCO", 36),
        ("Phase 2", 38),
        ("Species", 40),
        ("MLST", 43),
        ("Serotyping", 45),
        ("AMRFinderPlus", 50),
        ("MOB-recon", 55),
        ("MobileElementFinder", 58),
        ("IntegronFinder", 62),
        ("geNomad", 65),
        ("PointFinder", 68),
        ("cgMLST", 72),
        ("CRISPR", 75),
        ("DefenseFinder", 78),
        ("ICEfinder", 82),
        ("Context annotations", 85),
        ("ML phenotype", 90),
        ("Phenotype prediction", 93),
        ("Risk scoring", 96),
        ("completed successfully", 100),
    ]
    progress = 0
    for marker, pct in markers:
        if marker in log:
            progress = max(progress, pct)
    return progress


def _strip_extensions(filename: str) -> str:
    """Remove known sequencing file extensions."""
    base = filename
    for ext in [".fastq.gz", ".fq.gz", ".fastq", ".fq", ".fasta", ".fa", ".fna"]:
        if base.lower().endswith(ext):
            return base[: len(base) - len(ext)]
    return base


def _parse_filename(filename: str) -> Tuple[str, PairType, Optional[SequencingPlatform]]:
    """Parse sample name and pair type from filename.

    Rules:
      SAMPLE_R1.fastq.gz / SAMPLE_1.fastq.gz -> Illumina R1
      SAMPLE_R2.fastq.gz / SAMPLE_2.fastq.gz -> Illumina R2
      SAMPLE_ONT.fastq.gz                    -> long read, ONT
      SAMPLE_PB.fastq.gz                     -> long read, PacBio
      SAMPLE.fastq.gz                        -> long read (platform detected from content)
      SAMPLE.fasta/.fa/.fna                  -> pre-assembled FASTA
    """
    # Check for FASTA files first
    lower = filename.lower()
    if lower.endswith((".fasta", ".fa", ".fna", ".fasta.gz", ".fa.gz", ".fna.gz")):
        base = _strip_extensions(filename)
        return base, PairType.assembly, None

    base = _strip_extensions(filename)

    # Illumina paired-end: _R1/_R2 or _1/_2
    m = re.match(r"^(.+?)_R1$", base, re.IGNORECASE)
    if m:
        return m.group(1), PairType.R1, SequencingPlatform.illumina
    m = re.match(r"^(.+?)_R2$", base, re.IGNORECASE)
    if m:
        return m.group(1), PairType.R2, SequencingPlatform.illumina
    m = re.match(r"^(.+?)_1$", base)
    if m:
        return m.group(1), PairType.R1, SequencingPlatform.illumina
    m = re.match(r"^(.+?)_2$", base)
    if m:
        return m.group(1), PairType.R2, SequencingPlatform.illumina

    # Explicit long-read platform tags
    m = re.match(r"^(.+?)_ONT$", base, re.IGNORECASE)
    if m:
        return m.group(1), PairType.long_read, SequencingPlatform.ont
    m = re.match(r"^(.+?)_PB$", base, re.IGNORECASE)
    if m:
        return m.group(1), PairType.long_read, SequencingPlatform.pacbio

    # No suffix -> long read (platform auto-detected from FASTQ headers)
    return base, PairType.long_read, None


def _detect_platform_from_fastq(file_path: str) -> Tuple[Optional[SequencingPlatform], Optional[PairType]]:
    """Auto-detect sequencing platform and read number from FASTQ headers.

    Reads the first few records to determine:
    - Illumina: headers like @INSTRUMENT:RUN:FLOWCELL:LANE:TILE:X:Y 1:N:0:INDEX
    - ONT: headers containing 'runid=' or channel/read info
    - PacBio: headers like @m64011_... or containing /ccs or zmw patterns

    Also detects R1 vs R2 for Illumina from the header.
    """
    try:
        is_gz = file_path.endswith(".gz")
        opener = gzip.open if is_gz else open
        mode = "rt" if is_gz else "r"

        headers = []
        read_lengths = []
        with opener(file_path, mode) as fh:
            line_num = 0
            for line in fh:
                line = line.strip()
                if line_num % 4 == 0 and line.startswith("@"):
                    headers.append(line)
                elif line_num % 4 == 1:
                    read_lengths.append(len(line))
                line_num += 1
                # Sample first 20 reads
                if len(headers) >= 20:
                    break

        if not headers:
            return None, None

        # --- Check for Illumina ---
        # Modern Illumina: @INSTRUMENT:RUN:FLOWCELLID:LANE:TILE:X:Y READNUM:FILTERED:0:INDEX
        # Old Illumina: @INSTRUMENT:LANE:TILE:X:Y#INDEX/READNUM
        illumina_modern = re.compile(
            r"^@[\w-]+:\d+:[\w-]+:\d+:\d+:\d+:\d+\s+([12]):[YN]:\d+:"
        )
        illumina_old = re.compile(
            r"^@[\w-]+:\d+:\d+:\d+:\d+#[\w-]+/([12])"
        )

        illumina_count = 0
        read_num = None
        for h in headers:
            m = illumina_modern.match(h)
            if m:
                illumina_count += 1
                read_num = m.group(1)
                continue
            m = illumina_old.match(h)
            if m:
                illumina_count += 1
                read_num = m.group(1)

        if illumina_count > len(headers) * 0.5:
            pair = PairType.R1 if read_num == "1" else PairType.R2
            return SequencingPlatform.illumina, pair

        # --- Check for ONT ---
        # ONT headers typically contain 'runid=' or have UUID-style read IDs
        ont_pattern = re.compile(r"runid=|ch=\d+|start_time=|basecall_model")
        ont_uuid = re.compile(r"^@[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        ont_count = sum(
            1 for h in headers
            if ont_pattern.search(h) or ont_uuid.match(h)
        )
        if ont_count > len(headers) * 0.5:
            return SequencingPlatform.ont, PairType.long_read

        # --- Check for PacBio ---
        # PacBio CCS: @m64011_190830_220126/12345/ccs
        # PacBio CLR: @m64011_190830_220126/12345/0_1234
        pacbio_pattern = re.compile(r"^@m\d+[_e]\d+")
        pacbio_count = sum(1 for h in headers if pacbio_pattern.match(h))
        if pacbio_count > len(headers) * 0.5:
            return SequencingPlatform.pacbio, PairType.long_read

        # --- Fallback: use read length heuristic ---
        if read_lengths:
            avg_len = sum(read_lengths) / len(read_lengths)
            if avg_len <= 600:
                return SequencingPlatform.illumina, None
            else:
                return SequencingPlatform.ont, PairType.long_read

        return None, None

    except Exception:
        return None, None


# ── GET global file manager view ────────────────────────────────────────────

def _get_or_create_default_project(db: Session) -> Project:
    """Get or create a default project for global uploads."""
    project = db.query(Project).filter(Project.name == "Default").first()
    if not project:
        project = Project(name="Default", description="Auto-created default project")
        db.add(project)
        db.flush()
    return project


@router.get("/file-manager/all", response_model=FileManagerResponse)
def get_all_file_manager(db: Session = Depends(get_db)):
    """Return all samples across all projects with project name."""
    samples = (
        db.query(Sample)
        .join(Project, Sample.project_id == Project.id)
        .order_by(Project.name, Sample.created_at)
        .all()
    )
    # Build a project name lookup
    project_ids = {s.project_id for s in samples}
    projects = db.query(Project).filter(Project.id.in_(project_ids)).all()
    project_names = {p.id: p.name for p in projects}

    entries = [
        _build_sample_entry(s, db, project_name=project_names.get(s.project_id))
        for s in samples
    ]
    return FileManagerResponse(samples=entries, total=len(entries))


@router.post("/file-manager/upload", response_model=FileManagerResponse)
async def global_upload_files(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Upload files globally (auto-creates default project).

    Supports FASTQ (paired-end, long-read) and FASTA (pre-assembled) files.
    FASTA files (.fasta, .fa, .fna) are treated as assemblies and skip QC/assembly in the pipeline.
    """
    project = _get_or_create_default_project(db)
    project_id = project.id
    created_samples = {}

    for upload_file in files:
        if not upload_file.filename:
            continue

        sample_name, pair_from_name, platform_from_name = _parse_filename(upload_file.filename)
        is_fasta = pair_from_name == PairType.assembly

        if sample_name in created_samples:
            sample = created_samples[sample_name]
            if is_fasta and sample.input_type != InputType.fasta:
                sample.input_type = InputType.fasta
        else:
            sample = (
                db.query(Sample)
                .filter(Sample.project_id == project_id, Sample.name == sample_name)
                .first()
            )
            if not sample:
                sample = Sample(
                    project_id=project_id,
                    name=sample_name,
                    input_type=InputType.fasta if is_fasta else InputType.fastq,
                    status=SampleStatus.pending,
                )
                db.add(sample)
                db.flush()
            elif is_fasta:
                sample.input_type = InputType.fasta
            created_samples[sample_name] = sample

        upload_dir = os.path.join(settings.UPLOAD_DIR, str(sample.id))
        os.makedirs(upload_dir, exist_ok=True)
        dest_path = os.path.join(upload_dir, upload_file.filename)

        content = await upload_file.read()
        with open(dest_path, "wb") as f:
            f.write(content)

        file_size = len(content)

        pair = pair_from_name
        platform = platform_from_name
        if pair == PairType.long_read and platform is None:
            is_fastq = upload_file.filename.lower().endswith(
                (".fastq.gz", ".fq.gz", ".fastq", ".fq")
            )
            if is_fastq:
                detected_platform, _ = _detect_platform_from_fastq(dest_path)
                if detected_platform:
                    platform = detected_platform

        ext = os.path.splitext(upload_file.filename)[1]
        if upload_file.filename.endswith(".gz"):
            ext = os.path.splitext(upload_file.filename[:-3])[1] + ".gz"

        sf = SampleFile(
            sample_id=sample.id,
            file_path=dest_path,
            file_type=ext,
            pair=pair,
            platform=platform,
            source=FileSource.upload,
            original_filename=upload_file.filename,
            file_size=file_size,
        )
        db.add(sf)

    db.commit()

    # Return all samples
    all_samples = db.query(Sample).order_by(Sample.created_at).all()
    project_ids = {s.project_id for s in all_samples}
    projects = db.query(Project).filter(Project.id.in_(project_ids)).all()
    project_names = {p.id: p.name for p in projects}
    entries = [_build_sample_entry(s, db, project_name=project_names.get(s.project_id)) for s in all_samples]
    return FileManagerResponse(samples=entries, total=len(entries))


@router.post("/file-manager/server-paths", response_model=FileManagerResponse)
def global_register_server_paths(
    body: ServerPathRequest,
    db: Session = Depends(get_db),
):
    """Register files from server paths (auto-creates default project)."""
    project = _get_or_create_default_project(db)

    expanded_paths = []
    for p in body.paths:
        p = p.strip()
        if not p:
            continue
        if os.path.isdir(p):
            for fname in sorted(os.listdir(p)):
                fpath = os.path.join(p, fname)
                if os.path.isfile(fpath) and not fname.startswith("."):
                    expanded_paths.append(fpath)
        else:
            expanded_paths.append(p)

    created_samples = {}

    for src_path in expanded_paths:
        if not os.path.isfile(src_path):
            continue

        filename = os.path.basename(src_path)
        sample_name, pair_from_name, platform_from_name = _parse_filename(filename)
        is_fasta = pair_from_name == PairType.assembly

        if sample_name in created_samples:
            sample = created_samples[sample_name]
            if is_fasta and sample.input_type != InputType.fasta:
                sample.input_type = InputType.fasta
        else:
            sample = (
                db.query(Sample)
                .filter(Sample.project_id == project.id, Sample.name == sample_name)
                .first()
            )
            if not sample:
                sample = Sample(
                    project_id=project.id,
                    name=sample_name,
                    input_type=InputType.fasta if is_fasta else InputType.fastq,
                    status=SampleStatus.pending,
                )
                db.add(sample)
                db.flush()
            elif is_fasta:
                sample.input_type = InputType.fasta
            created_samples[sample_name] = sample

        upload_dir = os.path.join(settings.UPLOAD_DIR, str(sample.id))
        os.makedirs(upload_dir, exist_ok=True)
        dest_path = os.path.join(upload_dir, filename)

        if os.path.exists(dest_path):
            os.remove(dest_path)
        try:
            os.link(src_path, dest_path)
        except OSError:
            shutil.copy2(src_path, dest_path)

        file_size = os.path.getsize(dest_path)

        pair = pair_from_name
        platform = platform_from_name
        if pair == PairType.long_read and platform is None:
            is_fastq = filename.lower().endswith(
                (".fastq.gz", ".fq.gz", ".fastq", ".fq")
            )
            if is_fastq:
                detected_platform, _ = _detect_platform_from_fastq(dest_path)
                if detected_platform:
                    platform = detected_platform

        ext = os.path.splitext(filename)[1]
        if filename.endswith(".gz"):
            ext = os.path.splitext(filename[:-3])[1] + ".gz"

        sf = SampleFile(
            sample_id=sample.id,
            file_path=dest_path,
            file_type=ext,
            pair=pair,
            platform=platform,
            source=FileSource.upload,
            original_filename=filename,
            file_size=file_size,
        )
        db.add(sf)

    db.commit()

    all_samples = db.query(Sample).order_by(Sample.created_at).all()
    project_ids = {s.project_id for s in all_samples}
    projects = db.query(Project).filter(Project.id.in_(project_ids)).all()
    project_names = {p.id: p.name for p in projects}
    entries = [_build_sample_entry(s, db, project_name=project_names.get(s.project_id)) for s in all_samples]
    return FileManagerResponse(samples=entries, total=len(entries))


@router.post("/file-manager/sra", response_model=List[SRADownloadRead])
def global_start_sra_downloads(
    body: SRARequest,
    db: Session = Depends(get_db),
):
    """Submit SRA accessions for download (auto-creates default project)."""
    project = _get_or_create_default_project(db)
    results = []
    for accession in body.accessions:
        accession = accession.strip()
        if not accession:
            continue

        sample = Sample(
            project_id=project.id,
            name=accession,
            input_type=InputType.fastq,
            status=SampleStatus.pending,
        )
        db.add(sample)
        db.flush()

        dl = SRADownload(
            project_id=project.id,
            sample_id=sample.id,
            srr_accession=accession,
            status=SRADownloadStatus.queued,
        )
        db.add(dl)
        db.flush()

        results.append(dl)
        result = celery_app.send_task("app.core.sra.download_sra", args=[str(dl.id)])
        dl.celery_task_id = result.id

    db.commit()
    for dl in results:
        db.refresh(dl)

    return [SRADownloadRead.model_validate(dl) for dl in results]


@router.get("/file-manager/sra", response_model=List[SRADownloadRead])
def global_list_sra_downloads(db: Session = Depends(get_db)):
    """List all SRA download jobs."""
    downloads = (
        db.query(SRADownload)
        .order_by(SRADownload.created_at.desc())
        .all()
    )
    return [SRADownloadRead.model_validate(dl) for dl in downloads]


@router.delete("/file-manager/sra/{download_id}")
def cancel_sra_download(download_id: uuid.UUID, db: Session = Depends(get_db)):
    """Cancel an SRA download."""
    dl = db.query(SRADownload).filter(SRADownload.id == download_id).first()
    if not dl:
        raise HTTPException(status_code=404, detail="SRA download not found")

    if dl.status in (SRADownloadStatus.complete, SRADownloadStatus.failed):
        raise HTTPException(status_code=400, detail="Download already finished")

    # Revoke the Celery task
    if dl.celery_task_id:
        try:
            from app.celery_app import celery_app as app
            app.control.revoke(dl.celery_task_id, terminate=True, signal="SIGTERM")
        except Exception:
            pass

    dl.status = SRADownloadStatus.failed
    dl.error_message = "Cancelled by user"
    dl.finished_at = datetime.utcnow()
    db.commit()

    return {"detail": "Download cancelled"}


# ── GET file manager view ───────────────────────────────────────────────────

@router.get("/projects/{project_id}/file-manager", response_model=FileManagerResponse)
def get_file_manager(project_id: uuid.UUID, db: Session = Depends(get_db)):
    samples = (
        db.query(Sample)
        .filter(Sample.project_id == project_id)
        .order_by(Sample.created_at)
        .all()
    )
    entries = [_build_sample_entry(s, db) for s in samples]
    return FileManagerResponse(samples=entries, total=len(entries))


# ── Upload files ────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/file-manager/upload", response_model=FileManagerResponse)
async def upload_files(
    project_id: uuid.UUID,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    created_samples = {}  # name -> Sample

    for upload_file in files:
        if not upload_file.filename:
            continue

        sample_name, pair_from_name, platform_from_name = _parse_filename(upload_file.filename)

        # Find or create sample
        if sample_name in created_samples:
            sample = created_samples[sample_name]
        else:
            sample = (
                db.query(Sample)
                .filter(Sample.project_id == project_id, Sample.name == sample_name)
                .first()
            )
            if not sample:
                sample = Sample(
                    project_id=project_id,
                    name=sample_name,
                    input_type=InputType.fastq,
                    status=SampleStatus.pending,
                )
                db.add(sample)
                db.flush()
            created_samples[sample_name] = sample

        # Save file
        upload_dir = os.path.join(settings.UPLOAD_DIR, str(sample.id))
        os.makedirs(upload_dir, exist_ok=True)
        dest_path = os.path.join(upload_dir, upload_file.filename)

        content = await upload_file.read()
        with open(dest_path, "wb") as f:
            f.write(content)

        file_size = len(content)

        # For long reads, auto-detect ONT vs PacBio from FASTQ headers
        pair = pair_from_name
        platform = platform_from_name
        if pair == PairType.long_read and platform is None:
            is_fastq = upload_file.filename.lower().endswith(
                (".fastq.gz", ".fq.gz", ".fastq", ".fq")
            )
            if is_fastq:
                detected_platform, _ = _detect_platform_from_fastq(dest_path)
                if detected_platform:
                    platform = detected_platform

        # Determine file_type extension
        ext = os.path.splitext(upload_file.filename)[1]
        if upload_file.filename.endswith(".gz"):
            ext = os.path.splitext(upload_file.filename[:-3])[1] + ".gz"

        sf = SampleFile(
            sample_id=sample.id,
            file_path=dest_path,
            file_type=ext,
            pair=pair,
            platform=platform,
            source=FileSource.upload,
            original_filename=upload_file.filename,
            file_size=file_size,
        )
        db.add(sf)

    db.commit()

    # Return updated file manager view
    samples = (
        db.query(Sample)
        .filter(Sample.project_id == project_id)
        .order_by(Sample.created_at)
        .all()
    )
    entries = [_build_sample_entry(s, db) for s in samples]
    return FileManagerResponse(samples=entries, total=len(entries))


# ── Browse server filesystem ───────────────────────────────────────────────

@router.get("/file-browser")
def browse_files(path: str = os.path.expanduser("~")):
    """List files and directories at the given server path."""
    resolved = os.path.abspath(path)
    if not os.path.isdir(resolved):
        raise HTTPException(status_code=400, detail="Not a directory")

    entries = []
    try:
        for entry in sorted(os.scandir(resolved), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith("."):
                continue
            try:
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "path": entry.path,
                    "is_dir": entry.is_dir(),
                    "size": stat.st_size if not entry.is_dir() else None,
                })
            except PermissionError:
                continue
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    parent = os.path.dirname(resolved) if resolved != "/" else None

    return {
        "current": resolved,
        "parent": parent,
        "entries": entries,
    }


# ── Register files from server path ────────────────────────────────────────

@router.post("/projects/{project_id}/file-manager/server-paths", response_model=FileManagerResponse)
def register_server_paths(
    project_id: uuid.UUID,
    body: ServerPathRequest,
    db: Session = Depends(get_db),
):
    # Expand directories to individual files
    expanded_paths = []
    for p in body.paths:
        p = p.strip()
        if not p:
            continue
        if os.path.isdir(p):
            for fname in sorted(os.listdir(p)):
                fpath = os.path.join(p, fname)
                if os.path.isfile(fpath) and not fname.startswith("."):
                    expanded_paths.append(fpath)
        else:
            expanded_paths.append(p)

    errors = []
    created_samples = {}

    for src_path in expanded_paths:
        if not os.path.isfile(src_path):
            errors.append(f"File not found: {src_path}")
            continue

        filename = os.path.basename(src_path)
        sample_name, pair_from_name, platform_from_name = _parse_filename(filename)

        # Find or create sample
        if sample_name in created_samples:
            sample = created_samples[sample_name]
        else:
            sample = (
                db.query(Sample)
                .filter(Sample.project_id == project_id, Sample.name == sample_name)
                .first()
            )
            if not sample:
                sample = Sample(
                    project_id=project_id,
                    name=sample_name,
                    input_type=InputType.fastq,
                    status=SampleStatus.pending,
                )
                db.add(sample)
                db.flush()
            created_samples[sample_name] = sample

        # Link or copy file to upload directory
        upload_dir = os.path.join(settings.UPLOAD_DIR, str(sample.id))
        os.makedirs(upload_dir, exist_ok=True)
        dest_path = os.path.join(upload_dir, filename)

        if os.path.exists(dest_path):
            os.remove(dest_path)
        try:
            # Hard link: instant, survives deletion of original
            os.link(src_path, dest_path)
        except OSError:
            # Cross-filesystem: fall back to copy
            shutil.copy2(src_path, dest_path)

        file_size = os.path.getsize(dest_path)

        # Auto-detect platform for long reads
        pair = pair_from_name
        platform = platform_from_name
        if pair == PairType.long_read and platform is None:
            is_fastq = filename.lower().endswith(
                (".fastq.gz", ".fq.gz", ".fastq", ".fq")
            )
            if is_fastq:
                detected_platform, _ = _detect_platform_from_fastq(dest_path)
                if detected_platform:
                    platform = detected_platform

        # Determine file_type extension
        ext = os.path.splitext(filename)[1]
        if filename.endswith(".gz"):
            ext = os.path.splitext(filename[:-3])[1] + ".gz"

        sf = SampleFile(
            sample_id=sample.id,
            file_path=dest_path,
            file_type=ext,
            pair=pair,
            platform=platform,
            source=FileSource.upload,
            original_filename=filename,
            file_size=file_size,
        )
        db.add(sf)

    db.commit()

    # Return updated file manager view
    samples = (
        db.query(Sample)
        .filter(Sample.project_id == project_id)
        .order_by(Sample.created_at)
        .all()
    )
    entries = [_build_sample_entry(s, db) for s in samples]
    return FileManagerResponse(samples=entries, total=len(entries))


# ── Metadata TSV upload ─────────────────────────────────────────────────────

@router.post("/projects/{project_id}/file-manager/metadata", response_model=MetadataTSVResult)
async def upload_metadata(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content), sep="\t")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse TSV: {e}")

    if "sample_id" not in df.columns:
        raise HTTPException(status_code=400, detail="TSV must contain a 'sample_id' column")

    known_columns = {"species", "source", "collection_date", "location"}
    updated = 0
    created = 0
    errors: List[str] = []

    for _, row in df.iterrows():
        sample_name = str(row["sample_id"]).strip()
        sample = (
            db.query(Sample)
            .filter(Sample.project_id == project_id, Sample.name == sample_name)
            .first()
        )
        if not sample:
            errors.append(f"Sample '{sample_name}' not found")
            continue

        # Build metadata fields
        meta_fields = {}
        custom = {}
        for col in df.columns:
            if col == "sample_id":
                continue
            val = row[col]
            if pd.isna(val):
                continue
            if col in known_columns:
                meta_fields[col] = val
            else:
                custom[col] = val

        # Find or create metadata record
        meta = (
            db.query(Metadata)
            .filter(Metadata.sample_id == sample.id)
            .first()
        )
        if meta:
            for k, v in meta_fields.items():
                setattr(meta, k, v)
            if custom:
                existing_custom = meta.custom_json or {}
                existing_custom.update(custom)
                meta.custom_json = existing_custom
            updated += 1
        else:
            meta = Metadata(
                sample_id=sample.id,
                **meta_fields,
                custom_json=custom if custom else None,
            )
            db.add(meta)
            created += 1

    db.commit()
    return MetadataTSVResult(updated=updated, created=created, errors=errors)


# ── SRA download ────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/file-manager/sra", response_model=List[SRADownloadRead])
def start_sra_downloads(
    project_id: uuid.UUID,
    body: SRARequest,
    db: Session = Depends(get_db),
):
    results = []
    for accession in body.accessions:
        accession = accession.strip()
        if not accession:
            continue

        # Create sample
        sample = Sample(
            project_id=project_id,
            name=accession,
            input_type=InputType.fastq,
            status=SampleStatus.pending,
        )
        db.add(sample)
        db.flush()

        # Create download record
        dl = SRADownload(
            project_id=project_id,
            sample_id=sample.id,
            srr_accession=accession,
            status=SRADownloadStatus.queued,
        )
        db.add(dl)
        db.flush()

        results.append(dl)

        # Dispatch Celery task
        result = celery_app.send_task("app.core.sra.download_sra", args=[str(dl.id)])
        dl.celery_task_id = result.id

    db.commit()
    for dl in results:
        db.refresh(dl)

    return [SRADownloadRead.model_validate(dl) for dl in results]


@router.get("/projects/{project_id}/file-manager/sra", response_model=List[SRADownloadRead])
def list_sra_downloads(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    downloads = (
        db.query(SRADownload)
        .filter(SRADownload.project_id == project_id)
        .order_by(SRADownload.created_at)
        .all()
    )
    return [SRADownloadRead.model_validate(dl) for dl in downloads]


# ── BV-BRC fetch ────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/file-manager/bvbrc", response_model=List[BVBRCFetchRead])
def start_bvbrc_fetches(
    project_id: uuid.UUID,
    body: BVBRCRequest,
    db: Session = Depends(get_db),
):
    results = []
    for genome_id in body.genome_ids:
        genome_id = genome_id.strip()
        if not genome_id:
            continue

        # Create sample
        sample = Sample(
            project_id=project_id,
            name=genome_id,
            input_type=InputType.fasta,
            status=SampleStatus.pending,
        )
        db.add(sample)
        db.flush()

        # Create fetch record
        fetch = BVBRCFetch(
            project_id=project_id,
            sample_id=sample.id,
            genome_id=genome_id,
            status=SRADownloadStatus.queued,
        )
        db.add(fetch)
        db.flush()

        results.append(fetch)

        # Dispatch Celery task
        celery_app.send_task("app.core.bvbrc.fetch_bvbrc", args=[str(fetch.id)])

    db.commit()
    for fetch in results:
        db.refresh(fetch)

    return [BVBRCFetchRead.model_validate(f) for f in results]


@router.get("/projects/{project_id}/file-manager/bvbrc", response_model=List[BVBRCFetchRead])
def list_bvbrc_fetches(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    fetches = (
        db.query(BVBRCFetch)
        .filter(BVBRCFetch.project_id == project_id)
        .order_by(BVBRCFetch.created_at)
        .all()
    )
    return [BVBRCFetchRead.model_validate(f) for f in fetches]


# ── Delete file ─────────────────────────────────────────────────────────────

@router.delete("/projects/{project_id}/file-manager/files/{file_id}")
def delete_file(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    sf = db.query(SampleFile).filter(SampleFile.id == file_id).first()
    if not sf:
        raise HTTPException(status_code=404, detail="File not found")

    # Verify the file belongs to a sample in this project
    sample = db.query(Sample).filter(Sample.id == sf.sample_id).first()
    if not sample or sample.project_id != project_id:
        raise HTTPException(status_code=404, detail="File not found in this project")

    # Delete physical file
    if sf.file_path and os.path.exists(sf.file_path):
        os.remove(sf.file_path)

    db.delete(sf)
    db.commit()
    return {"detail": "File deleted"}


# ── Delete sample ───────────────────────────────────────────────────────────

@router.delete("/projects/{project_id}/file-manager/samples/{sample_id}")
def delete_sample(
    project_id: uuid.UUID,
    sample_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    sample = db.query(Sample).filter(
        Sample.id == sample_id, Sample.project_id == project_id
    ).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    # Delete physical files
    for sf in sample.files:
        if sf.file_path and os.path.exists(sf.file_path):
            os.remove(sf.file_path)

    # Delete sample directory if it exists
    sample_dir = os.path.join(settings.UPLOAD_DIR, str(sample_id))
    if os.path.isdir(sample_dir):
        import shutil
        shutil.rmtree(sample_dir, ignore_errors=True)

    db.delete(sample)
    db.commit()
    return {"detail": "Sample and all associated files deleted"}
