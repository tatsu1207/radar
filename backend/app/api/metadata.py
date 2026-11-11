import io
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models.models import Sample, Metadata, ASTResult, SIR, Project, User
from app.core.auth import get_current_user
from app.core.ownership import require_sample_owner, require_project_owner
from app.schemas.schemas import (
    MetadataCreate,
    MetadataRead,
    MetadataUpdate,
    ASTResultCreate,
    ASTResultRead,
    ASTResultUpdate,
)

router = APIRouter(tags=["metadata"])


@router.put("/samples/{sample_id}/metadata", response_model=MetadataRead)
def upsert_metadata(
    sample_id: uuid.UUID,
    payload: MetadataCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sample = require_sample_owner(sample_id, current_user, db)

    meta = db.query(Metadata).filter(Metadata.sample_id == sample_id).first()
    if meta:
        if payload.source is not None:
            meta.source = payload.source
        if payload.collection_date is not None:
            meta.collection_date = payload.collection_date
        if payload.location is not None:
            meta.location = payload.location
        if getattr(payload, 'host', None) is not None:
            meta.host = payload.host
        if payload.species is not None:
            meta.species = payload.species
        if payload.custom_json is not None:
            meta.custom_json = payload.custom_json
    else:
        meta = Metadata(
            sample_id=sample_id,
            source=payload.source,
            collection_date=payload.collection_date,
            location=payload.location,
            host=getattr(payload, 'host', None),
            species=payload.species,
            custom_json=payload.custom_json,
        )
        db.add(meta)

    db.commit()
    db.refresh(meta)
    return meta


@router.get("/samples/{sample_id}/metadata", response_model=MetadataRead)
def get_metadata(sample_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    meta = db.query(Metadata).filter(Metadata.sample_id == sample_id).first()
    if not meta:
        raise HTTPException(status_code=404, detail="Metadata not found for this sample")
    return meta


def _resolve_organism_host(sample_id: uuid.UUID, db: Session):
    """Best-effort (organism, host) for a sample, for breakpoint auto-interpretation.
    organism: pipeline species (skani) else user metadata species.
    host: metadata animal host mapped to dog/cat/livestock."""
    from app.models.models import SpeciesResult
    organism = host = None
    sr = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    if sr and sr.species:
        organism = sr.species
    meta = db.query(Metadata).filter(Metadata.sample_id == sample_id).first()
    if meta:
        organism = organism or meta.species
        h = (meta.host or "").lower()
        if "dog" in h or "개" in h or "canine" in h:
            host = "dog"
        elif "cat" in h or "고양이" in h or "feline" in h:
            host = "cat"
        elif any(k in h for k in ("cattle", "cow", "bovine", "pig", "swine", "porcine",
                                  "chicken", "poultry", "duck", "소", "돼지", "닭", "오리")):
            host = "livestock"
    return organism, host


@router.post("/samples/{sample_id}/ast", response_model=ASTResultRead, status_code=201)
def add_ast_result(
    sample_id: uuid.UUID,
    payload: ASTResultCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sample = require_sample_owner(sample_id, current_user, db)

    sir = payload.sir
    # auto-interpret from MIC + editable breakpoints when SIR wasn't supplied
    if not sir and payload.mic:
        from app.core.breakpoints import interpret_mic
        organism = payload.organism
        host = payload.host
        if not organism:
            organism, auto_host = _resolve_organism_host(sample_id, db)
            host = host or auto_host
        sir, _bp = interpret_mic(db, organism or "", payload.antibiotic, payload.mic, host)
    if not sir:
        raise HTTPException(
            status_code=422,
            detail="Could not determine S/I/R: provide 'sir' explicitly, or a MIC with a "
                   "matching breakpoint for the sample's organism.",
        )

    ast = ASTResult(
        sample_id=sample_id,
        antibiotic=payload.antibiotic,
        method=payload.method,
        mic=payload.mic,
        sir=SIR(sir),
    )
    db.add(ast)
    db.commit()
    db.refresh(ast)
    return ast


@router.get("/samples/{sample_id}/ast", response_model=List[ASTResultRead])
def list_ast_results(sample_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return db.query(ASTResult).filter(ASTResult.sample_id == sample_id).all()


@router.put("/samples/{sample_id}/ast/{ast_id}", response_model=ASTResultRead)
def update_ast_result(
    sample_id: uuid.UUID,
    ast_id: uuid.UUID,
    payload: ASTResultUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_sample_owner(sample_id, current_user, db)
    ast = db.query(ASTResult).filter(ASTResult.id == ast_id, ASTResult.sample_id == sample_id).first()
    if not ast:
        raise HTTPException(status_code=404, detail="AST result not found")
    if payload.antibiotic is not None:
        ast.antibiotic = payload.antibiotic
    if payload.method is not None:
        ast.method = payload.method
    if payload.mic is not None:
        ast.mic = payload.mic
    if payload.sir is not None:
        ast.sir = SIR(payload.sir)
    db.commit()
    db.refresh(ast)
    return ast


@router.delete("/samples/{sample_id}/ast/{ast_id}", status_code=204)
def delete_ast_result(
    sample_id: uuid.UUID,
    ast_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_sample_owner(sample_id, current_user, db)
    ast = db.query(ASTResult).filter(ASTResult.id == ast_id, ASTResult.sample_id == sample_id).first()
    if not ast:
        raise HTTPException(status_code=404, detail="AST result not found")
    db.delete(ast)
    db.commit()


def _parse_sir(value) -> str | None:
    """Normalize a cell to S/I/R, accepting full words. Returns None if blank/invalid."""
    import pandas as _pd
    if value is None or (isinstance(value, float) and _pd.isna(value)):
        return None
    v = str(value).strip().upper()
    if v in ("", "NA", "N/A", "-", "ND"):
        return None
    if v in ("S", "I", "R"):
        return v
    if v.startswith("SUSCEPT"):
        return "S"
    if v.startswith("INTERMED"):
        return "I"
    if v.startswith("RESIST"):
        return "R"
    return None  # unrecognized


@router.post("/ast/upload", status_code=200)
async def bulk_upload_ast(
    file: UploadFile = File(...),
    standard: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk-import AST (phenotype) results from CSV/TSV/Excel.

    First column must be SAMPLE (matches sample name). Two layouts are accepted:
      - LONG: columns SAMPLE, antibiotic, [method], [mic], [sir]
      - WIDE: SAMPLE + one column per antibiotic, each cell = S/I/R

    `standard` controls how S/I/R is derived for LONG rows that carry a MIC:
      - EUCAST / CLSI: interpret the MIC against that guideline's breakpoints for the
        sample's species (auto-fill S/I/R; a value in the file's sir column is ignored).
      - self-defined: use the file's sir if given, otherwise interpret the MIC against
        the user's own 'custom' breakpoints.
      - unset: use the file's sir as-is (no interpretation).
    WIDE cells are always taken as-is. Existing (sample, antibiotic) rows upsert."""
    import pandas as pd
    from app.core.breakpoints import interpret_mic

    std = (standard or "").strip().lower()
    guideline = {"eucast": "EUCAST", "clsi": "CLSI",
                 "self": "custom", "self-defined": "custom", "self defined": "custom",
                 "custom": "custom"}.get(std)

    content = await file.read()
    filename = file.filename or ""
    try:
        if filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            df = pd.read_csv(io.BytesIO(content), sep="\t")
            if len(df.columns) <= 1:
                df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {str(e)}")

    col_map = {c.lower().strip(): c for c in df.columns}
    sample_col = col_map.get("sample") or col_map.get("sample_name") or col_map.get("sample_id")
    if not sample_col:
        raise HTTPException(status_code=400, detail=f"File must contain a 'SAMPLE' column. Found: {list(df.columns)}")

    is_long = "antibiotic" in col_map
    meta_cols = {sample_col.lower(), "sample", "sample_name", "sample_id", "antibiotic", "method", "mic", "sir"}

    org_cache: dict = {}

    def organism_host(sample):
        if sample.id not in org_cache:
            org_cache[sample.id] = _resolve_organism_host(sample.id, db)
        return org_cache[sample.id]

    def upsert(sample, antibiotic, sir, method=None, mic=None):
        antibiotic = str(antibiotic).strip()
        existing = db.query(ASTResult).filter(
            ASTResult.sample_id == sample.id, ASTResult.antibiotic.ilike(antibiotic)
        ).first()
        if existing:
            existing.sir = SIR(sir)
            if method is not None:
                existing.method = method
            if mic is not None:
                existing.mic = mic
        else:
            db.add(ASTResult(sample_id=sample.id, antibiotic=antibiotic, method=method, mic=mic, sir=SIR(sir)))

    imported, skipped, auto_interpreted, errors = 0, 0, 0, []
    samples_seen = set()
    for _, row in df.iterrows():
        sample_name = str(row[sample_col]).strip()
        if not sample_name or sample_name.lower() == "nan":
            continue
        sample = db.query(Sample).filter(Sample.name == sample_name).first()
        if not sample:
            errors.append(f"Sample '{sample_name}' not found")
            continue
        samples_seen.add(sample_name)

        if is_long:
            file_sir = _parse_sir(row.get(col_map.get("sir", "sir")))
            abx = row.get(col_map["antibiotic"])
            if abx is None or str(abx).strip().lower() in ("", "nan"):
                continue
            method = row.get(col_map["method"]) if "method" in col_map else None
            mic = row.get(col_map["mic"]) if "mic" in col_map else None
            method = None if (method is None or pd.isna(method)) else str(method).strip()
            mic = None if (mic is None or pd.isna(mic)) else str(mic).strip()

            # derive S/I/R per the selected standard
            computed = None
            if guideline and mic:
                organism, host = organism_host(sample)
                if organism:
                    computed, _bp = interpret_mic(db, organism, str(abx).strip(), mic, host, guideline)
            if guideline in ("EUCAST", "CLSI"):
                sir = computed or file_sir            # guideline wins; fall back to file
            elif guideline == "custom":
                sir = file_sir or computed            # user's own call wins; else custom cutoffs
            else:
                sir = file_sir
            if computed and sir == computed:
                auto_interpreted += 1

            if sir is None:
                reason = "no breakpoint for MIC" if (guideline and mic) else "no S/I/R"
                errors.append(f"{sample_name}/{str(abx).strip()}: {reason}")
                skipped += 1
                continue
            upsert(sample, abx, sir, method, mic)
            imported += 1
        else:
            for col in df.columns:
                if col.lower().strip() in meta_cols:
                    continue
                sir = _parse_sir(row[col])
                if sir is None:
                    continue  # blank cell = not tested
                upsert(sample, col, sir)
                imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "samples": len(samples_seen),
            "auto_interpreted": auto_interpreted, "standard": guideline, "errors": errors[:50]}


@router.get("/ast/all")
def list_all_ast(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """All AST results across samples, with sample name (for the AST page)."""
    rows = (
        db.query(ASTResult, Sample.name)
        .join(Sample, ASTResult.sample_id == Sample.id)
        .order_by(Sample.name, ASTResult.antibiotic)
        .all()
    )
    return [
        {
            "id": str(a.id),
            "sample_id": str(a.sample_id),
            "sample_name": name,
            "antibiotic": a.antibiotic,
            "method": a.method,
            "mic": a.mic,
            "sir": a.sir.value if hasattr(a.sir, "value") else a.sir,
        }
        for a, name in rows
    ]


@router.post("/projects/{project_id}/metadata/import", status_code=200)
async def bulk_import_metadata(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_owner(project_id, current_user, db)

    content = await file.read()
    filename = file.filename or ""

    import pandas as pd

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
        else:
            df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {str(e)}")

    # Accept either "SAMPLE" or "sample_name" as the first column
    col_lower_map = {c.lower(): c for c in df.columns}
    if "sample" in col_lower_map:
        sample_col = col_lower_map["sample"]
    elif "sample_name" in col_lower_map:
        sample_col = col_lower_map["sample_name"]
    else:
        raise HTTPException(
            status_code=400,
            detail=f"File must contain a 'SAMPLE' column. Found: {list(df.columns)}",
        )

    updated = 0
    created = 0
    errors = []

    for _, row in df.iterrows():
        sample_name = str(row[sample_col]).strip()
        sample = (
            db.query(Sample)
            .filter(Sample.project_id == project_id, Sample.name == sample_name)
            .first()
        )
        if not sample:
            errors.append(f"Sample '{sample_name}' not found in project")
            continue

        meta = db.query(Metadata).filter(Metadata.sample_id == sample.id).first()

        source = row.get("source") if "source" in df.columns else None
        collection_date = row.get("collection_date") if "collection_date" in df.columns else None
        location = row.get("location") if "location" in df.columns else None
        species = row.get("species") if "species" in df.columns else None

        # Handle NaN values from pandas
        if pd.isna(source):
            source = None
        if pd.isna(location):
            location = None
        if pd.isna(species):
            species = None
        if collection_date is not None and pd.isna(collection_date):
            collection_date = None

        # Collect extra columns into custom_json
        known_cols = {sample_col, "sample_name", "sample", "source", "collection_date", "location", "species"}
        extra = {
            col: (None if pd.isna(row[col]) else row[col])
            for col in df.columns
            if col not in known_cols
        }
        # Convert numpy types to native Python types for JSON serialization
        for k, v in extra.items():
            if hasattr(v, "item"):
                extra[k] = v.item()

        custom_json = extra if extra else None

        if meta:
            if source is not None:
                meta.source = str(source)
            if collection_date is not None:
                meta.collection_date = pd.to_datetime(collection_date)
            if location is not None:
                meta.location = str(location)
            if species is not None:
                meta.species = str(species)
            if custom_json:
                meta.custom_json = custom_json
            updated += 1
        else:
            meta = Metadata(
                sample_id=sample.id,
                source=str(source) if source else None,
                collection_date=pd.to_datetime(collection_date) if collection_date else None,
                location=str(location) if location else None,
                species=str(species) if species else None,
                custom_json=custom_json,
            )
            db.add(meta)
            created += 1

    db.commit()

    return {
        "created": created,
        "updated": updated,
        "errors": errors,
    }


@router.post("/metadata/upload", status_code=200)
async def global_upload_metadata(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload metadata TSV globally. First column must be SAMPLE (matches sample name across all projects)."""
    content = await file.read()
    filename = file.filename or ""

    import pandas as pd

    try:
        if filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
        else:
            # Try TSV first, fall back to CSV
            try:
                df = pd.read_csv(io.BytesIO(content), sep="\t")
                if len(df.columns) <= 1:
                    df = pd.read_csv(io.BytesIO(content))
            except Exception:
                df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {str(e)}")

    # Accept either "SAMPLE" or "sample_name" as the first column
    col_lower_map = {c.lower(): c for c in df.columns}
    if "sample" in col_lower_map:
        sample_col = col_lower_map["sample"]
    elif "sample_name" in col_lower_map:
        sample_col = col_lower_map["sample_name"]
    else:
        raise HTTPException(
            status_code=400,
            detail=f"File must contain a 'SAMPLE' column. Found: {list(df.columns)}",
        )

    updated = 0
    created = 0
    errors = []

    for _, row in df.iterrows():
        sample_name = str(row[sample_col]).strip()
        sample = db.query(Sample).filter(Sample.name == sample_name).first()
        if not sample:
            errors.append(f"Sample '{sample_name}' not found")
            continue

        meta = db.query(Metadata).filter(Metadata.sample_id == sample.id).first()

        source_val = row.get("source") if "source" in df.columns else None
        collection_date = row.get("collection_date") if "collection_date" in df.columns else None
        location = row.get("location") if "location" in df.columns else None

        import pandas as _pd
        if source_val is not None and _pd.isna(source_val):
            source_val = None
        if location is not None and _pd.isna(location):
            location = None
        if collection_date is not None and _pd.isna(collection_date):
            collection_date = None

        known_cols = {sample_col, "sample_name", "sample", "source", "collection_date", "location"}
        extra = {
            col: (None if _pd.isna(row[col]) else row[col])
            for col in df.columns
            if col.lower() not in {k.lower() for k in known_cols}
        }
        for k, v in extra.items():
            if hasattr(v, "item"):
                extra[k] = v.item()
        custom_json = extra if extra else None

        if meta:
            if source_val is not None:
                meta.source = str(source_val)
            if collection_date is not None:
                meta.collection_date = _pd.to_datetime(collection_date)
            if location is not None:
                meta.location = str(location)
            if custom_json:
                existing = meta.custom_json or {}
                existing.update(custom_json)
                meta.custom_json = existing
            updated += 1
        else:
            meta = Metadata(
                sample_id=sample.id,
                source=str(source_val) if source_val else None,
                collection_date=_pd.to_datetime(collection_date) if collection_date else None,
                location=str(location) if location else None,
                custom_json=custom_json,
            )
            db.add(meta)
            created += 1

    db.commit()

    return {"created": created, "updated": updated, "errors": errors}


@router.get("/metadata/all")
def list_all_metadata(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Return all samples with their metadata (if any)."""
    samples = (
        db.query(Sample)
        .options(joinedload(Sample.metadata_record))
        .order_by(Sample.name)
        .all()
    )

    rows = []
    all_custom_keys: list[str] = []

    # First pass: collect all custom_json keys
    for s in samples:
        meta = s.metadata_record
        if meta and meta.custom_json:
            for k in meta.custom_json:
                if k not in all_custom_keys:
                    all_custom_keys.append(k)

    # Second pass: build rows
    for s in samples:
        meta = s.metadata_record
        row: dict = {
            "sample_id": str(s.id),
            "sample_name": s.name,
            "host": getattr(meta, 'host', None) if meta else None,
            "source": meta.source if meta else None,
            "collection_date": (
                meta.collection_date.strftime("%Y-%m-%d") if meta and meta.collection_date else None
            ),
            "location": meta.location if meta else None,
        }
        # Add custom fields
        for k in all_custom_keys:
            row[k] = meta.custom_json.get(k) if meta and meta.custom_json else None
        rows.append(row)

    return {"rows": rows, "custom_columns": all_custom_keys}


@router.get("/metadata/download")
def download_metadata_tsv(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Download all sample metadata as a TSV file."""
    samples = (
        db.query(Sample)
        .options(joinedload(Sample.metadata_record))
        .order_by(Sample.name)
        .all()
    )

    # Collect all custom keys
    all_custom_keys: list[str] = []
    for s in samples:
        meta = s.metadata_record
        if meta and meta.custom_json:
            for k in meta.custom_json:
                if k not in all_custom_keys:
                    all_custom_keys.append(k)

    # Build TSV
    columns = ["SAMPLE", "source", "collection_date", "location"] + all_custom_keys
    lines = ["\t".join(columns)]

    for s in samples:
        meta = s.metadata_record
        vals = [
            s.name,
            meta.source or "" if meta else "",
            meta.collection_date.strftime("%Y-%m-%d") if meta and meta.collection_date else "",
            meta.location or "" if meta else "",
        ]
        for k in all_custom_keys:
            v = meta.custom_json.get(k) if meta and meta.custom_json else None
            vals.append(str(v) if v is not None else "")
        lines.append("\t".join(vals))

    tsv_content = "\n".join(lines) + "\n"

    return StreamingResponse(
        io.BytesIO(tsv_content.encode("utf-8")),
        media_type="text/tab-separated-values",
        headers={"Content-Disposition": "attachment; filename=metadata.tsv"},
    )
