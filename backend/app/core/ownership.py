"""Helpers for checking project/sample ownership."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import Project, Sample, User


def require_project_owner(project_id, user: User, db: Session) -> Project:
    """Get project and verify the user owns it. Raises 403/404."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.user_id and project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your project")
    return project


def require_sample_owner(sample_id, user: User, db: Session) -> Sample:
    """Get sample and verify the user owns its project. Raises 403/404."""
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    project = db.query(Project).filter(Project.id == sample.project_id).first()
    if project and project.user_id and project.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your project")
    return sample
