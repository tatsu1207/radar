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
    ProphageResult,
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


@router.get("/samples/{sample_id}/is-elements")
def get_is_elements(
    sample_id: uuid.UUID,
    flanking: int = Query(default=5000, ge=0, le=50000, description="Flanking distance in bp"),
    db: Session = Depends(get_db),
):
    """Return IS elements from MOB-recon with ARG associations within flanking distance."""
    import os
    from app.config import settings

    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    mob_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "plasmid", "mob_recon_out")
    mge_report = os.path.join(mob_dir, "mge.report.txt")

    # Parse all IS elements (exclude rRNA)
    is_elements = []
    if os.path.exists(mge_report):
        with open(mge_report) as f:
            header = f.readline().strip().split("\t")
            for line in f:
                cols = line.strip().split("\t")
                if len(cols) < 15:
                    continue
                row = dict(zip(header, cols))
                mge_type = row.get("mge_type", "")
                if "rRNA" in mge_type or mge_type in ("16S", "23S"):
                    continue
                contig_raw = row.get("contig_id", "")
                contig_id = contig_raw.split()[0]
                try:
                    start = int(row.get("contig_start", 0))
                    end = int(row.get("contig_end", 0))
                except (ValueError, TypeError):
                    continue
                mol_type = row.get("molecule_type", "")
                is_elements.append({
                    "contig": contig_id,
                    "start": min(start, end),
                    "end": max(start, end),
                    "is_name": row.get("mge_type", ""),
                    "is_family": row.get("mge_subtype", ""),
                    "molecule_type": mol_type,
                    "plasmid_id": row.get("primary_cluster_id", "") if mol_type == "plasmid" else "",
                })

    # Get ARGs
    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()

    # Find ARG-IS associations within flanking distance
    arg_is_pairs = []
    for is_el in is_elements:
        nearby_args = []
        for arg in args:
            arg_contig = arg.contig.split()[0] if arg.contig else ""
            if arg_contig != is_el["contig"]:
                continue
            if not arg.start or not arg.end:
                continue
            # Distance from IS to ARG
            if arg.end < is_el["start"]:
                dist = is_el["start"] - arg.end
            elif arg.start > is_el["end"]:
                dist = arg.start - is_el["end"]
            else:
                dist = 0  # overlapping
            if dist <= flanking:
                nearby_args.append({
                    "gene": arg.gene,
                    "drug_class": arg.drug_class or "",
                    "start": arg.start,
                    "end": arg.end,
                    "distance": dist,
                    "database": arg.database or "",
                })
        is_el["nearby_args"] = nearby_args

    # Also build ARG-centric view: for each ARG, list nearby IS elements
    arg_associations = []
    for arg in args:
        if not arg.start or not arg.end:
            continue
        arg_contig = arg.contig.split()[0] if arg.contig else ""
        nearby_is = []
        for is_el in is_elements:
            if is_el["contig"] != arg_contig:
                continue
            if arg.end < is_el["start"]:
                dist = is_el["start"] - arg.end
            elif arg.start > is_el["end"]:
                dist = arg.start - is_el["end"]
            else:
                dist = 0
            if dist <= flanking:
                nearby_is.append({
                    "is_name": is_el["is_name"],
                    "is_family": is_el["is_family"],
                    "start": is_el["start"],
                    "end": is_el["end"],
                    "distance": dist,
                })
        if nearby_is:
            arg_associations.append({
                "gene": arg.gene,
                "drug_class": arg.drug_class or "",
                "contig": arg_contig,
                "start": arg.start,
                "end": arg.end,
                "on_plasmid": arg.on_plasmid,
                "database": arg.database or "",
                "nearby_is": sorted(nearby_is, key=lambda x: x["distance"]),
            })

    return {
        "is_elements": is_elements,
        "arg_associations": sorted(arg_associations, key=lambda x: len(x["nearby_is"]), reverse=True),
        "flanking_distance": flanking,
        "total_is": len(is_elements),
        "args_with_is": len(arg_associations),
    }


@router.get("/samples/{sample_id}/linear-map")
def get_linear_map(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return per-contig features for Easyfig-style linear genome maps."""
    import os
    from app.config import settings
    from app.models.models import IntegronResult as IntegronResultModel

    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    mob_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "plasmid", "mob_recon_out")

    # Get contig sizes from contig_report
    contig_info = {}  # contig_id -> {size, molecule_type, plasmid_id}
    contig_report = os.path.join(mob_dir, "contig_report.txt")
    if os.path.exists(contig_report):
        with open(contig_report) as f:
            header = f.readline().strip().split("\t")
            for line in f:
                cols = line.strip().split("\t")
                if len(cols) < 6:
                    continue
                row = dict(zip(header, cols))
                cid = row.get("contig_id", "").split()[0]
                contig_info[cid] = {
                    "size": int(row.get("size", 0)),
                    "molecule_type": row.get("molecule_type", ""),
                    "plasmid_id": row.get("primary_cluster_id", "") if row.get("molecule_type") == "plasmid" else "",
                }

    # IS elements from MOB-recon
    mge_report = os.path.join(mob_dir, "mge.report.txt")
    is_features = {}  # contig_id -> list
    if os.path.exists(mge_report):
        with open(mge_report) as f:
            header = f.readline().strip().split("\t")
            for line in f:
                cols = line.strip().split("\t")
                if len(cols) < 15:
                    continue
                row = dict(zip(header, cols))
                mge_type = row.get("mge_type", "")
                if "rRNA" in mge_type or mge_type in ("16S", "23S"):
                    continue
                cid = row.get("contig_id", "").split()[0]
                try:
                    start = int(row.get("contig_start", 0))
                    end = int(row.get("contig_end", 0))
                    strand_str = row.get("sstrand", "plus")
                except (ValueError, TypeError):
                    continue
                is_features.setdefault(cid, []).append({
                    "type": "mobile_element",
                    "name": mge_type,
                    "label": row.get("mge_subtype", ""),
                    "family": row.get("mge_subtype", ""),
                    "start": min(start, end),
                    "end": max(start, end),
                    "strand": 1 if strand_str == "plus" else -1,
                })

    # Conjugation elements from biomarkers
    biomarker_file = os.path.join(mob_dir, "biomarkers.blast.txt")
    if os.path.exists(biomarker_file):
        with open(biomarker_file) as f:
            bm_header = f.readline().strip().split("\t")
            for line in f:
                cols = line.strip().split("\t")
                if len(cols) < len(bm_header):
                    continue
                row = dict(zip(bm_header, cols))
                sseqid = row.get("sseqid", "")
                cid = sseqid.split()[0]
                if cid not in contig_info or contig_info[cid]["molecule_type"] != "plasmid":
                    continue
                bm_type = row.get("biomarker", "")
                try:
                    start = int(row.get("sstart", 0))
                    end = int(row.get("send", 0))
                except (ValueError, TypeError):
                    continue
                qseqid = row.get("qseqid", "")
                short_label = qseqid.split("|")[-1] if "|" in qseqid else qseqid
                type_map = {"relaxase": "relaxase", "oriT": "orit", "mate-pair-formation": "t4ss", "replicon": "replicon"}
                feat_type = type_map.get(bm_type)
                if not feat_type:
                    continue
                is_features.setdefault(cid, []).append({
                    "type": feat_type,
                    "name": short_label,
                    "label": bm_type,
                    "family": short_label,
                    "start": min(start, end),
                    "end": max(start, end),
                    "strand": 1,
                })

    # ARGs
    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    arg_features = {}
    for arg in args:
        if not arg.start or not arg.end:
            continue
        cid = arg.contig.split()[0] if arg.contig else ""
        arg_features.setdefault(cid, []).append({
            "type": "arg",
            "name": arg.gene,
            "label": arg.drug_class or "",
            "family": arg.mechanism or "",
            "start": min(arg.start, arg.end),
            "end": max(arg.start, arg.end),
            "strand": 1,
        })

    # VFs
    vf_features = {}
    vfs = db.query(VirulenceResult).filter(VirulenceResult.sample_id == sample_id).all()
    for vf in vfs:
        if not vf.start or not vf.end:
            continue
        cid = vf.contig.split()[0] if vf.contig else ""
        vf_features.setdefault(cid, []).append({
            "type": "virulence",
            "name": vf.gene,
            "label": vf.category or "virulence",
            "family": "",
            "start": min(vf.start, vf.end),
            "end": max(vf.start, vf.end),
            "strand": 1,
        })

    # Prophages
    prophage_features = {}
    prophages = db.query(ProphageResult).filter(ProphageResult.sample_id == sample_id).all()
    for ph in prophages:
        if not ph.start or not ph.end:
            continue
        cid = ph.contig.split()[0] if ph.contig else ""
        prophage_features.setdefault(cid, []).append({
            "type": "prophage",
            "name": ph.taxonomy or "prophage",
            "label": f"score={ph.virus_score}" if ph.virus_score else "",
            "family": "",
            "start": min(ph.start, ph.end),
            "end": max(ph.start, ph.end),
            "strand": 1,
        })

    # BacMet
    from app.models.models import BacMetResult
    bacmet_features = {}
    bacmets = db.query(BacMetResult).filter(BacMetResult.sample_id == sample_id).all()
    for bm in bacmets:
        if not bm.start or not bm.end:
            continue
        cid = bm.contig.split()[0] if bm.contig else ""
        bacmet_features.setdefault(cid, []).append({
            "type": "bacmet",
            "name": bm.gene,
            "label": bm.compound or "",
            "family": "",
            "start": min(bm.start, bm.end),
            "end": max(bm.start, bm.end),
            "strand": 1,
        })

    # Integrons
    integrons = db.query(IntegronResultModel).filter(IntegronResultModel.sample_id == sample_id).all()
    integ_features = {}
    for ig in integrons:
        cid = ig.contig or ""
        if ig.cassettes:
            for c in ig.cassettes:
                if c.get("annotation") == "intI":
                    ft = "integrase"
                elif c.get("annotation") == "attC":
                    ft = "attc"
                else:
                    continue
                integ_features.setdefault(cid, []).append({
                    "type": ft,
                    "name": c["annotation"],
                    "label": ig.integron_type or "",
                    "family": ig.integron_id or "",
                    "start": c["start"],
                    "end": c["end"],
                    "strand": 1,
                })

    # Build per-contig result
    all_contigs = set(
        list(contig_info.keys()) + list(arg_features.keys()) +
        list(vf_features.keys()) + list(prophage_features.keys()) +
        list(bacmet_features.keys())
    )
    result = []
    for cid in sorted(all_contigs):
        info = contig_info.get(cid, {"size": 0, "molecule_type": "unknown", "plasmid_id": ""})
        features = []
        features.extend(arg_features.get(cid, []))
        features.extend(vf_features.get(cid, []))
        features.extend(is_features.get(cid, []))
        features.extend(integ_features.get(cid, []))
        features.extend(prophage_features.get(cid, []))
        features.extend(bacmet_features.get(cid, []))
        features.sort(key=lambda f: f["start"])
        if not features:
            continue
        result.append({
            "contig": cid,
            "length": info["size"],
            "molecule_type": info["molecule_type"],
            "plasmid_id": info["plasmid_id"],
            "features": features,
        })

    return result


@router.get("/samples/{sample_id}/plasmid-map")
def get_plasmid_map(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return plasmid map data: contigs with ARGs, IS elements, prophages mapped."""
    import os
    from app.config import settings

    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    mob_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "plasmid", "mob_recon_out")
    contig_report = os.path.join(mob_dir, "contig_report.txt")
    mge_report = os.path.join(mob_dir, "mge.report.txt")

    # Parse contig report for plasmid contigs
    plasmid_contigs = {}  # contig_id -> {plasmid_id, size, replicon, mob_type, mpf_type}
    if os.path.exists(contig_report):
        with open(contig_report) as f:
            header = f.readline().strip().split("\t")
            for line in f:
                cols = line.strip().split("\t")
                if len(cols) < 6:
                    continue
                row = dict(zip(header, cols))
                if row.get("molecule_type") != "plasmid":
                    continue
                contig_raw = row.get("contig_id", "")
                contig_id = contig_raw.split()[0]  # strip " polypolish" etc
                plasmid_contigs[contig_id] = {
                    "plasmid_id": row.get("primary_cluster_id", ""),
                    "size": int(row.get("size", 0)),
                    "replicon": row.get("rep_type(s)", "-"),
                    "mob_type": row.get("relaxase_type(s)", "-"),
                    "mpf_type": row.get("mpf_type", "-"),
                    "orit_type": row.get("orit_type(s)", "-"),
                    "predicted_mobility": row.get("predicted_mobility", "-"),
                }

    if not plasmid_contigs:
        return []

    # Parse MGE report for IS elements on plasmid contigs
    mge_features = {}  # contig_id -> list of features
    if os.path.exists(mge_report):
        with open(mge_report) as f:
            header = f.readline().strip().split("\t")
            for line in f:
                cols = line.strip().split("\t")
                if len(cols) < 15:
                    continue
                row = dict(zip(header, cols))
                if row.get("molecule_type") != "plasmid":
                    continue
                contig_raw = row.get("contig_id", "")
                contig_id = contig_raw.split()[0]
                mge_type = row.get("mge_type", "")
                if mge_type in ("16s-rRNA", "23s-rRNA", "16S", "23S"):
                    continue
                start = int(row.get("contig_start", 0))
                end = int(row.get("contig_end", 0))
                mge_features.setdefault(contig_id, []).append({
                    "type": "mobile_element",
                    "name": row.get("mge_id", ""),
                    "label": row.get("mge_type", ""),
                    "family": row.get("mge_subtype", ""),
                    "start": min(start, end),
                    "end": max(start, end),
                })

    # Parse biomarkers BLAST for conjugation elements (relaxase, oriT, MPF/T4SS, replicons)
    # Deduplicate by contig + type + name (keep best/first hit)
    biomarker_file = os.path.join(mob_dir, "biomarkers.blast.txt")
    conjugation_features = {}  # contig_id -> list of features
    _seen_biomarkers = set()
    if os.path.exists(biomarker_file):
        with open(biomarker_file) as f:
            bm_header = f.readline().strip().split("\t")
            for line in f:
                cols = line.strip().split("\t")
                if len(cols) < len(bm_header):
                    continue
                row = dict(zip(bm_header, cols))
                sseqid = row.get("sseqid", "")
                contig_id = sseqid.split()[0]
                if contig_id not in plasmid_contigs:
                    continue
                bm_type = row.get("biomarker", "")
                try:
                    start = int(row.get("sstart", 0))
                    end = int(row.get("send", 0))
                except (ValueError, TypeError):
                    continue
                qseqid = row.get("qseqid", "")
                short_label = qseqid.split("|")[-1] if "|" in qseqid else qseqid

                if bm_type == "relaxase":
                    feat_type = "relaxase"
                    name = short_label
                elif bm_type == "oriT":
                    feat_type = "orit"
                    name = "oriT"
                elif bm_type == "mate-pair-formation":
                    feat_type = "t4ss"
                    name = short_label
                elif bm_type == "replicon":
                    feat_type = "replicon"
                    name = short_label
                else:
                    continue

                # Deduplicate: one feature per type+name per contig
                dedup_key = f"{contig_id}:{feat_type}:{name}"
                if dedup_key in _seen_biomarkers:
                    continue
                _seen_biomarkers.add(dedup_key)

                conjugation_features.setdefault(contig_id, []).append({
                    "type": feat_type,
                    "name": name,
                    "label": bm_type,
                    "family": short_label,
                    "start": min(start, end),
                    "end": max(start, end),
                })

    # Get ARGs on plasmid contigs
    args = db.query(ARGResult).filter(
        ARGResult.sample_id == sample_id,
        ARGResult.on_plasmid == True,
    ).all()

    # Get VFs on plasmid contigs
    vfs = db.query(VirulenceResult).filter(
        VirulenceResult.sample_id == sample_id,
    ).all()

    # Get prophages on plasmid contigs
    prophages = db.query(ProphageResult).filter(
        ProphageResult.sample_id == sample_id,
    ).all()

    # Build map per plasmid
    result = []
    for contig_id, pinfo in plasmid_contigs.items():
        features = []

        # ARGs
        for arg in args:
            arg_contig = arg.contig.split()[0] if arg.contig else ""
            if arg_contig == contig_id and arg.start and arg.end:
                features.append({
                    "type": "arg",
                    "name": arg.gene,
                    "label": arg.drug_class or "",
                    "family": arg.mechanism or "",
                    "start": min(arg.start, arg.end),
                    "end": max(arg.start, arg.end),
                })

        # VFs
        for vf in vfs:
            vf_contig = vf.contig.split()[0] if vf.contig else ""
            if vf_contig == contig_id and vf.start and vf.end:
                features.append({
                    "type": "virulence",
                    "name": vf.gene,
                    "label": vf.category or "virulence",
                    "family": "",
                    "start": min(vf.start, vf.end),
                    "end": max(vf.start, vf.end),
                })

        # IS elements from MOB-recon MGE report
        for mge in mge_features.get(contig_id, []):
            features.append(mge)

        # Conjugation elements (relaxase, oriT, T4SS, replicon)
        for cf in conjugation_features.get(contig_id, []):
            features.append(cf)

        # Prophages
        for ph in prophages:
            ph_contig = ph.contig.split()[0] if ph.contig else ""
            if ph_contig == contig_id and ph.start and ph.end:
                features.append({
                    "type": "prophage",
                    "name": ph.taxonomy or "prophage",
                    "label": f"score={ph.virus_score}" if ph.virus_score else "",
                    "family": "",
                    "start": min(ph.start, ph.end),
                    "end": max(ph.start, ph.end),
                })

        features.sort(key=lambda f: f["start"])

        # Infer mobility from conjugation elements if not reported
        predicted_mobility = pinfo["predicted_mobility"]
        if predicted_mobility == "-" or not predicted_mobility:
            feat_types = {f["type"] for f in features}
            has_relaxase = "relaxase" in feat_types
            has_orit = "orit" in feat_types
            has_t4ss = "t4ss" in feat_types
            if has_relaxase and has_t4ss:
                predicted_mobility = "conjugative"
            elif has_relaxase or has_orit:
                predicted_mobility = "mobilizable"
            else:
                predicted_mobility = "non-mobilizable"

        result.append({
            "plasmid_id": pinfo["plasmid_id"],
            "contig": contig_id,
            "size": pinfo["size"],
            "replicon": pinfo["replicon"],
            "mob_type": pinfo["mob_type"],
            "mpf_type": pinfo["mpf_type"],
            "orit_type": pinfo["orit_type"],
            "predicted_mobility": predicted_mobility,
            "features": features,
        })

    return result


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


@router.get("/export/annotations")
def export_all_annotations(
    sample_ids: str = Query(..., description="Comma-separated sample UUIDs"),
    db: Session = Depends(get_db),
):
    """Export all annotation results for selected samples as a ZIP of TSV files."""
    import zipfile
    from app.models.models import (
        SpeciesResult, MLSTResult, PlasmidResult, MobilityResult,
        ProphageResult, IntegronResult, CRISPRResult, DefenseFinderResult,
        ICEResult, BacMetResult, MLPhenotypePrediction, RiskScore,
    )

    ids = [s.strip() for s in sample_ids.split(",") if s.strip()]
    samples = db.query(Sample).filter(Sample.id.in_(ids)).all()
    sample_names = {str(s.id): s.name for s in samples}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

        # ARGs
        out = io.StringIO()
        w = csv.writer(out, delimiter="\t")
        w.writerow(["sample", "gene", "drug_class", "mechanism", "identity", "coverage",
                     "contig", "start", "end", "on_plasmid", "on_prophage", "cai", "gene_gc"])
        for sid in ids:
            name = sample_names.get(sid, sid)
            for a in db.query(ARGResult).filter(ARGResult.sample_id == sid).all():
                w.writerow([name, a.gene, a.drug_class, a.mechanism, a.identity, a.coverage,
                            a.contig, a.start, a.end, a.on_plasmid, a.on_prophage, a.cai, a.gene_gc])
        zf.writestr("args.tsv", out.getvalue())

        # Virulence
        out = io.StringIO()
        w = csv.writer(out, delimiter="\t")
        w.writerow(["sample", "gene", "category", "identity", "coverage", "contig", "start", "end"])
        for sid in ids:
            name = sample_names.get(sid, sid)
            for v in db.query(VirulenceResult).filter(VirulenceResult.sample_id == sid).all():
                w.writerow([name, v.gene, v.category, v.identity, v.coverage, v.contig, v.start, v.end])
        zf.writestr("virulence.tsv", out.getvalue())

        # Plasmids
        out = io.StringIO()
        w = csv.writer(out, delimiter="\t")
        w.writerow(["sample", "plasmid_id", "replicon", "mob_type", "mobility"])
        for sid in ids:
            name = sample_names.get(sid, sid)
            for p in db.query(PlasmidResult).filter(PlasmidResult.sample_id == sid).all():
                w.writerow([name, p.plasmid_id, p.replicon, p.mob_type, p.predicted_mobility])
        zf.writestr("plasmids.tsv", out.getvalue())

        # BacMet
        out = io.StringIO()
        w = csv.writer(out, delimiter="\t")
        w.writerow(["sample", "gene", "bacmet_id", "compound", "identity", "coverage", "contig", "start", "end"])
        for sid in ids:
            name = sample_names.get(sid, sid)
            for b in db.query(BacMetResult).filter(BacMetResult.sample_id == sid).all():
                w.writerow([name, b.gene, b.bacmet_id, b.compound, b.identity, b.coverage, b.contig, b.start, b.end])
        zf.writestr("bacmet.tsv", out.getvalue())

        # ML Phenotype Predictions
        out = io.StringIO()
        w = csv.writer(out, delimiter="\t")
        w.writerow(["sample", "antibiotic", "drug_class", "prediction", "probability", "confidence", "key_genes", "key_mutations"])
        for sid in ids:
            name = sample_names.get(sid, sid)
            for p in db.query(MLPhenotypePrediction).filter(MLPhenotypePrediction.sample_id == sid).all():
                w.writerow([name, p.antibiotic, p.drug_class, p.prediction, p.probability, p.confidence,
                            ";".join(p.key_genes or []), ";".join(p.key_mutations or [])])
        zf.writestr("phenotype_predictions.tsv", out.getvalue())

        # Species + MLST
        out = io.StringIO()
        w = csv.writer(out, delimiter="\t")
        w.writerow(["sample", "species", "species_identity", "species_method", "mlst_scheme", "mlst_st"])
        for sid in ids:
            name = sample_names.get(sid, sid)
            sp = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sid).first()
            mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sid).first()
            w.writerow([name,
                        sp.species if sp else "", sp.identity if sp else "", sp.method if sp else "",
                        mlst.scheme if mlst else "", mlst.sequence_type if mlst else ""])
        zf.writestr("species_mlst.tsv", out.getvalue())

        # Risk scores
        out = io.StringIO()
        w = csv.writer(out, delimiter="\t")
        w.writerow(["sample", "arg_score", "vf_score", "mobility_score", "composite_score", "risk_category"])
        for sid in ids:
            name = sample_names.get(sid, sid)
            r = db.query(RiskScore).filter(RiskScore.sample_id == sid).first()
            if r:
                w.writerow([name, r.arg_score, r.vf_score, r.mobility_score, r.composite_score, r.risk_category.value])
        zf.writestr("risk_scores.tsv", out.getvalue())

        # Prophages
        out = io.StringIO()
        w = csv.writer(out, delimiter="\t")
        w.writerow(["sample", "contig", "start", "end", "length", "virus_score", "taxonomy"])
        for sid in ids:
            name = sample_names.get(sid, sid)
            for p in db.query(ProphageResult).filter(ProphageResult.sample_id == sid).all():
                w.writerow([name, p.contig, p.start, p.end, p.length, p.virus_score, p.taxonomy])
        zf.writestr("prophages.tsv", out.getvalue())

        # Defense systems
        out = io.StringIO()
        w = csv.writer(out, delimiter="\t")
        w.writerow(["sample", "system_type", "subtype", "contig", "start", "end", "protein_count"])
        for sid in ids:
            name = sample_names.get(sid, sid)
            for d in db.query(DefenseFinderResult).filter(DefenseFinderResult.sample_id == sid).all():
                w.writerow([name, d.system_type, d.subtype, d.contig, d.start, d.end, d.protein_count])
        zf.writestr("defense_systems.tsv", out.getvalue())

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=radar_annotations.zip"},
    )


@router.get("/export/feature-matrix")
def export_feature_matrix_csv(db: Session = Depends(get_db)):
    """Export all samples as a wide feature matrix CSV.

    Format: Sample_ID, gene1, gene1_dg_mrna, gene1_dg_total, gene1_expression,
    gene1_promoter_dist, gene1_promoter_ldf, gene1_promoter_tf, gene1_promoter_up,
    gene1_is_count, gene1_is_min_dist, gene1_is_orientation, gene2, ...

    Compatible with vault/phenotype/data/test_inputs/ format.
    """
    from app.core.export_features import export_feature_matrix

    samples = db.query(Sample).order_by(Sample.name).all()
    sample_ids = [str(s.id) for s in samples]

    csv_content = export_feature_matrix(sample_ids, db)

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=feature_matrix.csv"},
    )


@router.get("/sra-submission")
def get_sra_submission_data(db: Session = Depends(get_db)):
    """Get sample data formatted for SRA submission preparation.

    Returns metadata for BioSample and SRA metadata TSV templates.
    Only includes samples with FASTQ files.
    """
    from app.models.models import SampleFile, Metadata, SpeciesResult

    samples = db.query(Sample).order_by(Sample.name).all()
    entries = []

    for sample in samples:
        files = db.query(SampleFile).filter(SampleFile.sample_id == sample.id).all()
        fastq_files = [f for f in files if f.file_path and
                       any(f.file_path.lower().endswith(ext) for ext in (".fastq.gz", ".fq.gz", ".fastq", ".fq"))]
        if not fastq_files:
            continue

        metadata = db.query(Metadata).filter(Metadata.sample_id == sample.id).first()
        species = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample.id).first()

        # Determine library layout from files
        from app.models.models import PairType
        has_r1 = any(f.pair == PairType.R1 for f in files)
        has_r2 = any(f.pair == PairType.R2 for f in files)
        has_long = any(f.pair == PairType.long_read for f in files)
        is_paired = has_r1 and has_r2

        # Determine platform
        platform = "ILLUMINA"
        instrument = "Illumina MiSeq"
        if has_long and not has_r1:
            plat_files = [f for f in files if f.pair == PairType.long_read]
            if plat_files and plat_files[0].platform:
                pv = plat_files[0].platform.value
                if "ont" in pv.lower():
                    platform = "OXFORD_NANOPORE"
                    instrument = "MinION"
                elif "pacbio" in pv.lower():
                    platform = "PACBIO_SMRT"
                    instrument = "PacBio RS II"

        import os
        filenames = [f.original_filename or os.path.basename(f.file_path) for f in fastq_files]

        entries.append({
            "sample_id": str(sample.id),
            "sample_name": sample.name,
            "organism": species.species if species else (metadata.species if metadata and hasattr(metadata, 'species') else ""),
            "collection_date": metadata.collection_date if metadata else "",
            "geo_loc_name": metadata.location if metadata else "",
            "isolation_source": metadata.source if metadata else "",
            "library_strategy": "WGS",
            "library_source": "GENOMIC",
            "library_selection": "RANDOM",
            "library_layout": "paired" if is_paired else "single",
            "platform": platform,
            "instrument_model": instrument,
            "filetype": "fastq",
            "filenames": filenames,
            "filename1": filenames[0] if filenames else "",
            "filename2": filenames[1] if len(filenames) > 1 and is_paired else "",
        })

    return entries


# ── BacMet Results ───────────────────────────────────────────────────────────

@router.get("/samples/{sample_id}/bacmet")
def get_bacmet_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get BacMet2 biocide/metal resistance results for a sample."""
    from app.models.models import BacMetResult

    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    results = (
        db.query(BacMetResult)
        .filter(BacMetResult.sample_id == sample_id)
        .order_by(BacMetResult.compound, BacMetResult.gene)
        .all()
    )

    return [
        {
            "id": str(r.id),
            "gene": r.gene,
            "bacmet_id": r.bacmet_id,
            "compound": r.compound,
            "identity": r.identity,
            "coverage": r.coverage,
            "contig": r.contig,
            "start": r.start,
            "end": r.end,
        }
        for r in results
    ]


# ── ML Phenotype Predictions ─────────────────────────────────────────────────

@router.get("/samples/{sample_id}/ml-predictions")
def get_ml_predictions(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get ML-based phenotype predictions for a sample."""
    from app.models.models import MLPhenotypePrediction, SpeciesResult, MLSTResult

    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    preds = (
        db.query(MLPhenotypePrediction)
        .filter(MLPhenotypePrediction.sample_id == sample_id)
        .order_by(MLPhenotypePrediction.antibiotic)
        .all()
    )

    species = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()

    n_r = sum(1 for p in preds if p.prediction == "Resistant")

    return {
        "species": species.species if species else None,
        "mlst_st": mlst.sequence_type if mlst else None,
        "n_antibiotics": len(preds),
        "n_resistant": n_r,
        "n_susceptible": len(preds) - n_r,
        "predictions": [
            {
                "id": str(p.id),
                "antibiotic": p.antibiotic,
                "drug_class": p.drug_class,
                "prediction": p.prediction,
                "probability": p.probability,
                "confidence": p.confidence,
                "key_genes": p.key_genes or [],
                "key_mutations": p.key_mutations or [],
            }
            for p in preds
        ],
    }
