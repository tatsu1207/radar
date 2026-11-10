#!/usr/bin/env python
"""Seed the 45 PacBio HiFi BAMs into RADAR and enqueue the full pipeline.

Registers each BAM as a long_read/pacbio SampleFile (symlinked into the uploads
dir; the pipeline converts BAM->FASTQ and re-confirms platform from the @RG
header), attaches placeholder metadata, and dispatches run_preprocessing on the
'pipeline' Celery queue.

Usage:
    python seed_pacbio_batch.py --dry-run     # show the plan, touch nothing
    python seed_pacbio_batch.py --go          # create rows, symlink, enqueue
"""
import argparse
import os
import sys
from datetime import datetime

from app.config import settings
from app.db import SessionLocal
from app.models.models import (
    User, Project, Sample, SampleFile, Metadata,
    InputType, SampleStatus, PairType, SequencingPlatform, FileSource,
    AnalysisJob, JobStatus,
)
from app.api.file_manager import _safe_filename

BAM_DIR = "/data/E/NGS_data/NGS_projects/RADAR 업로드/RADAR 업로드 파일_Pacbio"
OWNER_USERNAME = "b4_2"
PROJECT_NAME = "PacBio isolates"
THREADS = 8

META = dict(
    host="swine",
    location="Cheongju",
    collection_date=datetime(2025, 2, 2),
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--go", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.go):
        ap.error("pass --dry-run or --go")

    bams = sorted(f for f in os.listdir(BAM_DIR) if f.lower().endswith(".bam"))
    print(f"Found {len(bams)} BAM files in:\n  {BAM_DIR}\n")

    db = SessionLocal()
    owner = db.query(User).filter(User.username == OWNER_USERNAME).first()
    if not owner:
        sys.exit(f"User {OWNER_USERNAME!r} not found")

    existing = db.query(Project).filter(
        Project.name == PROJECT_NAME, Project.user_id == owner.id
    ).first()
    if existing:
        sys.exit(f"Project {PROJECT_NAME!r} already exists for {OWNER_USERNAME} "
                 f"(id={existing.id}); refusing to duplicate.")

    print(f"Owner:   {owner.username} ({owner.id})")
    print(f"Project: {PROJECT_NAME} (new)")
    print(f"Metadata: host={META['host']} location={META['location']} "
          f"date={META['collection_date'].date()}")
    print(f"Threads/job: {THREADS}\n")

    if args.dry_run:
        for b in bams:
            name = b[:-4]
            size = os.path.getsize(os.path.join(BAM_DIR, b))
            print(f"  {name:<16} <- {b}  ({size/1e9:.1f} GB)")
        print(f"\nDRY RUN — nothing created. {len(bams)} samples would be seeded.")
        db.close()
        return

    # --- real run ---
    project = Project(user_id=owner.id, name=PROJECT_NAME,
                      description="PacBio HiFi batch (Revio), seeded from BAM.")
    db.add(project)
    db.commit()
    db.refresh(project)
    print(f"Created project {project.id}\n")

    from app.core.pipeline import run_preprocessing

    seeded = []
    for b in bams:
        name = b[:-4]
        src = os.path.abspath(os.path.join(BAM_DIR, b))

        sample = Sample(project_id=project.id, name=name,
                        input_type=InputType.fastq, status=SampleStatus.pending)
        db.add(sample)
        db.commit()
        db.refresh(sample)

        upload_dir = os.path.join(settings.UPLOAD_DIR, str(sample.id))
        os.makedirs(upload_dir, exist_ok=True)
        dest = os.path.join(upload_dir, _safe_filename(b))
        if not os.path.exists(dest):
            os.symlink(src, dest)

        sf = SampleFile(
            sample_id=sample.id, file_path=dest, file_type=".bam",
            pair=PairType.long_read, platform=SequencingPlatform.pacbio,
            source=FileSource.upload, original_filename=b,
            file_size=os.path.getsize(src),
        )
        db.add(sf)

        md = Metadata(sample_id=sample.id, host=META["host"],
                      location=META["location"],
                      collection_date=META["collection_date"])
        db.add(md)
        db.commit()

        job = AnalysisJob(sample_id=sample.id, tool="pipeline",
                          status=JobStatus.pending, threads=THREADS)
        db.add(job)
        db.commit()
        db.refresh(job)

        res = run_preprocessing.delay(str(sample.id), str(job.id), THREADS)
        job.celery_task_id = res.id
        db.commit()
        seeded.append((name, sample.id, res.id))
        print(f"  queued {name:<16} sample={sample.id} task={res.id}")

    print(f"\nDone. {len(seeded)} samples seeded and enqueued on the 'pipeline' queue "
          f"(concurrency 4).")
    print(f"Project id: {project.id}")
    db.close()


if __name__ == "__main__":
    main()
