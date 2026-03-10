import os
import uuid
from datetime import datetime

import httpx

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models.models import (
    BVBRCFetch,
    SRADownloadStatus,
    Sample,
    SampleFile,
    PairType,
    FileSource,
    InputType,
)


@celery_app.task(name="app.core.bvbrc.fetch_bvbrc")
def fetch_bvbrc(fetch_id: str):
    db = SessionLocal()
    try:
        fetch = db.query(BVBRCFetch).filter(BVBRCFetch.id == uuid.UUID(fetch_id)).first()
        if not fetch:
            return

        # Update status to downloading
        fetch.status = SRADownloadStatus.downloading
        db.commit()

        genome_id = fetch.genome_id

        try:
            # Fetch from BV-BRC API
            url = (
                f"https://www.bv-brc.org/api/genome_sequence/"
                f"?eq(genome_id,{genome_id})&http_accept=application/dna+fasta"
            )
            response = httpx.get(url, timeout=300.0)
            response.raise_for_status()

            fasta_content = response.text
            if not fasta_content.strip():
                raise RuntimeError(f"Empty response from BV-BRC for genome {genome_id}")

            # Save FASTA file
            output_dir = os.path.join(settings.UPLOAD_DIR, str(fetch.sample_id))
            os.makedirs(output_dir, exist_ok=True)

            filename = f"{genome_id}.fasta"
            dest_path = os.path.join(output_dir, filename)

            with open(dest_path, "w") as f:
                f.write(fasta_content)

            file_size = os.path.getsize(dest_path)

            # Create SampleFile record
            sf = SampleFile(
                sample_id=fetch.sample_id,
                file_path=dest_path,
                file_type=".fasta",
                pair=PairType.assembly,
                source=FileSource.bvbrc,
                original_filename=filename,
                file_size=file_size,
            )
            db.add(sf)

            # Update sample input_type to fasta
            sample = db.query(Sample).filter(Sample.id == fetch.sample_id).first()
            if sample:
                sample.input_type = InputType.fasta

            fetch.status = SRADownloadStatus.complete
            fetch.finished_at = datetime.utcnow()
            db.commit()

        except Exception as e:
            fetch.status = SRADownloadStatus.failed
            fetch.error_message = str(e)[:2000]
            fetch.finished_at = datetime.utcnow()
            db.commit()

    finally:
        db.close()
