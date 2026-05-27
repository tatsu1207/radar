import os
import glob
import gzip
import shutil
import subprocess
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
            # Prefetch
            subprocess.run(
                ["conda", "run", "-n", "radar", "prefetch", accession],
                check=True,
                capture_output=True,
                text=True,
                timeout=3600,
            )

            dl.progress = 50.0
            db.commit()

            # Fasterq-dump
            subprocess.run(
                [
                    "conda", "run", "-n", "radar",
                    "fasterq-dump", accession,
                    "--outdir", output_dir,
                    "--split-files",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=7200,
            )

            dl.progress = 80.0
            db.commit()

            # Compress output fastq files with gzip
            fastq_files = sorted(glob.glob(os.path.join(output_dir, f"{accession}*.fastq")))
            for fq in fastq_files:
                gz_path = fq + ".gz"
                with open(fq, "rb") as f_in:
                    with gzip.open(gz_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(fq)

            # Find compressed files
            gz_files = sorted(glob.glob(os.path.join(output_dir, f"{accession}*.fastq.gz")))

            if len(gz_files) == 0:
                raise RuntimeError("No output files produced by fasterq-dump")

            # Auto-detect paired vs single
            if len(gz_files) >= 2:
                # Paired-end
                for i, gz_file in enumerate(gz_files[:2]):
                    pair = PairType.R1 if i == 0 else PairType.R2
                    file_size = os.path.getsize(gz_file)
                    sf = SampleFile(
                        sample_id=dl.sample_id,
                        file_path=gz_file,
                        file_type=".fastq.gz",
                        pair=pair,
                        platform=SequencingPlatform.illumina,
                        source=FileSource.sra,
                        original_filename=os.path.basename(gz_file),
                        file_size=file_size,
                    )
                    db.add(sf)
            else:
                # Single-end
                gz_file = gz_files[0]
                file_size = os.path.getsize(gz_file)
                sf = SampleFile(
                    sample_id=dl.sample_id,
                    file_path=gz_file,
                    file_type=".fastq.gz",
                    pair=PairType.single,
                    platform=SequencingPlatform.illumina,
                    source=FileSource.sra,
                    original_filename=os.path.basename(gz_file),
                    file_size=file_size,
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
