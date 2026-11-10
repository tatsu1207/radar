"""Editable AST breakpoints: CRUD + MIC->S/I/R interpretation."""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.auth import get_current_user
from app.models.models import Breakpoint, User
from app.core.breakpoints import select_breakpoint, interpret
from app.schemas.schemas import (
    BreakpointCreate,
    BreakpointUpdate,
    BreakpointRead,
    InterpretRequest,
    InterpretResponse,
)

router = APIRouter(tags=["breakpoints"])


@router.get("/breakpoints", response_model=List[BreakpointRead])
def list_breakpoints(
    organism: Optional[str] = None,
    host: Optional[str] = None,
    antibiotic: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Breakpoint)
    if organism:
        q = q.filter(func.lower(Breakpoint.organism) == organism.strip().lower())
    if host:
        q = q.filter(func.lower(Breakpoint.host) == host.strip().lower())
    if antibiotic:
        q = q.filter(func.lower(Breakpoint.antibiotic) == antibiotic.strip().lower())
    return q.order_by(Breakpoint.organism, Breakpoint.subclass, Breakpoint.antibiotic).all()


@router.get("/breakpoints/organisms")
def list_organisms(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Distinct organisms with their hosts and antibiotic panels — drives the AST dropdowns."""
    out = {}
    for b in db.query(Breakpoint).order_by(Breakpoint.organism, Breakpoint.antibiotic).all():
        o = out.setdefault(b.organism, {"organism": b.organism, "hosts": set(), "antibiotics": []})
        if b.host:
            o["hosts"].add(b.host)
        entry = {"antibiotic": b.antibiotic, "abbreviation": b.abbreviation, "subclass": b.subclass}
        if entry not in o["antibiotics"]:
            o["antibiotics"].append(entry)
    return [{**o, "hosts": sorted(o["hosts"])} for o in out.values()]


@router.post("/breakpoints", response_model=BreakpointRead, status_code=201)
def create_breakpoint(payload: BreakpointCreate, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    bp = Breakpoint(**payload.model_dump())
    db.add(bp)
    db.commit()
    db.refresh(bp)
    return bp


@router.put("/breakpoints/{bp_id}", response_model=BreakpointRead)
def update_breakpoint(bp_id: uuid.UUID, payload: BreakpointUpdate, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    bp = db.query(Breakpoint).filter(Breakpoint.id == bp_id).first()
    if not bp:
        raise HTTPException(status_code=404, detail="Breakpoint not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(bp, k, v)
    db.commit()
    db.refresh(bp)
    return bp


@router.delete("/breakpoints/{bp_id}", status_code=204)
def delete_breakpoint(bp_id: uuid.UUID, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    bp = db.query(Breakpoint).filter(Breakpoint.id == bp_id).first()
    if not bp:
        raise HTTPException(status_code=404, detail="Breakpoint not found")
    db.delete(bp)
    db.commit()


@router.post("/breakpoints/interpret", response_model=InterpretResponse)
def interpret_endpoint(payload: InterpretRequest, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    bp = select_breakpoint(db, payload.organism, payload.antibiotic, payload.host)
    sir = interpret(bp, payload.mic)
    return InterpretResponse(
        sir=sir,
        breakpoint_id=bp.id if bp else None,
        resistant_min=bp.resistant_min if bp else None,
        matched_organism=bp.organism if bp else None,
        matched_host=bp.host if bp else None,
    )
