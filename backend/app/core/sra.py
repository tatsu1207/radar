import logging
import os
import glob
import gzip
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models.models import (
    SRADownload,
    SRADownloadStatus,
    Sample,
    SampleFile,
    PairType,
    SequencingPlatform,
    FileSource,
)

logger = logging.getLogger(__name__)

# Progress ranges for each phase (0-100 overall)
PREFETCH_RANGE = (0, 45)       # 0-45%
FASTERQ_RANGE = (45, 75)      # 45-75%
COMPRESS_RANGE = (75, 95)     # 75-95%
# 95-100% = register files


def _map_progress(phase_pct: float, phase_range: tuple) -> float:
    """Map a 0-100 phase percentage to the overall progress range."""
    lo, hi = phase_range
    return lo + (hi - lo) * phase_pct / 100.0


def _stream_progress(proc, dl_id: str, phase_range: tuple, parse_fn):
    """Read stderr from a subprocess line-by-line, parse progress, update DB."""
    db = SessionLocal()
    try:
        for line in proc.stderr:
            pct = parse_fn(line)
            if pct is not None:
                overall = _map_progress(pct, phase_range)
                dl = db.query(SRADownload).filter(SRADownload.id == uuid.UUID(dl_id)).first()
                if dl:
                    dl.progress = round(overall, 1)
                    db.commit()
    except Exception:
        pass
    finally:
        db.close()


def _parse_prefetch_progress(line: str):
    """Parse prefetch stderr for progress percentage."""
    # prefetch outputs lines like: "SRR10971019 ( 234.5 MB / 1.2 GB ) 19%"
    m = re.search(r'(\d+)%', line)
    if m:
        return float(m.group(1))
    return None


def _parse_fasterq_progress(line: str):
    """Parse fasterq-dump stderr for progress percentage."""
    # fasterq-dump outputs: "spots read: 1,234,567" or progress like "25%"
    m = re.search(r'(\d+)%', line)
    if m:
        return float(m.group(1))
    return None


def _get_sra_platform(accession: str) -> SequencingPlatform | None:
    """Query SRA metadata for sequencing platform."""
    try:
        result = subprocess.run(
            ["conda", "run", "-n", "radar", "vdb-dump", "--info", accession],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("platf"):
                    platf = line.split(":", 1)[1].strip()
                    if "PACBIO" in platf:
                        return SequencingPlatform.pacbio
                    elif "OXFORD" in platf or "NANOPORE" in platf:
                        return SequencingPlatform.ont
                    elif "ILLUMINA" in platf:
                        return SequencingPlatform.illumina
    except Exception:
        pass
    return None


@celery_app.task(name="app.core.sra.download_sra")
def download_sra(download_id: str):
    db = SessionLocal()
    try:
        dl = db.query(SRADownload).filter(SRADownload.id == uuid.UUID(download_id)).first()
        if not dl:
            return

        # Update status to downloading
        dl.status = SRADownloadStatus.downloading
        dl.progress = 0.0
        db.commit()

        accession = dl.srr_accession
        output_dir = os.path.join(settings.UPLOAD_DIR, str(dl.sample_id))
        os.makedirs(output_dir, exist_ok=True)

        try:
            # Phase 1: Prefetch (0-45%)
            proc = subprocess.Popen(
                ["conda", "run", "-n", "radar", "prefetch", "--progress", accession],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            monitor = threading.Thread(
                target=_stream_progress,
                args=(proc, download_id, PREFETCH_RANGE, _parse_prefetch_progress),
                daemon=True,
            )
            monitor.start()
            stdout, stderr = proc.communicate(timeout=3600)
            monitor.join(timeout=5)
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, "prefetch", stderr)

            dl.progress = PREFETCH_RANGE[1]
            db.commit()

            # Phase 2: Fasterq-dump (45-75%)
            proc = subprocess.Popen(
                [
                    "conda", "run", "-n", "radar",
                    "fasterq-dump", accession,
                    "--outdir", output_dir,
                    "--split-files",
                    "--progress",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            monitor = threading.Thread(
                target=_stream_progress,
                args=(proc, download_id, FASTERQ_RANGE, _parse_fasterq_progress),
                daemon=True,
            )
            monitor.start()
            stdout, stderr = proc.communicate(timeout=7200)
            monitor.join(timeout=5)
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, "fasterq-dump", stderr)

            dl.progress = FASTERQ_RANGE[1]
            db.commit()

            # Phase 3: Compress (75-95%)
            fastq_files = sorted(glob.glob(os.path.join(output_dir, f"{accession}*.fastq")))
            for i, fq in enumerate(fastq_files):
                gz_path = fq + ".gz"
                with open(fq, "rb") as f_in:
                    with gzip.open(gz_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(fq)
                pct = _map_progress((i + 1) / len(fastq_files) * 100, COMPRESS_RANGE)
                dl.progress = round(pct, 1)
                db.commit()

            # Phase 4: Register files (95-100%)
            dl.progress = 95.0
            db.commit()

            gz_files = sorted(glob.glob(os.path.join(output_dir, f"{accession}*.fastq.gz")))

            if len(gz_files) == 0:
                raise RuntimeError("No output files produced by fasterq-dump")

            # Detect platform: SRA metadata first, then FASTQ headers
            from app.api.file_manager import _detect_platform_from_fastq
            sra_platform = _get_sra_platform(accession)
            if not sra_platform:
                detected_platform, _ = _detect_platform_from_fastq(gz_files[0])
                sra_platform = detected_platform
            platform = sra_platform or SequencingPlatform.illumina
            logger.info(f"SRA platform for {accession}: {platform} ({len(gz_files)} files)")

            is_long_read = platform in (SequencingPlatform.ont, SequencingPlatform.pacbio)

            if is_long_read:
                # Long-read: register largest file as long_read, skip others
                # (fasterq-dump --split-files may produce multiple files for ONT/PacBio)
                largest = max(gz_files, key=os.path.getsize)
                sf = SampleFile(
                    sample_id=dl.sample_id,
                    file_path=largest,
                    file_type=".fastq.gz",
                    pair=PairType.long_read,
                    platform=platform,
                    source=FileSource.sra,
                    original_filename=os.path.basename(largest),
                    file_size=os.path.getsize(largest),
                )
                db.add(sf)
            elif len(gz_files) >= 2:
                # Illumina paired-end
                for i, gz_file in enumerate(gz_files[:2]):
                    pair = PairType.R1 if i == 0 else PairType.R2
                    sf = SampleFile(
                        sample_id=dl.sample_id,
                        file_path=gz_file,
                        file_type=".fastq.gz",
                        pair=pair,
                        platform=platform,
                        source=FileSource.sra,
                        original_filename=os.path.basename(gz_file),
                        file_size=os.path.getsize(gz_file),
                    )
                    db.add(sf)
            else:
                # Illumina single-end
                gz_file = gz_files[0]
                sf = SampleFile(
                    sample_id=dl.sample_id,
                    file_path=gz_file,
                    file_type=".fastq.gz",
                    pair=PairType.single,
                    platform=platform,
                    source=FileSource.sra,
                    original_filename=os.path.basename(gz_file),
                    file_size=os.path.getsize(gz_file),
                )
                db.add(sf)

            dl.status = SRADownloadStatus.complete
            dl.progress = 100.0
            dl.finished_at = datetime.utcnow()
            db.commit()

        except Exception as e:
            dl.status = SRADownloadStatus.failed
            dl.error_message = str(e)[:2000]
            dl.finished_at = datetime.utcnow()
            db.commit()

    finally:
        db.close()
