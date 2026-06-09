import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.models import Sample, AnalysisJob, JobStatus
from app.schemas.schemas import AnalysisJobRead, AnalysisRequest

router = APIRouter(tags=["analysis"])

# Canonical pipeline step order
PIPELINE_STEPS = [
    "fastp", "assembly", "quast", "busco",
    "amrfinderplus", "mob_recon", "mefinder",
    "phenotype_prediction", "risk_scoring",
]


class StepRequest(BaseModel):
    tool: str
    threads: int = Field(default=4, ge=1, le=128)


@router.post("/samples/{sample_id}/analyze", response_model=AnalysisJobRead, status_code=202)
def start_analysis(
    sample_id: uuid.UUID,
    payload: AnalysisRequest = None,
    db: Session = Depends(get_db),
):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    if not sample.files:
        raise HTTPException(status_code=400, detail="Sample has no uploaded files")

    threads = payload.threads if payload else 4

    # Create a master pipeline job
    job = AnalysisJob(
        sample_id=sample_id,
        tool="pipeline",
        status="pending",
        threads=threads,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Dispatch Celery task
    try:
        from app.core.pipeline import run_pipeline
        result = run_pipeline.delay(str(sample_id), str(job.id), threads)
        job.celery_task_id = result.id
        db.commit()
    except Exception:
        job.log = "Warning: Celery broker unavailable. Task queued for manual processing."
        db.commit()

    return job


@router.post("/samples/{sample_id}/run-step", response_model=AnalysisJobRead, status_code=202)
def run_step(
    sample_id: uuid.UUID,
    payload: StepRequest,
    db: Session = Depends(get_db),
):
    """Run a single pipeline step for a sample."""
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    if payload.tool not in PIPELINE_STEPS:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {payload.tool}")

    # Create job for this step
    job = AnalysisJob(
        sample_id=sample_id,
        tool=payload.tool,
        status="pending",
        threads=payload.threads,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        from app.core.pipeline import run_single_step
        result = run_single_step.delay(str(sample_id), str(job.id), payload.tool, payload.threads)
        job.celery_task_id = result.id
        db.commit()
    except Exception:
        job.log = "Warning: Celery broker unavailable."
        db.commit()

    return job


@router.post("/jobs/{job_id}/cancel", response_model=AnalysisJobRead)
def cancel_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in (JobStatus.pending, JobStatus.running):
        raise HTTPException(status_code=400, detail=f"Cannot cancel job with status '{job.status}'")

    # Revoke the Celery task
    if job.celery_task_id:
        try:
            from app.celery_app import celery_app
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
        except Exception:
            pass

    # Cancel all sub-jobs for this sample that are pending/running
    if job.tool == "pipeline":
        sub_jobs = (
            db.query(AnalysisJob)
            .filter(
                AnalysisJob.sample_id == job.sample_id,
                AnalysisJob.id != job.id,
                AnalysisJob.status.in_([JobStatus.pending, JobStatus.running]),
            )
            .all()
        )
        for sj in sub_jobs:
            sj.status = JobStatus.cancelled
            sj.finished_at = datetime.utcnow()
            sj.log = (sj.log or "") + "\nCancelled by user"

    job.status = JobStatus.cancelled
    job.finished_at = datetime.utcnow()
    existing_log = job.log or ""
    job.log = existing_log + "\nCancelled by user"

    # Reset sample status
    sample = db.query(Sample).filter(Sample.id == job.sample_id).first()
    if sample:
        from app.models.models import SampleStatus
        sample.status = SampleStatus.pending
    db.commit()

    return job


@router.get("/samples/{sample_id}/jobs", response_model=List[AnalysisJobRead])
def list_jobs(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    jobs = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.sample_id == sample_id)
        .order_by(AnalysisJob.started_at.desc().nullslast())
        .all()
    )
    return jobs


@router.get("/projects/{project_id}/jobs", response_model=List[AnalysisJobRead])
def list_project_jobs(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get all jobs for all samples in a project."""
    from app.models.models import Sample as SampleModel
    sample_ids = [s.id for s in db.query(SampleModel.id).filter(SampleModel.project_id == project_id).all()]
    if not sample_ids:
        return []
    jobs = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.sample_id.in_(sample_ids))
        .all()
    )
    return jobs


@router.get("/jobs/{job_id}", response_model=AnalysisJobRead)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ── Preprocessing Pipeline ─────────────────────────────────────────────────

@router.get("/pipeline/status")
def pipeline_status(db: Session = Depends(get_db)):
    """Get preprocessing pipeline status for all samples."""
    from sqlalchemy.orm import joinedload

    samples = db.query(Sample).order_by(Sample.name).all()

    result = []
    for s in samples:
        # Find the latest preprocessing job for this sample
        job = (
            db.query(AnalysisJob)
            .filter(
                AnalysisJob.sample_id == s.id,
                AnalysisJob.tool == "preprocessing",
            )
            .order_by(AnalysisJob.started_at.desc().nullslast())
            .first()
        )

        status = "not_started"
        job_id = None
        log = None
        if job:
            job_id = str(job.id)
            log = job.log
            if job.status == JobStatus.complete:
                status = "complete"
            elif job.status in (JobStatus.running, JobStatus.pending):
                status = "running"
            elif job.status == JobStatus.failed:
                status = "failed"

        # Check if QC reports exist
        qc_dir = os.path.join(settings.RESULTS_DIR, str(s.id), "assembly")
        quast_report = os.path.join(qc_dir, "quast", "report.tsv")
        busco_dir = os.path.join(qc_dir, "busco", "busco_result")
        has_qc = os.path.exists(quast_report) or os.path.isdir(busco_dir)

        result.append({
            "sample_id": str(s.id),
            "sample_name": s.name,
            "status": status,
            "job_id": job_id,
            "log": log,
            "has_qc": has_qc,
        })

    return result


@router.get("/pipeline/qc/{sample_id}")
def download_qc_report(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Download combined QUAST + BUSCO QC report as text."""
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    qc_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    parts = [f"Assembly QC Report: {sample.name}", "=" * 50, ""]

    # Contig Circularity (from assembly FASTA headers)
    assembly_fasta = os.path.join(qc_dir, "assembly.fasta")
    if os.path.exists(assembly_fasta):
        import re
        parts.append("Contig Circularity")
        parts.append("-" * 30)
        with open(assembly_fasta) as f:
            for line in f:
                if line.startswith(">"):
                    header = line.strip()[1:]
                    # Parse: "1 length=5268325 depth=1.00x circular=true"
                    name = header.split()[0]
                    length_m = re.search(r'length=(\d+)', header)
                    depth_m = re.search(r'depth=([\d.]+)x', header)
                    circ_m = re.search(r'circular=(\w+)', header)
                    length = length_m.group(1) if length_m else "?"
                    depth = depth_m.group(1) if depth_m else "?"
                    circular = circ_m.group(1) if circ_m else "unknown"
                    status = "CIRCULAR" if circular == "true" else "LINEAR"
                    parts.append(f"  Contig {name}: {length} bp, depth {depth}x, {status}")
        parts.append("")

    # QUAST
    quast_report = os.path.join(qc_dir, "quast", "report.tsv")
    if os.path.exists(quast_report):
        parts.append("QUAST Assembly Metrics")
        parts.append("-" * 30)
        with open(quast_report) as f:
            parts.append(f.read().strip())
        parts.append("")
    else:
        parts.append("QUAST: not available")
        parts.append("")

    # BUSCO
    busco_result_dir = os.path.join(qc_dir, "busco", "busco_result")
    busco_found = False
    if os.path.isdir(busco_result_dir):
        for root, dirs, files in os.walk(busco_result_dir):
            for fname in files:
                if fname.startswith("short_summary"):
                    parts.append("BUSCO Completeness Assessment")
                    parts.append("-" * 30)
                    with open(os.path.join(root, fname)) as f:
                        parts.append(f.read().strip())
                    parts.append("")
                    busco_found = True
                    break
            if busco_found:
                break

    if not busco_found:
        parts.append("BUSCO: not available")
        parts.append("")

    report = "\n".join(parts)
    return PlainTextResponse(
        content=report,
        headers={"Content-Disposition": f"attachment; filename={sample.name}_qc_report.txt"},
    )


@router.get("/pipeline/assembly/{sample_id}")
def download_assembly(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Download assembled genome FASTA."""
    from fastapi.responses import FileResponse
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    assembly_path = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly", "assembly.fasta")
    if not os.path.exists(assembly_path):
        raise HTTPException(status_code=404, detail="Assembly not found")
    filename = f"{sample.name}_assembly.fasta"
    return FileResponse(assembly_path, media_type="application/octet-stream", filename=filename)


@router.get("/pipeline/qc/{sample_id}/fastp")
def get_fastp_report(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Serve fastp HTML report."""
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    report_path = os.path.join(settings.RESULTS_DIR, str(sample_id), "qc", "fastp_report.html")
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="fastp report not found")
    with open(report_path) as f:
        return HTMLResponse(content=f.read())


@router.get("/pipeline/qc/{sample_id}/quast")
def get_quast_report(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Serve QUAST HTML report."""
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    report_path = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly", "quast", "report.html")
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="QUAST report not found")
    with open(report_path) as f:
        return HTMLResponse(content=f.read())


class PipelineStartRequest(BaseModel):
    threads: int = Field(default=12, ge=1, le=128)


@router.post("/pipeline/start/{sample_id}")
def start_preprocessing(
    sample_id: uuid.UUID,
    payload: PipelineStartRequest = None,
    db: Session = Depends(get_db),
):
    """Start the preprocessing pipeline (fastp + Chopper + SPAdes/Flye) for a sample."""
    threads = payload.threads if payload else 12

    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    if not sample.files:
        raise HTTPException(status_code=400, detail="Sample has no uploaded files")

    # Clean up stale running jobs (older than 2 hours) and allow restart
    stale_cutoff = datetime.utcnow() - __import__('datetime').timedelta(hours=2)
    stale_jobs = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.sample_id == sample_id,
            AnalysisJob.tool == "preprocessing",
            AnalysisJob.status.in_([JobStatus.pending, JobStatus.running]),
        )
        .all()
    )
    for sj in stale_jobs:
        if sj.started_at and sj.started_at < stale_cutoff:
            sj.status = JobStatus.failed
            sj.finished_at = datetime.utcnow()
            sj.log = (sj.log or "") + "\nMarked failed (stale job cleanup)\n"
        else:
            # Genuinely running
            raise HTTPException(status_code=409, detail="Preprocessing already in progress")
    db.commit()

    job = AnalysisJob(
        sample_id=sample_id,
        tool="preprocessing",
        status=JobStatus.pending,
        threads=threads,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        from app.core.pipeline import run_preprocessing
        result = run_preprocessing.delay(str(sample_id), str(job.id), threads)
        job.celery_task_id = result.id
        db.commit()
    except Exception:
        job.log = "Warning: Celery broker unavailable. Task queued."
        db.commit()

    return {"job_id": str(job.id), "status": "started"}
