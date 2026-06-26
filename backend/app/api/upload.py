import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.models import Sample, SampleFile, PairType, User
from app.core.auth import get_current_user
from app.core.ownership import require_sample_owner
from app.schemas.schemas import FileUploadResponse, SampleFileRead

router = APIRouter(tags=["upload"])


def _validate_extension(filename: str) -> bool:
    lower = filename.lower()
    for ext in settings.ALLOWED_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return False


def _detect_pair(filename: str) -> PairType:
    lower = filename.lower()
    if "_r1" in lower or "_1.fastq" in lower or "_1.fq" in lower:
        return PairType.R1
    elif "_r2" in lower or "_2.fastq" in lower or "_2.fq" in lower:
        return PairType.R2
    elif lower.endswith((".fasta", ".fa", ".fna")):
        return PairType.assembly
    return PairType.single


@router.post("/samples/{sample_id}/upload", response_model=FileUploadResponse)
async def upload_files(
    sample_id: uuid.UUID,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sample = require_sample_owner(sample_id, current_user, db)

    upload_dir = os.path.join(settings.UPLOAD_DIR, str(sample_id))
    os.makedirs(upload_dir, exist_ok=True)

    created_files: List[SampleFile] = []

    for upload_file in files:
        if not upload_file.filename:
            raise HTTPException(status_code=400, detail="File must have a filename")

        if not _validate_extension(upload_file.filename):
            raise HTTPException(
                status_code=400,
                detail=f"File extension not allowed for '{upload_file.filename}'. "
                       f"Allowed: {settings.ALLOWED_EXTENSIONS}",
            )

        dest_path = os.path.join(upload_dir, upload_file.filename)
        content = await upload_file.read()

        if len(content) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File exceeds maximum upload size")

        with open(dest_path, "wb") as f:
            f.write(content)

        pair = _detect_pair(upload_file.filename)
        ext = os.path.splitext(upload_file.filename)[1]
        if upload_file.filename.endswith(".gz"):
            ext = os.path.splitext(upload_file.filename[:-3])[1] + ".gz"

        sf = SampleFile(
            sample_id=sample_id,
            file_path=dest_path,
            file_type=ext,
            pair=pair,
        )
        db.add(sf)
        created_files.append(sf)

    db.commit()
    for sf in created_files:
        db.refresh(sf)

    return FileUploadResponse(
        sample_id=sample_id,
        files=[SampleFileRead.model_validate(sf) for sf in created_files],
        message=f"Successfully uploaded {len(created_files)} file(s)",
    )
