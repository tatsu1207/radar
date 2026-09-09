"""Celery tasks for heavy comparative genomics tools.

Wraps synchronous tool functions as async Celery tasks that save
results as JSON files. Frontend polls for completion via job_id.
"""

import json
import logging
import os
from datetime import datetime

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models.models import AnalysisJob, JobStatus

logger = logging.getLogger(__name__)

TOOLS_RESULTS_DIR = os.path.join(settings.RESULTS_DIR, "tools")


def _save_result(job_id: str, tool: str, data: dict):
    """Save tool result as JSON file."""
    tool_dir = os.path.join(TOOLS_RESULTS_DIR, tool)
    os.makedirs(tool_dir, exist_ok=True)
    path = os.path.join(tool_dir, f"{job_id}.json")
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _load_result(job_id: str, tool: str) -> dict | None:
    """Load tool result from JSON file."""
    path = os.path.join(TOOLS_RESULTS_DIR, tool, f"{job_id}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


@celery_app.task(name="tool_ani", bind=True)
def task_ani(self, sample_ids: list, job_id: str):
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            return
        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        db.commit()

        from app.core.ani import compute_ani_for_samples
        ani_result = compute_ani_for_samples(sample_ids, db)

        from app.core.outbreak import detect_clusters_for_samples
        cluster_result = detect_clusters_for_samples(
            sample_ids, db,
            ani_matrix=ani_result.get("ani_matrix"),
            ani_sample_ids=ani_result.get("sample_ids"),
        )

        _save_result(job_id, "ani", {"ani": ani_result, "clusters": cluster_result})

        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.error(f"ANI task failed: {e}")
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                job.status = JobStatus.failed
                job.finished_at = datetime.utcnow()
                job.log = str(e)[:1000]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@celery_app.task(name="tool_syntracker", bind=True)
def task_syntracker(self, sample_ids: list, job_id: str, mode: str = "full", flanking: int = 20000):
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            return
        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        db.commit()

        from app.core.syntracker import compute_synteny_for_samples
        result = compute_synteny_for_samples(sample_ids, db, mode=mode, flanking=flanking)

        _save_result(job_id, "syntracker", result)

        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.error(f"SynTracker task failed: {e}")
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                job.status = JobStatus.failed
                job.finished_at = datetime.utcnow()
                job.log = str(e)[:1000]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@celery_app.task(name="tool_easyfig", bind=True)
def task_easyfig(self, sample_ids: list, job_id: str):
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            return
        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        db.commit()

        from app.core.easyfig import compute_easyfig
        result = compute_easyfig(sample_ids, db)

        _save_result(job_id, "easyfig", result)

        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.error(f"EasyFig task failed: {e}")
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                job.status = JobStatus.failed
                job.finished_at = datetime.utcnow()
                job.log = str(e)[:1000]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@celery_app.task(name="tool_pangenome", bind=True)
def task_pangenome(self, sample_ids: list, job_id: str):
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            return
        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        db.commit()

        from app.core.pangenome import compute_pangenome
        result = compute_pangenome(sample_ids, db)

        _save_result(job_id, "pangenome", result)

        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.error(f"Pangenome task failed: {e}")
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                job.status = JobStatus.failed
                job.finished_at = datetime.utcnow()
                job.log = str(e)[:1000]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
