import io
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models.models import Sample, Metadata, ASTResult, SIR, Project
from app.schemas.schemas import (
    MetadataCreate,
    MetadataRead,
    MetadataUpdate,
    ASTResultCreate,
    ASTResultRead,
)

router = APIRouter(tags=["metadata"])


@router.put("/samples/{sample_id}/metadata", response_model=MetadataRead)
def upsert_metadata(
    sample_id: uuid.UUID,
    payload: MetadataCreate,
    db: Session = Depends(get_db),
):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    meta = db.query(Metadata).filter(Metadata.sample_id == sample_id).first()
    if meta:
        if payload.source is not None:
            meta.source = payload.source
        if payload.collection_date is not None:
            meta.collection_date = payload.collection_date
        if payload.location is not None:
            meta.location = payload.location
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
            species=payload.species,
            custom_json=payload.custom_json,
        )
        db.add(meta)

    db.commit()
    db.refresh(meta)
    return meta


@router.get("/samples/{sample_id}/metadata", response_model=MetadataRead)
def get_metadata(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    meta = db.query(Metadata).filter(Metadata.sample_id == sample_id).first()
    if not meta:
        raise HTTPException(status_code=404, detail="Metadata not found for this sample")
    return meta


@router.post("/samples/{sample_id}/ast", response_model=ASTResultRead, status_code=201)
def add_ast_result(
    sample_id: uuid.UUID,
    payload: ASTResultCreate,
    db: Session = Depends(get_db),
):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    ast = ASTResult(
        sample_id=sample_id,
        antibiotic=payload.antibiotic,
        method=payload.method,
        mic=payload.mic,
        sir=SIR(payload.sir),
    )
    db.add(ast)
    db.commit()
    db.refresh(ast)
    return ast


@router.get("/samples/{sample_id}/ast", response_model=List[ASTResultRead])
def list_ast_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return db.query(ASTResult).filter(ASTResult.sample_id == sample_id).all()


@router.post("/projects/{project_id}/metadata/import", status_code=200)
async def bulk_import_metadata(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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
def list_all_metadata(db: Session = Depends(get_db)):
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
def download_metadata_tsv(db: Session = Depends(get_db)):
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
