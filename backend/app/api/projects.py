import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.models import Project, Sample, User
from app.core.auth import get_current_user
from app.schemas.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectRead,
    ProjectList,
    SampleRead,
)

router = APIRouter(tags=["projects"])


def _check_project_owner(project: Project, user: User):
    """Raise 403 if user is not the project owner."""
    if project.user_id and project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your project")


@router.post("/projects", response_model=ProjectRead, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(name=payload.name, description=payload.description, user_id=current_user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=ProjectList)
def list_projects(
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    offset = (page - 1) * size
    total = db.query(Project).count()
    items = db.query(Project).order_by(Project.created_at.desc()).offset(offset).limit(size).all()
    return ProjectList(items=items, total=total, page=page, size=size)


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _check_project_owner(project, current_user)
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _check_project_owner(project, current_user)
    db.delete(project)
    db.commit()
    return None
