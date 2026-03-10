import csv
import io
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.models import (
    Sample,
    ARGResult,
    PlasmidResult,
    MobilityResult,
    RiskScore,
    VirulenceResult,
    Project,
)
from app.schemas.schemas import (
    ARGResultRead,
    PlasmidResultRead,
    MobilityResultRead,
    RiskScoreRead,
    VirulenceResultRead,
)

router = APIRouter(tags=["results"])


@router.get("/samples/{sample_id}/args", response_model=List[ARGResultRead])
def get_arg_results(
    sample_id: uuid.UUID,
    drug_class: Optional[str] = None,
    database: Optional[str] = None,
    min_identity: Optional[float] = None,
    on_plasmid: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    query = db.query(ARGResult).filter(ARGResult.sample_id == sample_id)

    if drug_class:
        query = query.filter(ARGResult.drug_class.ilike(f"%{drug_class}%"))
    if database:
        query = query.filter(ARGResult.database == database)
    if min_identity is not None:
        query = query.filter(ARGResult.identity >= min_identity)
    if on_plasmid is not None:
        query = query.filter(ARGResult.on_plasmid == on_plasmid)

    return query.all()


@router.get("/samples/{sample_id}/plasmids", response_model=List[PlasmidResultRead])
def get_plasmid_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return db.query(PlasmidResult).filter(PlasmidResult.sample_id == sample_id).all()


@router.get("/samples/{sample_id}/mobility", response_model=List[MobilityResultRead])
def get_mobility_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return db.query(MobilityResult).filter(MobilityResult.sample_id == sample_id).all()


@router.get("/samples/{sample_id}/risk", response_model=RiskScoreRead)
def get_risk_score(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    risk = db.query(RiskScore).filter(RiskScore.sample_id == sample_id).first()
    if not risk:
        raise HTTPException(status_code=404, detail="Risk score not calculated yet")
    return risk


@router.get("/samples/{sample_id}/virulence", response_model=List[VirulenceResultRead])
def get_virulence_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return db.query(VirulenceResult).filter(VirulenceResult.sample_id == sample_id).all()


@router.get("/projects/{project_id}/heatmap")
def get_heatmap_data(project_id: uuid.UUID, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    samples = db.query(Sample).filter(Sample.project_id == project_id).all()

    # Build matrix: samples x drug_classes
    all_drug_classes: set = set()
    sample_data: Dict[str, Dict[str, int]] = {}

    for sample in samples:
        args = db.query(ARGResult).filter(ARGResult.sample_id == sample.id).all()
        drug_map: Dict[str, int] = {}
        for arg in args:
            if arg.drug_class:
                classes = [c.strip() for c in arg.drug_class.split(";")]
                for dc in classes:
                    all_drug_classes.add(dc)
                    drug_map[dc] = drug_map.get(dc, 0) + 1
        sample_data[sample.name] = drug_map

    drug_classes_sorted = sorted(all_drug_classes)

    matrix = []
    sample_names = []
    for sample in samples:
        sample_names.append(sample.name)
        row = []
        drug_map = sample_data.get(sample.name, {})
        for dc in drug_classes_sorted:
            row.append(drug_map.get(dc, 0))
        matrix.append(row)

    return {
        "samples": sample_names,
        "drug_classes": drug_classes_sorted,
        "matrix": matrix,
    }


@router.get("/samples/{sample_id}/export")
def export_results_csv(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    output = io.StringIO()
    writer = csv.writer(output)

    # ARG results
    writer.writerow([
        "result_type", "gene", "drug_class", "mechanism", "identity",
        "coverage", "contig", "start", "end", "database", "on_plasmid",
    ])

    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    for arg in args:
        writer.writerow([
            "ARG", arg.gene, arg.drug_class, arg.mechanism, arg.identity,
            arg.coverage, arg.contig, arg.start, arg.end, arg.database, arg.on_plasmid,
        ])

    vfs = db.query(VirulenceResult).filter(VirulenceResult.sample_id == sample_id).all()
    for vf in vfs:
        writer.writerow([
            "VF", vf.gene, vf.category, "", vf.identity,
            vf.coverage, vf.contig, "", "", vf.database, "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={sample.name}_results.csv"},
    )
