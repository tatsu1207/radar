import logging
import os
import subprocess
from datetime import datetime
from typing import List

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models.models import (
    ComparativeAnalysisJob,
    JobStatus,
    MashtreeResult,
    Sample,
    SampleFile,
)

logger = logging.getLogger(__name__)

CONDA_TREE = "radar-tree"


@celery_app.task(name="run_mashtree", bind=True)
def run_mashtree(
    self,
    project_id: str,
    job_id: str,
    sample_ids: List[str],
    threads: int = 4,
):
    """Run Mashtree for rapid phylogenomic distance tree.

    Uses MinHash sketches from assemblies to compute pairwise distances
    and build a neighbor-joining tree.
    """
    db = SessionLocal()
    try:
        job = db.query(ComparativeAnalysisJob).filter(
            ComparativeAnalysisJob.id == job_id
        ).first()
        if not job:
            return
        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        job.log = "Collecting assemblies for Mashtree...\n"
        db.commit()

        results_dir = os.path.join(
            settings.RESULTS_DIR, "projects", str(project_id), "mashtree"
        )
        os.makedirs(results_dir, exist_ok=True)

        # Collect assembly paths
        assembly_paths = []
        for sid in sample_ids:
            asm = _get_assembly_path(sid, db)
            if asm:
                assembly_paths.append(asm)
            else:
                sample = db.query(Sample).filter(Sample.id == sid).first()
                name = sample.name if sample else sid
                job.log += f"  WARNING: No assembly for {name}, skipping\n"
                db.commit()

        if len(assembly_paths) < 3:
            raise RuntimeError(
                f"Need at least 3 assemblies for Mashtree, got {len(assembly_paths)}"
            )

        job.log += f"Running Mashtree on {len(assembly_paths)} assemblies...\n"
        db.commit()

        newick_path = os.path.join(results_dir, "mashtree.nwk")
        matrix_path = os.path.join(results_dir, "mashtree.distances.tsv")

        cmd = [
            "conda", "run", "-n", CONDA_TREE,
            "mashtree",
            "--numcpus", str(threads),
            "--outtree", newick_path,
            *assembly_paths,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            raise RuntimeError(f"Mashtree failed: {result.stderr[-1000:]}")

        # Save distance matrix if produced
        if result.stdout.strip():
            with open(matrix_path, "w") as f:
                f.write(result.stdout)

        # Save result
        mt = MashtreeResult(
            project_id=project_id,
            job_id=job_id,
            newick_path=newick_path if os.path.exists(newick_path) else None,
            distance_matrix_path=matrix_path if os.path.exists(matrix_path) else None,
        )
        db.add(mt)

        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        job.result_dir = results_dir
        job.log += f"Mashtree complete: tree saved to {newick_path}\n"
        db.commit()

        logger.info(f"Mashtree complete for project {project_id}")

    except Exception as e:
        logger.error(f"Mashtree failed: {e}")
        try:
            job = db.query(ComparativeAnalysisJob).filter(
                ComparativeAnalysisJob.id == job_id
            ).first()
            if job:
                job.status = JobStatus.failed
                job.finished_at = datetime.utcnow()
                job.log = (job.log or "") + f"FAILED: {str(e)}\n"
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


def _get_assembly_path(sample_id: str, db):
    """Find assembly FASTA for a sample."""
    assembly = os.path.join(
        settings.RESULTS_DIR, str(sample_id), "assembly", "assembly.fasta"
    )
    if os.path.exists(assembly):
        return assembly

    files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
    fasta_exts = (".fasta", ".fa", ".fna")
    for f in files:
        if any(f.file_path.endswith(ext) for ext in fasta_exts):
            return f.file_path
    return None
