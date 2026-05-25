import csv
import io
import os
import re
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
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
    SpeciesResult,
    MLSTResult,
    SerotypeResult,
    BacMetResult,
)
from app.schemas.schemas import (
    ARGResultRead,
    PlasmidResultRead,
    MobilityResultRead,
    RiskScoreRead,
    VirulenceResultRead,
)

router = APIRouter(tags=["results"])


@router.get("/samples/{sample_id}/summary")
def get_sample_summary(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Aggregate summary of all annotation results for a sample."""
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    # Species
    species_row = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    # MLST
    mlst_row = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
    # Serotype
    sero_row = db.query(SerotypeResult).filter(SerotypeResult.sample_id == sample_id).first()

    # ARGs
    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    arg_genes = [a.gene for a in args]
    drug_classes = sorted(set(dc.strip() for a in args if a.drug_class for dc in a.drug_class.split(";")))

    # VFs
    vfs = db.query(VirulenceResult).filter(VirulenceResult.sample_id == sample_id).all()

    # Plasmids
    plasmids = db.query(PlasmidResult).filter(PlasmidResult.sample_id == sample_id).all()

    # BacMet
    bacmets = db.query(BacMetResult).filter(BacMetResult.sample_id == sample_id).all()

    # QUAST (from file)
    quast_data = None
    quast_report = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly", "quast", "report.tsv")
    if os.path.exists(quast_report):
        quast_data = {}
        quast_key_map = {
            "Total length": "total_length",
            "# contigs": "num_contigs",
            "N50": "n50",
            "GC (%)": "gc_percent",
            "Largest contig": "largest_contig",
        }
        with open(quast_report) as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) < 2:
                    continue
                key, val = parts[0], parts[1]
                # Skip lines with parenthetical qualifiers like "# contigs (>= 1000 bp)"
                if key in quast_key_map:
                    field = quast_key_map[key]
                    if field == "gc_percent":
                        quast_data[field] = _safe_float_val(val)
                    else:
                        quast_data[field] = _safe_int_val(val)

    # BUSCO (from file)
    busco_data = None
    busco_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly", "busco", "busco_result")
    if os.path.isdir(busco_dir):
        for root, dirs, files in os.walk(busco_dir):
            for fname in files:
                if fname.startswith("short_summary"):
                    with open(os.path.join(root, fname)) as bf:
                        content = bf.read()
                        busco_data = {}
                        m = re.search(r"C:([\d.]+)%\[S:([\d.]+)%,D:([\d.]+)%\],F:([\d.]+)%.*M:([\d.]+)%", content)
                        if m:
                            busco_data["complete"] = float(m.group(1))
                            busco_data["single_copy"] = float(m.group(2))
                            busco_data["duplicated"] = float(m.group(3))
                            busco_data["fragmented"] = float(m.group(4))
                            busco_data["missing"] = float(m.group(5))
                    break
            if busco_data is not None:
                break

    return {
        "sample_id": str(sample_id),
        "sample_name": sample.name,
        "status": sample.status.value if sample.status else "unknown",
        "species": species_row.species if species_row else None,
        "species_identity": species_row.identity if species_row else None,
        "mlst_scheme": mlst_row.scheme if mlst_row else None,
        "mlst_st": mlst_row.sequence_type if mlst_row else None,
        "serotype": sero_row.serotype if sero_row else None,
        "serotype_tool": sero_row.tool if sero_row else None,
        "arg_count": len(args),
        "arg_genes": arg_genes,
        "drug_classes": drug_classes,
        "vf_count": len(vfs),
        "vf_genes": [v.gene for v in vfs],
        "drug_resistance": drug_classes,
        "pathotype": None,
        "plasmids": [
            {"plasmid_id": p.plasmid_id or "", "replicon": p.replicon or "", "mobility": p.predicted_mobility or ""}
            for p in plasmids
        ],
        "bacmet": [
            {"gene": b.gene, "compound": b.compound or "", "identity": b.identity or 0}
            for b in bacmets
        ],
        "quast": quast_data,
        "busco": busco_data,
    }


def _safe_int_val(val: str):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float_val(val: str):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


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

    # Deduplicate by gene name: keep the hit with highest identity
    results = query.all()
    seen: dict = {}
    for r in results:
        if r.gene not in seen or (r.identity or 0) > (seen[r.gene].identity or 0):
            seen[r.gene] = r
    return list(seen.values())


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

    # Get ARGs and VFs
    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    vfs = db.query(VirulenceResult).filter(VirulenceResult.sample_id == sample_id).all()

    def _calc_distance(el_start, el_end, feat_start, feat_end):
        if feat_end < el_start:
            return el_start - feat_end
        elif feat_start > el_end:
            return feat_start - el_end
        return 0  # overlapping

    # For each IS element, find nearby ARGs and VFs
    for is_el in is_elements:
        nearby = []
        for arg in args:
            arg_contig = arg.contig.split()[0] if arg.contig else ""
            if arg_contig != is_el["contig"] or not arg.start or not arg.end:
                continue
            dist = _calc_distance(is_el["start"], is_el["end"], arg.start, arg.end)
            if dist <= flanking:
                nearby.append({
                    "gene": arg.gene,
                    "type": "ARG",
                    "detail": arg.drug_class or "",
                    "start": arg.start,
                    "end": arg.end,
                    "strand": 1,
                    "distance": dist,
                })
        for vf in vfs:
            vf_contig = vf.contig.split()[0] if vf.contig else ""
            if vf_contig != is_el["contig"] or not vf.start or not vf.end:
                continue
            dist = _calc_distance(is_el["start"], is_el["end"], vf.start, vf.end)
            if dist <= flanking:
                nearby.append({
                    "gene": vf.gene,
                    "type": "VF",
                    "detail": vf.category or "virulence",
                    "start": vf.start,
                    "end": vf.end,
                    "strand": 1,
                    "distance": dist,
                })
        is_el["nearby_genes"] = sorted(nearby, key=lambda x: x["start"])

    # Build synteny regions: for each IS with nearby genes, define a region
    # spanning from the leftmost to the rightmost feature + padding
    synteny_regions = []
    for is_el in is_elements:
        if not is_el["nearby_genes"]:
            continue
        all_starts = [is_el["start"]] + [g["start"] for g in is_el["nearby_genes"]]
        all_ends = [is_el["end"]] + [g["end"] for g in is_el["nearby_genes"]]
        region_start = min(all_starts)
        region_end = max(all_ends)
        # Pad by 500bp for visual breathing room
        region_start = max(0, region_start - 500)
        region_end = region_end + 500

        # Build features list for this region
        features = [{
            "type": "mobile_element",
            "name": is_el["is_name"],
            "label": is_el["is_family"],
            "family": is_el["is_family"],
            "start": is_el["start"],
            "end": is_el["end"],
            "strand": 1,
        }]
        for g in is_el["nearby_genes"]:
            features.append({
                "type": "arg" if g["type"] == "ARG" else "virulence",
                "name": g["gene"],
                "label": g["detail"],
                "family": g["detail"],
                "start": g["start"],
                "end": g["end"],
                "strand": g["strand"],
            })
        features.sort(key=lambda f: f["start"])

        # Also find other IS elements on the same contig in this region
        for other in is_elements:
            if other is is_el:
                continue
            if other["contig"] != is_el["contig"]:
                continue
            if other["end"] >= region_start and other["start"] <= region_end:
                features.append({
                    "type": "mobile_element",
                    "name": other["is_name"],
                    "label": other["is_family"],
                    "family": other["is_family"],
                    "start": other["start"],
                    "end": other["end"],
                    "strand": 1,
                })
        features.sort(key=lambda f: f["start"])

        synteny_regions.append({
            "contig": is_el["contig"],
            "is_name": is_el["is_name"],
            "molecule_type": is_el["molecule_type"],
            "plasmid_id": is_el.get("plasmid_id", ""),
            "region_start": region_start,
            "region_end": region_end,
            "length": region_end - region_start,
            "features": features,
        })

    return {
        "is_elements": is_elements,
        "synteny_regions": synteny_regions,
        "flanking_distance": flanking,
        "total_is": len(is_elements),
        "with_nearby": sum(1 for el in is_elements if el["nearby_genes"]),
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

    # Group contigs by plasmid_id into single maps
    grouped: dict = {}
    for entry in result:
        pid = entry["plasmid_id"]
        if pid not in grouped:
            grouped[pid] = {
                "plasmid_id": pid,
                "contig": entry["contig"],
                "size": entry["size"],
                "replicon": entry["replicon"],
                "mob_type": entry["mob_type"],
                "mpf_type": entry["mpf_type"],
                "orit_type": entry["orit_type"],
                "predicted_mobility": entry["predicted_mobility"],
                "features": list(entry["features"]),
            }
        else:
            g = grouped[pid]
            g["size"] += entry["size"]
            g["contig"] += f", {entry['contig']}"
            # Merge features, offsetting positions by accumulated size
            offset = g["size"] - entry["size"]
            for f in entry["features"]:
                grouped[pid]["features"].append({
                    **f,
                    "start": f["start"] + offset,
                    "end": f["end"] + offset,
                })
            # Keep the more informative replicon/mob_type
            if entry["replicon"] != "-" and g["replicon"] == "-":
                g["replicon"] = entry["replicon"]
            if entry["mob_type"] != "-" and g["mob_type"] == "-":
                g["mob_type"] = entry["mob_type"]

    merged = list(grouped.values())
    for m in merged:
        m["features"].sort(key=lambda f: f["start"])

    return merged


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


@router.get("/samples/{sample_id}/export-all")
def export_sample_annotations_tsv(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Export all annotation results for a single sample as one TSV file."""
    from app.models.models import (
        SpeciesResult, MLSTResult, PlasmidResult,
        ProphageResult, IntegronResult, CRISPRResult, DefenseFinderResult,
        ICEResult, BacMetResult, PointMutationResult,
    )

    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    # Species & MLST for filename
    sp = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
    species_str = sp.species.replace(" ", "_") if sp and sp.species else "unknown"
    mlst_str = f"ST{mlst.sequence_type}" if mlst and mlst.sequence_type else "ST_unknown"
    filename = f"{sample.name}-{species_str}-{mlst_str}.tsv"

    # Build contig → location lookup from MOB-recon contig_report
    contig_location = {}  # contig_id -> "plasmid(cluster_id)" or "chromosome"
    contig_report = os.path.join(settings.RESULTS_DIR, str(sample_id), "plasmid", "mob_recon_out", "contig_report.txt")
    if os.path.exists(contig_report):
        with open(contig_report) as f:
            header = f.readline().strip().split("\t")
            for line in f:
                cols = line.strip().split("\t")
                if len(cols) < 6:
                    continue
                row = dict(zip(header, cols))
                cid = row.get("contig_id", "").split()[0]
                mol = row.get("molecule_type", "")
                if mol == "plasmid":
                    pid = row.get("primary_cluster_id", "")
                    contig_location[cid] = f"plasmid({pid})" if pid else "plasmid"
                else:
                    contig_location[cid] = "chromosome"

    def _loc(contig_str):
        if not contig_str:
            return ""
        cid = contig_str.split()[0]
        return contig_location.get(cid, "chromosome")

    rows = []

    # ARGs
    for a in db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all():
        rows.append([a.contig or "", _loc(a.contig), a.start or 0, a.end or 0,
                      a.gene, "ARG", a.drug_class or "", a.identity, a.coverage])

    # Virulence
    for v in db.query(VirulenceResult).filter(VirulenceResult.sample_id == sample_id).all():
        rows.append([v.contig or "", _loc(v.contig), v.start or 0, v.end or 0,
                      v.gene, "Virulence", v.category or "", v.identity, v.coverage])

    # BacMet
    for b in db.query(BacMetResult).filter(BacMetResult.sample_id == sample_id).all():
        rows.append([b.contig or "", _loc(b.contig), b.start or 0, b.end or 0,
                      b.gene, "BacMet", b.compound or "", b.identity, b.coverage])

    # Point mutations
    for pm in db.query(PointMutationResult).filter(PointMutationResult.sample_id == sample_id).all():
        rows.append(["", "", 0, 0,
                      pm.gene, "PointMutation", f"{pm.mutation} ({pm.drug_class or ''})", "", ""])

    # Prophages
    for p in db.query(ProphageResult).filter(ProphageResult.sample_id == sample_id).all():
        rows.append([p.contig or "", _loc(p.contig), p.start or 0, p.end or 0,
                      p.taxonomy or "prophage", "Prophage", f"score={p.virus_score or ''}", "", ""])

    # CRISPR
    for c in db.query(CRISPRResult).filter(CRISPRResult.sample_id == sample_id).all():
        rows.append([c.contig or "", _loc(c.contig), c.start or 0, c.end or 0,
                      c.crispr_id or "", "CRISPR", f"cas={c.cas_type or 'none'} spacers={c.num_spacers}", "", ""])

    # Defense systems
    for d in db.query(DefenseFinderResult).filter(DefenseFinderResult.sample_id == sample_id).all():
        rows.append([d.contig or "", _loc(d.contig), d.start or 0, d.end or 0,
                      d.system_type, "Defense", d.subtype or "", "", ""])

    # Integrons
    for ig in db.query(IntegronResult).filter(IntegronResult.sample_id == sample_id).all():
        rows.append([ig.contig or "", _loc(ig.contig), ig.start or 0, ig.end or 0,
                      ig.integron_id or "", "Integron", ig.integron_type or "", "", ""])

    # ICE
    for ice in db.query(ICEResult).filter(ICEResult.sample_id == sample_id).all():
        rows.append([ice.contig or "", _loc(ice.contig), ice.start or 0, ice.end or 0,
                      ice.ice_id or "", "ICE", f"{ice.ice_type or ''} integrase={ice.integrase or ''}", "", ""])

    # Plasmids (summary rows, no contig position — sorted last)
    for p in db.query(PlasmidResult).filter(PlasmidResult.sample_id == sample_id).all():
        rows.append(["~plasmid_summary", "plasmid", 0, 0,
                      p.plasmid_id or "", "Plasmid", f"replicon={p.replicon or ''} mob={p.mob_type or ''} {p.predicted_mobility or ''}", "", ""])

    # Sort by contig_id then start position
    rows.sort(key=lambda r: (r[0], r[2] if isinstance(r[2], int) else 0))

    output = io.StringIO()
    w = csv.writer(output, delimiter="\t")
    w.writerow(["contig_id", "location", "start", "end", "gene", "category", "detail", "identity", "coverage"])
    for row in rows:
        # Clean up plasmid summary contig marker
        if row[0] == "~plasmid_summary":
            row[0] = ""
            row[2] = ""
            row[3] = ""
        w.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/tab-separated-values",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
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


# ── Point Mutations ──────────────────────────────────────────────────────────

@router.get("/samples/{sample_id}/point-mutations")
def get_point_mutations(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.models import PointMutationResult
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    results = db.query(PointMutationResult).filter(PointMutationResult.sample_id == sample_id).all()
    return [
        {
            "id": str(r.id),
            "sample_id": str(r.sample_id),
            "gene": r.gene,
            "mutation": r.mutation,
            "drug_class": r.drug_class,
            "resistance": r.resistance,
            "nucleotide_change": r.nucleotide_change,
        }
        for r in results
    ]


# ── CRISPR, Defense Systems, ICE ─────────────────────────────────────────────

@router.get("/samples/{sample_id}/crispr")
def get_crispr_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.models import CRISPRResult
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    results = db.query(CRISPRResult).filter(CRISPRResult.sample_id == sample_id).all()
    return [
        {
            "id": str(r.id),
            "sample_id": str(r.sample_id),
            "crispr_id": r.crispr_id,
            "contig": r.contig,
            "start": r.start,
            "end": r.end,
            "cas_type": r.cas_type,
            "cas_genes": r.cas_genes,
            "num_spacers": r.num_spacers,
            "repeat_length": r.repeat_length,
            "spacer_length": r.spacer_length,
            "evidence_level": r.evidence_level,
        }
        for r in results
    ]


@router.get("/samples/{sample_id}/defense-systems")
def get_defense_systems(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.models import DefenseFinderResult
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    results = db.query(DefenseFinderResult).filter(DefenseFinderResult.sample_id == sample_id).all()
    return [
        {
            "id": str(r.id),
            "sample_id": str(r.sample_id),
            "system_type": r.system_type,
            "subtype": r.subtype,
            "genes": r.genes,
            "contig": r.contig,
            "start": r.start,
            "end": r.end,
            "protein_count": r.protein_count,
        }
        for r in results
    ]


@router.get("/samples/{sample_id}/ice")
def get_ice_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.models import ICEResult
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    results = db.query(ICEResult).filter(ICEResult.sample_id == sample_id).all()
    return [
        {
            "id": str(r.id),
            "sample_id": str(r.sample_id),
            "ice_id": r.ice_id,
            "ice_type": r.ice_type,
            "contig": r.contig,
            "start": r.start,
            "end": r.end,
            "length": r.length,
            "integrase": r.integrase,
            "arg_genes": r.arg_genes,
            "nearest_trna": r.nearest_trna,
        }
        for r in results
    ]


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
