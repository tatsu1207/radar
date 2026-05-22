import csv
import logging
import os
import subprocess
from datetime import datetime
from typing import List

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models.models import (
    BaktaAnnotation,
    ComparativeAnalysisJob,
    JobStatus,
    PangenomeResult,
    Sample,
)

logger = logging.getLogger(__name__)

CONDA_PANGENOME = "radar-pangenome"


@celery_app.task(name="run_pangenome", bind=True)
def run_pangenome(self, project_id: str, job_id: str, sample_ids: List[str], threads: int = 4):
    """Run Panaroo pan-genome analysis on project samples.

    Takes Bakta GFF3 outputs from all specified samples and constructs
    a pan-genome with gene presence/absence matrix.
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
        job.log = "Collecting Bakta GFF3 files...\n"
        db.commit()

        results_dir = os.path.join(settings.RESULTS_DIR, "projects", str(project_id), "pangenome")
        os.makedirs(results_dir, exist_ok=True)

        # Collect GFF3 files from Bakta annotations
        gff_files = []
        for sid in sample_ids:
            annotation = db.query(BaktaAnnotation).filter(
                BaktaAnnotation.sample_id == sid
            ).first()
            if annotation and annotation.gff_path and os.path.exists(annotation.gff_path):
                gff_files.append(annotation.gff_path)
            else:
                sample = db.query(Sample).filter(Sample.id == sid).first()
                name = sample.name if sample else sid
                job.log += f"  WARNING: No Bakta GFF3 for sample {name}, skipping\n"
                db.commit()

        if len(gff_files) < 2:
            raise RuntimeError(
                f"Need at least 2 annotated samples for pan-genome, got {len(gff_files)}"
            )

        job.log += f"Running Panaroo on {len(gff_files)} samples...\n"
        db.commit()

        # Run Panaroo
        cmd = [
            "conda", "run", "-n", CONDA_PANGENOME,
            "panaroo",
            "-i", *gff_files,
            "-o", results_dir,
            "--clean-mode", "moderate",
            "-t", str(threads),
            "--core_threshold", "0.95",
            "-a", "core",  # produce core genome alignment
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if result.returncode != 0:
            raise RuntimeError(f"Panaroo failed: {result.stderr[-1000:]}")

        # Parse summary
        summary = _parse_panaroo_summary(results_dir)

        gpa_path = os.path.join(results_dir, "gene_presence_absence.csv")
        core_aln_path = os.path.join(results_dir, "core_gene_alignment.aln")

        # Save result
        pr = PangenomeResult(
            project_id=project_id,
            job_id=job_id,
            core_genes=summary.get("core", 0),
            soft_core_genes=summary.get("soft_core", 0),
            shell_genes=summary.get("shell", 0),
            cloud_genes=summary.get("cloud", 0),
            total_genes=summary.get("total", 0),
            gene_presence_absence_path=gpa_path if os.path.exists(gpa_path) else None,
            core_alignment_path=core_aln_path if os.path.exists(core_aln_path) else None,
        )
        db.add(pr)

        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        job.result_dir = results_dir
        job.log += (
            f"Panaroo complete: {summary.get('total', 0)} total genes "
            f"({summary.get('core', 0)} core, {summary.get('shell', 0)} shell, "
            f"{summary.get('cloud', 0)} cloud)\n"
        )
        db.commit()

        logger.info(f"Pan-genome complete for project {project_id}")

    except Exception as e:
        logger.error(f"Pan-genome failed for project {project_id}: {e}")
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


def _parse_panaroo_summary(results_dir: str) -> dict:
    """Parse Panaroo output to count gene categories."""
    summary = {"core": 0, "soft_core": 0, "shell": 0, "cloud": 0, "total": 0}

    summary_file = os.path.join(results_dir, "summary_statistics.txt")
    if os.path.exists(summary_file):
        with open(summary_file) as f:
            for line in f:
                line = line.strip().lower()
                if "core genes" in line:
                    summary["core"] = _extract_count(line)
                elif "soft core" in line:
                    summary["soft_core"] = _extract_count(line)
                elif "shell genes" in line:
                    summary["shell"] = _extract_count(line)
                elif "cloud genes" in line:
                    summary["cloud"] = _extract_count(line)
                elif "total genes" in line:
                    summary["total"] = _extract_count(line)
        return summary

    # Fallback: count from gene_presence_absence.csv
    gpa_file = os.path.join(results_dir, "gene_presence_absence.csv")
    if os.path.exists(gpa_file):
        with open(gpa_file) as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header:
                n_samples = len(header) - 3  # first 3 cols are gene info
                for row in reader:
                    summary["total"] += 1
                    present = sum(1 for v in row[3:] if v.strip())
                    frac = present / n_samples if n_samples > 0 else 0
                    if frac >= 0.99:
                        summary["core"] += 1
                    elif frac >= 0.95:
                        summary["soft_core"] += 1
                    elif frac >= 0.15:
                        summary["shell"] += 1
                    else:
                        summary["cloud"] += 1

    return summary


def _extract_count(line: str) -> int:
    """Extract integer from a summary line like 'Core genes: 3245'."""
    import re
    match = re.search(r"(\d+)", line)
    return int(match.group(1)) if match else 0
