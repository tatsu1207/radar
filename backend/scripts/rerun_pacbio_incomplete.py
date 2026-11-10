#!/usr/bin/env python
"""Re-queue every non-complete sample in the 'PacBio isolates' project.

Overnight run stalled at 12 complete / 12 failed / ~20 never-started (empty-stderr
failures = OOM-killed children during the 8-concurrent peak). This resets each
incomplete sample to a clean state and re-enqueues run_preprocessing:
  - deletes partial/truncated *.fastq.gz in the uploads dir (keeps the .bam
    symlink) so BAM->FASTQ re-converts from scratch (pipeline skips conversion
    if a non-empty fastq.gz already exists -> would otherwise use corrupt reads)
  - wipes results/<sample_id>/ (partial assembly/annotation)
  - deletes old AnalysisJob rows, sets status=pending, enqueues a fresh job

Usage: python rerun_pacbio_incomplete.py --dry-run | --go
"""
import argparse
import glob
import os
import shutil
import sys

from app.config import settings
from app.db import SessionLocal
from app.models.models import (
    Project, Sample, SampleStatus, AnalysisJob, JobStatus,
)

PROJECT_NAME = "PacBio isolates"
THREADS = 8  # per-job threads; worker concurrency is 4 -> up to 32 cores peak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--go", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.go):
        ap.error("pass --dry-run or --go")

    db = SessionLocal()
    p = db.query(Project).filter(Project.name == PROJECT_NAME).order_by(
        Project.created_at.desc()).first()
    if not p:
        sys.exit("project not found")

    samples = db.query(Sample).filter(Sample.project_id == p.id).all()
    incomplete = [s for s in samples if s.status != SampleStatus.complete]
    print(f"project {p.id}: {len(samples)} samples, "
          f"{len(samples) - len(incomplete)} complete, {len(incomplete)} to re-run\n")

    for s in sorted(incomplete, key=lambda x: x.name):
        print(f"  {s.name:<14} (was {str(s.status).split('.')[-1]})")

    if args.dry_run:
        print("\nDRY RUN — nothing changed.")
        db.close()
        return

    from app.core.pipeline import run_preprocessing

    print()
    from app.models.models import SampleFile, PairType
    from app.api.file_manager import _safe_filename

    for s in sorted(incomplete, key=lambda x: x.name):
        # 1) delete partial converted fastq.gz (keep the .bam symlink)
        up = os.path.join(settings.UPLOAD_DIR, str(s.id))
        for fq in glob.glob(os.path.join(up, "*.fastq.gz")) + glob.glob(os.path.join(up, "*.fq.gz")):
            os.remove(fq)
        # 1b) if conversion already rewrote file_path to the (now-deleted) fastq.gz,
        #     reset it back to the .bam symlink so BAM->FASTQ re-runs. Otherwise the
        #     pipeline skips conversion and QC/Flye open a missing file.
        for sf in db.query(SampleFile).filter(
                SampleFile.sample_id == s.id, SampleFile.pair == PairType.long_read):
            if sf.original_filename and sf.original_filename.lower().endswith(".bam"):
                bam = os.path.join(up, _safe_filename(sf.original_filename))
                if os.path.exists(bam):
                    sf.file_path, sf.file_type = bam, ".bam"
        # 2) wipe partial results
        res = os.path.join(settings.RESULTS_DIR, str(s.id))
        if os.path.isdir(res):
            shutil.rmtree(res, ignore_errors=True)
        # 3) delete old jobs, reset status
        db.query(AnalysisJob).filter(AnalysisJob.sample_id == s.id).delete()
        s.status = SampleStatus.pending
        db.commit()
        # 4) fresh job + enqueue
        job = AnalysisJob(sample_id=s.id, tool="pipeline",
                          status=JobStatus.pending, threads=THREADS)
        db.add(job)
        db.commit()
        db.refresh(job)
        res_task = run_preprocessing.delay(str(s.id), str(job.id), THREADS)
        job.celery_task_id = res_task.id
        db.commit()
        print(f"  re-queued {s.name:<14} task={res_task.id}")

    print(f"\nDone. {len(incomplete)} samples cleaned and re-enqueued (concurrency 4).")
    db.close()


if __name__ == "__main__":
    main()
