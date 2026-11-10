"""Per-sample file downloads: input reads, QC reports, assembly, QUAST/BUSCO and
annotation results, plus a ZIP of all results.

The browser cannot send the Authorization header with a plain link, and reading a
multi-GB FASTQ into a blob would exhaust its memory. So downloads are two steps:
  1. POST /samples/{id}/files/{key}/link  (authenticated) -> short-lived signed URL
  2. GET  /download/{token}               (no header)     -> streamed file
The signed token carries no user ("sub"), so it can never be used as a login token,
and it names one file of one sample.
"""
import glob
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.api.results import build_sample_annotations_tsv
from app.config import settings
from app.core import nanoplot
from app.core.auth import get_current_user
from app.db import get_db
from app.models.models import PairType, Sample, SampleFile, User

router = APIRouter(tags=["downloads"])

LINK_MINUTES = 10
TOKEN_PURPOSE = "sample-download"

CATEGORIES = [
    ("reads", "Sequencing reads"),
    ("read_qc", "Read QC reports"),
    ("assembly", "Assembly & assembly QC"),
    ("annotation", "Annotation results"),
    ("bundle", "All results"),
]


class FileItem:
    def __init__(self, key: str, category: str, label: str, filename: str,
                 path: Optional[str] = None, build: Optional[Callable[[], bytes]] = None,
                 viewable: bool = False, in_zip: bool = True, zip_name: Optional[str] = None):
        self.key = key
        self.category = category
        self.label = label
        self.filename = filename
        self.path = path            # file on disk, or
        self.build = build          # content generated on request
        self.viewable = viewable    # HTML report that can open in a browser tab
        self.in_zip = in_zip
        self.zip_name = zip_name or filename

    def size(self) -> Optional[int]:
        try:
            return os.path.getsize(self.path) if self.path else None
        except OSError:
            return None


def _first(pattern: str) -> Optional[str]:
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else None


def _catalog(sample: Sample, db: Session) -> List[FileItem]:
    """Every downloadable item that exists for this sample, in display order."""
    sid = str(sample.id)
    name = sample.name
    res = os.path.join(settings.RESULTS_DIR, sid)
    qc = os.path.join(res, "qc")
    asm = os.path.join(res, "assembly")
    items: List[FileItem] = []

    def add(key, category, label, filename, path, **kw):
        if path and os.path.isfile(path):
            items.append(FileItem(key, category, label, filename, path=path, **kw))

    # Reads (uploaded and QC-processed); not put in the results ZIP (size)
    pair_label = {PairType.R1: "Illumina R1", PairType.R2: "Illumina R2",
                  PairType.long_read: "Long reads", PairType.single: "Reads",
                  PairType.assembly: "Input assembly"}
    files = db.query(SampleFile).filter(SampleFile.sample_id == sample.id).all()
    for f in files:
        base = f.original_filename or os.path.basename(f.file_path)
        platform = f" ({f.platform.value})" if f.platform else ""
        add(f"upload-{f.id}", "reads", f"{pair_label.get(f.pair, 'File')}{platform}: uploaded",
            base, f.file_path, in_zip=False)
    add("trimmed-r1", "reads", "Illumina R1: after fastp", f"{name}_trimmed_R1.fastq.gz",
        os.path.join(qc, "trimmed_R1.fastq.gz"), in_zip=False)
    add("trimmed-r2", "reads", "Illumina R2: after fastp", f"{name}_trimmed_R2.fastq.gz",
        os.path.join(qc, "trimmed_R2.fastq.gz"), in_zip=False)
    add("filtered-long", "reads", "Long reads: after Chopper", f"{name}_filtered_long.fastq.gz",
        os.path.join(qc, "filtered_long.fastq.gz"), in_zip=False)

    # Read QC
    add("fastp-html", "read_qc", "fastp report (Illumina)", f"{name}_fastp_report.html",
        os.path.join(qc, "fastp_report.html"), viewable=True, zip_name="qc/fastp_report.html")
    add("fastp-json", "read_qc", "fastp statistics (JSON)", f"{name}_fastp_report.json",
        os.path.join(qc, "fastp_report.json"), zip_name="qc/fastp_report.json")
    for stage, desc in (("raw", "uploaded long reads"), ("filtered", "long reads after Chopper")):
        add(f"nanoplot-{stage}-html", "read_qc", f"NanoPlot report: {desc}",
            f"{name}_NanoPlot-report_{stage}.html", nanoplot.report_path(sid, stage),
            viewable=True, zip_name=f"qc/nanoplot_{stage}/NanoPlot-report.html")
        add(f"nanoplot-{stage}-stats", "read_qc", f"NanoStats: {desc}",
            f"{name}_NanoStats_{stage}.txt", nanoplot.stats_path(sid, stage),
            zip_name=f"qc/nanoplot_{stage}/NanoStats.txt")

    # Assembly + QC
    add("assembly", "assembly", "Assembly (FASTA)", f"{name}_assembly.fasta",
        os.path.join(asm, "assembly.fasta"), zip_name="assembly/assembly.fasta")
    add("quast-html", "assembly", "QUAST report", f"{name}_quast_report.html",
        os.path.join(asm, "quast", "report.html"), viewable=True, zip_name="assembly/quast/report.html")
    add("quast-tsv", "assembly", "QUAST statistics (TSV)", f"{name}_quast_report.tsv",
        os.path.join(asm, "quast", "report.tsv"), zip_name="assembly/quast/report.tsv")
    busco = os.path.join(asm, "busco", "busco_result")
    add("busco-summary", "assembly", "BUSCO summary", f"{name}_busco_short_summary.txt",
        _first(os.path.join(busco, "short_summary*.txt")) or _first(os.path.join(busco, "run_*", "short_summary.txt")),
        zip_name="assembly/busco/short_summary.txt")
    add("busco-table", "assembly", "BUSCO full table (TSV)", f"{name}_busco_full_table.tsv",
        _first(os.path.join(busco, "run_*", "full_table.tsv")), zip_name="assembly/busco/full_table.tsv")

    # Annotation (generated from the database)
    def annotations() -> bytes:
        return build_sample_annotations_tsv(sample.id, db)[1].encode()
    if os.path.isfile(os.path.join(asm, "assembly.fasta")) or any(f.pair == PairType.assembly for f in files):
        items.append(FileItem("annotations", "annotation", "All annotation results (TSV)",
                              f"{name}_annotations.tsv", build=annotations,
                              zip_name="annotation/annotations.tsv"))

    # Bundle
    if any(i.in_zip for i in items):
        items.append(FileItem("results-zip", "bundle", "All results except reads (ZIP)",
                              f"{name}_RADAR_results.zip", build=None, in_zip=False))
    return items


def _get_sample(sample_id: uuid.UUID, db: Session) -> Sample:
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return sample


@router.get("/samples/{sample_id}/files")
def list_sample_files(sample_id: uuid.UUID, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """Downloadable files for one sample, grouped by category, plus NanoPlot read stats."""
    sample = _get_sample(sample_id, db)
    items = _catalog(sample, db)
    groups = []
    for cat, title in CATEGORIES:
        entries = [{"key": i.key, "label": i.label, "filename": i.filename,
                    "size": i.size(), "viewable": i.viewable}
                   for i in items if i.category == cat]
        if entries:
            groups.append({"category": cat, "title": title, "items": entries})
    return {
        "sample_id": str(sample.id),
        "sample_name": sample.name,
        "groups": groups,
        "read_qc": {
            "fastp": any(i.key == "fastp-html" for i in items),
            "nanoplot": {stage: (nanoplot.read_stats(str(sample.id), stage)
                                 if os.path.isfile(nanoplot.report_path(str(sample.id), stage)) else None)
                         for stage in nanoplot.STAGES},
        },
    }


class LinkRequest(BaseModel):
    inline: bool = False   # open an HTML report in the browser instead of saving it


@router.post("/samples/{sample_id}/files/{key}/link")
def create_download_link(sample_id: uuid.UUID, key: str, payload: LinkRequest = None,
                         db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Short-lived signed URL for one file of one sample."""
    sample = _get_sample(sample_id, db)
    item = next((i for i in _catalog(sample, db) if i.key == key), None)
    if not item:
        raise HTTPException(status_code=404, detail="File not available for this sample")
    inline = bool(payload and payload.inline and item.viewable)
    token = jwt.encode({
        "purpose": TOKEN_PURPOSE,
        "sample": str(sample.id),
        "key": key,
        "inline": inline,
        "by": current_user.username,
        "exp": datetime.utcnow() + timedelta(minutes=LINK_MINUTES),
    }, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {"url": f"/api/download/{token}", "filename": item.filename, "expires_minutes": LINK_MINUTES}


@router.get("/download/{token}")
def download_file(token: str, db: Session = Depends(get_db)):
    """Serve a file named by a signed link from create_download_link."""
    try:
        claims = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=403, detail="Download link is invalid or has expired")
    if claims.get("purpose") != TOKEN_PURPOSE or "sub" in claims:
        raise HTTPException(status_code=403, detail="Invalid download link")
    sample = _get_sample(uuid.UUID(claims["sample"]), db)
    items = _catalog(sample, db)
    item = next((i for i in items if i.key == claims["key"]), None)
    if not item:
        raise HTTPException(status_code=404, detail="File no longer available")
    disposition = "inline" if claims.get("inline") else "attachment"

    if item.key == "results-zip":
        path = _build_zip(sample, items)
        return FileResponse(path, filename=item.filename, media_type="application/zip",
                            background=BackgroundTask(os.remove, path))
    if item.build:
        return Response(item.build(), media_type="text/tab-separated-values",
                        headers={"Content-Disposition": f'attachment; filename="{item.filename}"'})
    media = "text/html" if item.viewable else None
    return FileResponse(item.path, filename=item.filename, media_type=media,
                        content_disposition_type=disposition)


def _build_zip(sample: Sample, items: List[FileItem]) -> str:
    """ZIP of every result item (not reads) in a temp file; deleted after sending."""
    fd, path = tempfile.mkstemp(prefix="radar_results_", suffix=".zip")
    os.close(fd)
    root = sample.name
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            if not item.in_zip:
                continue
            arc = f"{root}/{item.zip_name}"
            if item.build:
                zf.writestr(arc, item.build())
            else:
                zf.write(item.path, arc)
    return path
