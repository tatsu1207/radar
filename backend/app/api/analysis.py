import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.models import Sample, AnalysisJob, JobStatus
from app.schemas.schemas import AnalysisJobRead, AnalysisRequest

router = APIRouter(tags=["analysis"])

# Canonical pipeline step order
PIPELINE_STEPS = [
    "bbduk", "unicycler", "quast", "busco",
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
