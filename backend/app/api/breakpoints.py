"""Editable AST breakpoints: CRUD + MIC->S/I/R interpretation."""
import io
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.auth import get_current_user
from app.models.models import Breakpoint, User
from app.core.breakpoints import select_breakpoint, interpret, _sample_taxa
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
    standard: Optional[str] = None,
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
    if standard:
        q = q.filter(func.lower(Breakpoint.standard) == standard.strip().lower())
    return q.order_by(Breakpoint.organism, Breakpoint.subclass, Breakpoint.antibiotic).all()


@router.get("/breakpoints/standards")
def list_standards(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Distinct guideline standards with their row counts — drives the standard selector."""
    rows = (
        db.query(Breakpoint.standard, func.count(Breakpoint.id))
        .group_by(Breakpoint.standard)
        .all()
    )
    return [{"standard": s or "unknown", "count": n} for s, n in sorted(rows, key=lambda r: -r[1])]


@router.get("/breakpoints/organisms")
def list_organisms(
    standard: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Distinct organisms with their hosts and antibiotic panels — drives the AST dropdowns."""
    q = db.query(Breakpoint)
    if standard:
        q = q.filter(func.lower(Breakpoint.standard) == standard.strip().lower())
    out = {}
    for b in q.order_by(Breakpoint.organism, Breakpoint.antibiotic).all():
        o = out.setdefault(b.organism, {"organism": b.organism, "hosts": set(), "antibiotics": []})
        if b.host:
            o["hosts"].add(b.host)
        entry = {"antibiotic": b.antibiotic, "abbreviation": b.abbreviation, "subclass": b.subclass}
        if entry not in o["antibiotics"]:
            o["antibiotics"].append(entry)
    return [{**o, "hosts": sorted(o["hosts"])} for o in out.values()]


@router.get("/breakpoints/resolve")
def resolve_organism(
    organism: str,
    standard: Optional[str] = None,
    host: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Which breakpoint-panel taxon best covers a sample species, climbing its lineage
    (species -> genus -> family -> order). Lets the AST panel preselect the right panel
    for e.g. 'Escherichia coli' even when the breakpoints live under 'Enterobacterales'."""
    org = organism.strip().lower()
    taxa = {name: spec for spec, name in _sample_taxa(organism)}
    q = db.query(Breakpoint.organism).distinct()
    if standard:
        q = q.filter(func.lower(Breakpoint.standard) == standard.strip().lower())
    best_name, best_spec = None, 0
    for (name,) in q.all():
        bo = (name or "").strip().lower()
        if not bo:
            continue
        spec = 4 if (org == bo or org.startswith(bo) or bo.startswith(org)) else taxa.get(bo, 0)
        if spec > best_spec:
            best_name, best_spec = name, spec
    return {"organism": best_name}


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
    bp = select_breakpoint(db, payload.organism, payload.antibiotic, payload.host, payload.standard)
    sir = interpret(bp, payload.mic)
    return InterpretResponse(
        sir=sir,
        breakpoint_id=bp.id if bp else None,
        susceptible_max=bp.susceptible_max if bp else None,
        resistant_min=bp.resistant_min if bp else None,
        matched_organism=bp.organism if bp else None,
        matched_host=bp.host if bp else None,
        matched_standard=bp.standard if bp else None,
    )


# columns accepted in an import file; header match is case-insensitive
_TEXT_COLS = ("standard", "organism", "host", "antibiotic", "abbreviation", "subclass", "unit", "source", "notes")
_NUM_COLS = ("susceptible_max", "intermediate_min", "resistant_min")
# friendly header aliases -> canonical column
_ALIASES = {
    "s": "susceptible_max", "s<=": "susceptible_max", "s_max": "susceptible_max",
    "susceptible": "susceptible_max", "breakpoint_s": "susceptible_max",
    "i": "intermediate_min", "i>=": "intermediate_min", "i_min": "intermediate_min",
    "intermediate": "intermediate_min",
    "r": "resistant_min", "r>=": "resistant_min", "r_min": "resistant_min",
    "resistant": "resistant_min", "breakpoint_r": "resistant_min",
    "guideline": "standard", "drug": "antibiotic", "antimicrobial": "antibiotic",
    "species": "organism", "mo": "organism", "abbrev": "abbreviation", "class": "subclass",
}


@router.post("/breakpoints/import", status_code=200)
async def import_breakpoints(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk-load breakpoints from a CSV/TSV/Excel file.

    Columns (case-insensitive, friendly aliases accepted): organism and antibiotic are
    required; standard, host, abbreviation, subclass, unit, source, notes, and the
    cutoffs susceptible_max / intermediate_min / resistant_min (a.k.a. S / I / R) are
    optional. Rows upsert on (standard, organism, host, antibiotic) so re-importing
    updates in place rather than duplicating. standard defaults to 'custom'."""
    content = await file.read()
    filename = (file.filename or "").lower()

    import pandas as pd

    try:
        if filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            df = pd.read_csv(io.BytesIO(content), sep="\t")
            if len(df.columns) <= 1:
                df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")

    # map each file column to a canonical name
    colmap = {}
    for c in df.columns:
        key = str(c).strip().lower()
        canon = key if key in (_TEXT_COLS + _NUM_COLS) else _ALIASES.get(key)
        if canon:
            colmap[c] = canon
    canon_cols = set(colmap.values())
    if "organism" not in canon_cols or "antibiotic" not in canon_cols:
        raise HTTPException(
            status_code=400,
            detail=f"File must have 'organism' and 'antibiotic' columns. Found: {list(df.columns)}",
        )

    def cell(row, canon):
        for src, dst in colmap.items():
            if dst == canon:
                v = row[src]
                return None if pd.isna(v) else v
        return None

    def as_text(v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    def as_num(v):
        if v is None:
            return None
        try:
            return float(str(v).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    created = updated = skipped = 0
    errors: List[str] = []

    for i, row in df.iterrows():
        organism = as_text(cell(row, "organism"))
        antibiotic = as_text(cell(row, "antibiotic"))
        if not organism or not antibiotic:
            skipped += 1
            continue
        fields = {c: as_text(cell(row, c)) for c in _TEXT_COLS}
        fields.update({c: as_num(cell(row, c)) for c in _NUM_COLS})
        fields["organism"] = organism
        fields["antibiotic"] = antibiotic
        fields["standard"] = fields.get("standard") or "custom"
        fields["unit"] = fields.get("unit") or "µg/mL"
        if fields["susceptible_max"] is None and fields["intermediate_min"] is None \
                and fields["resistant_min"] is None:
            errors.append(f"row {int(i) + 2}: no S/I/R cutoff, skipped")
            skipped += 1
            continue

        existing = db.query(Breakpoint).filter(
            func.lower(Breakpoint.standard) == fields["standard"].lower(),
            func.lower(Breakpoint.organism) == organism.lower(),
            func.lower(Breakpoint.antibiotic) == antibiotic.lower(),
            func.coalesce(func.lower(Breakpoint.host), "") == (fields.get("host") or "").lower(),
        ).first()
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(Breakpoint(**fields))
            created += 1

    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}
