import os
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db import get_db
from app.models.models import Project, Sample, InputType
from app.schemas.schemas import SampleCreate, SampleRead, SampleList

router = APIRouter(tags=["samples"])


@router.post("/projects/{project_id}/samples", response_model=SampleRead, status_code=201)
def create_sample(
    project_id: uuid.UUID,
    payload: SampleCreate,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sample = Sample(
        project_id=project_id,
        name=payload.name,
        input_type=InputType(payload.input_type),
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample


@router.get("/projects/{project_id}/samples", response_model=SampleList)
def list_samples(
    project_id: uuid.UUID,
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    offset = (page - 1) * size
    query = db.query(Sample).filter(Sample.project_id == project_id)
    total = query.count()
    items = query.order_by(Sample.created_at.desc()).offset(offset).limit(size).all()
    return SampleList(items=items, total=total, page=page, size=size)


@router.get("/samples/{sample_id}", response_model=SampleRead)
def get_sample(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = (
        db.query(Sample)
        .options(joinedload(Sample.files))
        .filter(Sample.id == sample_id)
        .first()
    )
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return sample


@router.delete("/samples/{sample_id}", status_code=204)
def delete_sample(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    # Remove uploaded files from disk
    upload_dir = os.path.join(settings.UPLOAD_DIR, str(sample_id))
    if os.path.isdir(upload_dir):
        shutil.rmtree(upload_dir)

    db.delete(sample)
    db.commit()
    return None
