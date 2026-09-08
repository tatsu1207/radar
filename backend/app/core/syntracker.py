"""SynTracker integration — all-vs-all synteny conservation analysis.

Runs SynTracker on selected isolate assemblies to compute pairwise
Average Pairwise Synteny Scores (APSS). Executed as a Celery task
since it can take minutes for many samples.
"""

import csv
import logging
import os
import shutil
import tempfile
from datetime import datetime
from typing import Dict, List, Optional

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models.models import AnalysisJob, JobStatus, Sample

logger = logging.getLogger(__name__)

CONDA_ENV = "syntracker"
SYNTRACKER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "tools", "SynTracker", "syntracker.py",
)


def _get_assembly_path(sample_id: str) -> Optional[str]:
    asm = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly", "assembly.fasta")
    return asm if os.path.exists(asm) else None


def _parse_apss_matrix(summary_dir: str, sample_names: List[str]) -> Optional[Dict]:
    """Parse SynTracker APSS summary output into a pairwise matrix.

    SynTracker outputs CSV files in summary_output/ with columns like:
    sample1, sample2, synteny_score (or similar pairwise format).
    The exact format depends on the version — we try multiple parsings.
    """
    # Try the all-regions file first
    apss_file = os.path.join(summary_dir, "avg_synteny_scores_all_regions.csv")
    if not os.path.exists(apss_file):
        # Try per-region file
        apss_file = os.path.join(summary_dir, "synteny_scores_per_region.csv")
    if not os.path.exists(apss_file):
        # Look for any CSV
        csvs = [f for f in os.listdir(summary_dir) if f.endswith(".csv")]
        if csvs:
            apss_file = os.path.join(summary_dir, csvs[0])
        else:
            return None

    # Read the CSV — SynTracker APSS files are pairwise matrices
    # Format: rows and columns are sample names, values are APSS scores
    try:
        with open(apss_file) as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return None

        # Check if it's a matrix format (header row = sample names)
        header = rows[0]
        n = len(sample_names)

        # Try to parse as a square matrix
        # First column may be row names, rest are values
        if len(header) >= n:
            matrix = []
            name_to_idx = {}
            # Header might have an empty first cell (row label column)
            col_names = header[1:] if header[0] == "" or header[0].lower() in ("", "x", "sample") else header
            for i, name in enumerate(col_names):
                # Strip path and extension to get sample name
                clean = os.path.splitext(os.path.basename(name))[0]
                name_to_idx[clean] = i

            for row in rows[1:]:
                row_name = os.path.splitext(os.path.basename(row[0]))[0]
                values = row[1:] if len(row) > len(col_names) else row
                matrix.append([float(v) if v else 0.0 for v in values[:len(col_names)]])

            # Reorder to match sample_names order
            ordered_matrix = [[0.0] * n for _ in range(n)]
            for i, name_i in enumerate(sample_names):
                idx_i = name_to_idx.get(name_i)
                if idx_i is None:
                    continue
                for j, name_j in enumerate(sample_names):
                    idx_j = name_to_idx.get(name_j)
                    if idx_j is None:
                        continue
                    if idx_i < len(matrix) and idx_j < len(matrix[idx_i]):
                        ordered_matrix[i][j] = round(matrix[idx_i][idx_j], 4)

            return {"apss_matrix": ordered_matrix}

    except Exception as e:
        logger.warning(f"Failed to parse APSS matrix: {e}")

    # Fallback: return raw file content
    return None


@celery_app.task(name="run_syntracker", bind=True)
def run_syntracker_task(self, sample_ids: list, job_id: str, threads: int = 4):
    """Run SynTracker all-vs-all on selected samples."""
    import subprocess

    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            logger.error(f"SynTracker job {job_id} not found")
            return

        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        job.log = "SynTracker started\n"
        db.commit()

        # Collect assemblies
        sample_info = []  # [(sample_name, assembly_path)]
        for sid in sample_ids:
            s = db.query(Sample).filter(Sample.id == sid).first()
            if not s:
                continue
            asm = _get_assembly_path(str(s.id))
            if asm:
                sample_info.append((s.name, asm))

        if len(sample_info) < 2:
            job.log += "Need at least 2 samples with assemblies\n"
            job.status = JobStatus.failed
            job.finished_at = datetime.utcnow()
            db.commit()
            return

        job.log += f"Running on {len(sample_info)} samples\n"
        db.commit()

        # Create temp dirs with symlinks
        work_dir = tempfile.mkdtemp(prefix="syntracker_")
        ref_dir = os.path.join(work_dir, "ref")
        target_dir = os.path.join(work_dir, "target")
        output_dir = os.path.join(work_dir, "output")
        os.makedirs(ref_dir)
        os.makedirs(target_dir)

        sample_names = []
        for name, asm_path in sample_info:
            # Use sample name as filename (SynTracker uses filenames as labels)
            safe_name = name.replace(" ", "_").replace("/", "_")
            sample_names.append(safe_name)
            os.symlink(asm_path, os.path.join(ref_dir, f"{safe_name}.fasta"))
            os.symlink(asm_path, os.path.join(target_dir, f"{safe_name}.fasta"))

        # Run SynTracker
        cmd = [
            "conda", "run", "-n", CONDA_ENV,
            "python", SYNTRACKER_SCRIPT,
            "-target", target_dir,
            "-ref", ref_dir,
            "-out", output_dir,
            "-cores", str(threads),
            "-mode", "new",
        ]

        job.log += f"Command: {' '.join(cmd)}\n"
        db.commit()

        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=3600,  # 1 hour max
            cwd=work_dir,
        )

        if result.returncode != 0:
            job.log += f"SynTracker failed:\n{result.stderr[-1000:]}\n"
            job.status = JobStatus.failed
            job.finished_at = datetime.utcnow()
            db.commit()
            return

        job.log += "SynTracker completed, parsing results...\n"
        db.commit()

        # Parse results
        summary_dir = os.path.join(output_dir, "summary_output")
        if not os.path.isdir(summary_dir):
            # Check per-genome output dirs
            genome_dirs = [d for d in os.listdir(output_dir)
                          if os.path.isdir(os.path.join(output_dir, d))
                          and d not in ("summary_output",)]
            job.log += f"Output dirs: {os.listdir(output_dir)}\n"
            if genome_dirs:
                # Look for final_output in first genome dir
                for gd in genome_dirs:
                    final = os.path.join(output_dir, gd, "final_output")
                    if os.path.isdir(final):
                        summary_dir = final
                        break

        parsed = None
        if os.path.isdir(summary_dir):
            parsed = _parse_apss_matrix(summary_dir, sample_names)
            # List all output files for debugging
            for f in os.listdir(summary_dir):
                job.log += f"  Output: {f}\n"

        if parsed:
            # Store result as JSON in the job log (will be extracted by API)
            import json
            result_data = {
                "samples": sample_names,
                "sample_ids": sample_ids,
                "apss_matrix": parsed["apss_matrix"],
            }
            # Save to a result file
            result_file = os.path.join(settings.RESULTS_DIR, "syntracker", f"{job_id}.json")
            os.makedirs(os.path.dirname(result_file), exist_ok=True)
            with open(result_file, "w") as f:
                json.dump(result_data, f)

            job.log += f"Results saved to {result_file}\n"
        else:
            job.log += "Warning: Could not parse APSS matrix from output\n"
            # Save raw output listing
            result_file = os.path.join(settings.RESULTS_DIR, "syntracker", f"{job_id}.json")
            os.makedirs(os.path.dirname(result_file), exist_ok=True)
            import json
            with open(result_file, "w") as f:
                json.dump({"samples": sample_names, "sample_ids": sample_ids,
                          "apss_matrix": [], "raw_output": result.stdout[-2000:]}, f)

        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        job.log += "SynTracker analysis complete\n"
        db.commit()

        # Cleanup work dir
        shutil.rmtree(work_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"SynTracker failed: {e}")
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                job.status = JobStatus.failed
                job.finished_at = datetime.utcnow()
                job.log = (job.log or "") + f"FAILED: {str(e)}\n"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
