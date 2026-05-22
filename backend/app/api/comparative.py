"""API endpoints for project-level comparative analyses and new per-sample results."""

import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.models import (
    BaktaAnnotation,
    CgMLSTResult,
    ComparativeAnalysisJob,
    IntegronResult,
    JobStatus,
    MashtreeResult,
    PangenomeResult,
    PointMutationResult,
    Project,
    ResFinderResult,
    RGIResult,
    Sample,
    SerotypeResult,
    SNPPhylogenyResult,
    VFDBResult,
)

router = APIRouter(tags=["comparative"])


# ---------------------------------------------------------------------------
# Per-sample new result endpoints
# ---------------------------------------------------------------------------

@router.get("/samples/{sample_id}/resfinder")
def get_resfinder_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_sample(sample_id, db)
    return db.query(ResFinderResult).filter(ResFinderResult.sample_id == sample_id).all()


@router.get("/samples/{sample_id}/rgi")
def get_rgi_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_sample(sample_id, db)
    return db.query(RGIResult).filter(RGIResult.sample_id == sample_id).all()


@router.get("/samples/{sample_id}/vfdb")
def get_vfdb_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_sample(sample_id, db)
    return db.query(VFDBResult).filter(VFDBResult.sample_id == sample_id).all()


@router.get("/samples/{sample_id}/serotype")
def get_serotype_result(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_sample(sample_id, db)
    result = db.query(SerotypeResult).filter(SerotypeResult.sample_id == sample_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Serotype result not available")
    return result


@router.get("/samples/{sample_id}/cgmlst")
def get_cgmlst_result(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_sample(sample_id, db)
    result = db.query(CgMLSTResult).filter(CgMLSTResult.sample_id == sample_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="cgMLST result not available")
    return result


@router.get("/samples/{sample_id}/bakta")
def get_bakta_annotation(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_sample(sample_id, db)
    result = db.query(BaktaAnnotation).filter(BaktaAnnotation.sample_id == sample_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Bakta annotation not available")
    return result


@router.get("/samples/{sample_id}/species")
def get_species_result(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.models import SpeciesResult
    _check_sample(sample_id, db)
    result = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Species result not available")
    return result


@router.get("/samples/{sample_id}/mlst")
def get_mlst_result(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.models import MLSTResult
    _check_sample(sample_id, db)
    result = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="MLST result not available")
    return result


@router.get("/samples/{sample_id}/summary")
def get_sample_summary(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a compact summary of all key results for a sample.

    Returns species, MLST, serotype, ARG count, VF count, plasmid info,
    and assembly QC metrics in a single call.
    """
    from app.models.models import (
        ARGResult, SpeciesResult, MLSTResult, PlasmidResult,
        VirulenceResult, BacMetResult, AnalysisJob,
    )

    sample = _check_sample(sample_id, db)

    species = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
    serotype = db.query(SerotypeResult).filter(SerotypeResult.sample_id == sample_id).first()
    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    vfs = db.query(VirulenceResult).filter(VirulenceResult.sample_id == sample_id).all()
    plasmids = db.query(PlasmidResult).filter(PlasmidResult.sample_id == sample_id).all()
    bacmet = db.query(BacMetResult).filter(BacMetResult.sample_id == sample_id).all()

    # Get QUAST/BUSCO from report files
    import os
    from app.config import settings
    asm_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    quast_report = os.path.join(asm_dir, "quast", "report.tsv")
    quast_metrics = _parse_quast_file(quast_report)

    busco_dir = os.path.join(asm_dir, "busco", "busco_result")
    busco_metrics = _parse_busco_dir(busco_dir)

    # Drug classes
    drug_classes = set()
    for a in args:
        if a.drug_class:
            for dc in a.drug_class.split(";"):
                drug_classes.add(dc.strip())

    # VF genes
    vf_genes = [v.gene for v in vfs]

    # Predict drug resistance (exclude non-antibiotic categories)
    non_antibiotic = {
        "NA", "EFFLUX", "",
        "ARSENATE", "ARSENIC", "ARSENIC/GOLD",
        "COPPER", "MERCURY", "ZINC", "CADMIUM", "TELLURIUM", "SILVER",
        "QUATERNARY AMMONIUM", "BIOCIDE", "DISINFECTANT",
        "ACID", "HEAT",
    }
    clean_classes = set()
    for dc in drug_classes:
        dc_upper = dc.upper().strip()
        if dc_upper in non_antibiotic:
            continue
        # Skip if it looks like a metal/biocide
        if any(metal in dc_upper for metal in ("ARSEN", "MERCUR", "COPPER", "ZINC", "CADMIUM", "TELLURIT", "SILVER")):
            continue
        clean_classes.add(dc)
    drug_resistance = sorted(clean_classes)

    # Predict pathotype from VF profile
    pathotype_info = _predict_pathotype(vf_genes, species.species if species else None)

    return {
        "sample_id": str(sample_id),
        "sample_name": sample.name,
        "status": sample.status.value if sample.status else None,
        "species": species.species if species else None,
        "species_identity": species.identity if species else None,
        "mlst_scheme": mlst.scheme if mlst else None,
        "mlst_st": mlst.sequence_type if mlst else None,
        "serotype": serotype.serotype if serotype else None,
        "serotype_tool": serotype.tool if serotype else None,
        "arg_count": len(args),
        "arg_genes": [a.gene for a in args],
        "drug_classes": sorted(drug_classes),
        "drug_resistance": drug_resistance,
        "vf_count": len(vfs),
        "vf_genes": vf_genes,
        "pathotype": pathotype_info,
        "plasmids": [
            {
                "plasmid_id": p.plasmid_id,
                "replicon": p.replicon,
                "mobility": p.predicted_mobility or ("conjugative" if p.predicted_transferability else "non-mobilizable"),
            }
            for p in plasmids
        ],
        "quast": quast_metrics,
        "busco": busco_metrics,
        "bacmet": [
            {
                "gene": b.gene,
                "compound": b.compound,
                "identity": b.identity,
            }
            for b in bacmet
        ],
    }


def _predict_pathotype(vf_genes: list, species: str | None) -> dict:
    """Predict E. coli pathotype and potential diseases from virulence factor profile."""
    genes = set(g.lower() for g in vf_genes)

    # VF markers for E. coli pathotypes
    markers = {
        "adhesins_p_fimbriae": any(g.startswith("pap") for g in genes),
        "adhesins_type1_fimbriae": any(g.startswith("fim") for g in genes),
        "adhesins_s_fimbriae": any(g.startswith("sfa") for g in genes),
        "adhesins_afa": any(g.startswith("afa") for g in genes),
        "adhesins_iha": "iha" in genes,
        "toxin_hemolysin": any(g.startswith("hly") for g in genes),
        "toxin_cnf": any(g.startswith("cnf") for g in genes),
        "toxin_sat": "sat" in genes,
        "toxin_stx": any(g.startswith("stx") for g in genes),
        "toxin_lt": any(g in ("elta", "eltb", "lt") for g in genes),
        "toxin_st": any(g in ("sta", "stb", "sta1", "sta2", "estia", "estib") for g in genes),
        "siderophore_aerobactin": any(g.startswith("iuc") or g.startswith("iut") for g in genes),
        "siderophore_yersiniabactin": any(g.startswith("ybt") for g in genes),
        "siderophore_salmochelin": any(g.startswith("iro") for g in genes),
        "serum_resistance": "iss" in genes or any(g.startswith("trat") for g in genes),
        "capsule_k1": any(g.startswith("neub") or g.startswith("neuc") for g in genes),
        "invasin": any(g.startswith("ibea") or g.startswith("ibeb") for g in genes),
        "intimin": "eae" in genes,
        "bfp": any(g.startswith("bfp") for g in genes),
        "aggr": "aggr" in genes or any(g.startswith("agg") for g in genes),
        "senb": "senb" in genes,
    }

    pathotypes = []
    diseases = []
    evidence = []

    # UPEC (Uropathogenic E. coli)
    upec_score = sum([
        markers["adhesins_p_fimbriae"] * 3,
        markers["siderophore_aerobactin"] * 2,
        markers["siderophore_yersiniabactin"] * 2,
        markers["toxin_hemolysin"] * 2,
        markers["toxin_cnf"] * 1,
        markers["toxin_sat"] * 1,
        markers["adhesins_iha"] * 1,
        markers["serum_resistance"] * 1,
    ])
    if upec_score >= 3:
        pathotypes.append("UPEC (Uropathogenic)")
        diseases.extend(["Urinary tract infection (UTI)", "Pyelonephritis"])
        if markers["serum_resistance"] or markers["siderophore_aerobactin"]:
            diseases.append("Urosepsis / Bacteremia")
        ev = []
        if markers["adhesins_p_fimbriae"]: ev.append("P-fimbriae (papC/G)")
        if markers["siderophore_aerobactin"]: ev.append("Aerobactin (iuc/iut)")
        if markers["siderophore_yersiniabactin"]: ev.append("Yersiniabactin (ybt)")
        if markers["toxin_hemolysin"]: ev.append("Hemolysin (hlyA)")
        if markers["toxin_cnf"]: ev.append("CNF1 toxin")
        if markers["toxin_sat"]: ev.append("SAT toxin")
        evidence.extend(ev)

    # NMEC (Neonatal Meningitis E. coli)
    if markers["capsule_k1"] or markers["invasin"]:
        pathotypes.append("NMEC (Neonatal Meningitis)")
        diseases.append("Neonatal meningitis")

    # ExPEC (Extraintestinal Pathogenic)
    expec_markers = sum([
        markers["adhesins_p_fimbriae"],
        markers["adhesins_s_fimbriae"],
        markers["adhesins_afa"],
        markers["siderophore_aerobactin"],
        markers["toxin_hemolysin"],
        markers["capsule_k1"],
    ])
    if expec_markers >= 2 and "UPEC" not in str(pathotypes):
        pathotypes.append("ExPEC (Extraintestinal)")
        diseases.extend(["Bacteremia", "Wound infection", "Pneumonia"])

    # EHEC/STEC
    if markers["toxin_stx"]:
        pathotypes.append("STEC/EHEC (Shiga toxin-producing)")
        diseases.extend(["Hemorrhagic colitis", "Hemolytic uremic syndrome (HUS)"])
        if markers["intimin"]: evidence.append("Intimin (eae)")
        evidence.append("Shiga toxin (stx)")

    # ETEC
    if markers["toxin_lt"] or markers["toxin_st"]:
        pathotypes.append("ETEC (Enterotoxigenic)")
        diseases.append("Traveler's diarrhea / Watery diarrhea")

    # EPEC
    if markers["intimin"] and markers["bfp"] and not markers["toxin_stx"]:
        pathotypes.append("EPEC (Enteropathogenic)")
        diseases.append("Infantile diarrhea")

    # EAEC
    if markers["aggr"]:
        pathotypes.append("EAEC (Enteroaggregative)")
        diseases.append("Persistent diarrhea")

    # If we have serum resistance + siderophores but no clear pathotype
    if not pathotypes and (markers["serum_resistance"] or markers["siderophore_aerobactin"]):
        pathotypes.append("Potential ExPEC")
        diseases.append("Opportunistic infection")

    # Non-E. coli: generic assessment
    if species and "escherichia" not in (species or "").lower() and "e. coli" not in (species or "").lower():
        if markers["toxin_hemolysin"] or markers["serum_resistance"]:
            diseases.append("Invasive infection")
        if markers["siderophore_aerobactin"] or markers["siderophore_yersiniabactin"]:
            diseases.append("Systemic infection (iron acquisition)")
        if not pathotypes:
            pathotypes.append("Virulence factors detected")

    return {
        "pathotypes": pathotypes,
        "predicted_diseases": list(dict.fromkeys(diseases)),  # deduplicate preserving order
        "key_evidence": evidence,
        "vf_marker_summary": {k: v for k, v in markers.items() if v},
    }


def _parse_quast_log(log: str | None) -> dict | None:
    """Extract QUAST metrics from job log string."""
    if not log:
        return None
    import re
    metrics = {}
    # Try to parse key metrics from the log
    patterns = {
        "total_length": r"Total length[^:]*:\s*([\d,]+)",
        "num_contigs": r"# contigs[^:]*:\s*(\d+)",
        "n50": r"N50[^:]*:\s*([\d,]+)",
        "gc_percent": r"GC \(%\)[^:]*:\s*([\d.]+)",
        "largest_contig": r"Largest contig[^:]*:\s*([\d,]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, log, re.IGNORECASE)
        if match:
            val = match.group(1).replace(",", "")
            try:
                metrics[key] = float(val) if "." in val else int(val)
            except ValueError:
                pass

    # Also try JSON-like format: QUAST complete: {...}
    json_match = re.search(r"QUAST complete:\s*(\{.*\})", log)
    if json_match:
        import json
        try:
            metrics = json.loads(json_match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    return metrics if metrics else None


def _parse_busco_log(log: str | None) -> dict | None:
    """Extract BUSCO metrics from job log string."""
    if not log:
        return None
    import re
    metrics = {}
    # C:98.5%[S:97.2%,D:1.3%],F:0.5%,M:1.0%
    busco_match = re.search(
        r"C:([\d.]+)%\[S:([\d.]+)%,D:([\d.]+)%\],F:([\d.]+)%,M:([\d.]+)%",
        log
    )
    if busco_match:
        metrics = {
            "complete": float(busco_match.group(1)),
            "single_copy": float(busco_match.group(2)),
            "duplicated": float(busco_match.group(3)),
            "fragmented": float(busco_match.group(4)),
            "missing": float(busco_match.group(5)),
        }
    return metrics if metrics else None


def _parse_quast_file(report_path: str) -> dict | None:
    """Parse QUAST report.tsv file directly."""
    import os
    if not os.path.exists(report_path):
        return None
    metrics = {}
    key_map = {
        "# contigs": "num_contigs",
        "Total length": "total_length",
        "Largest contig": "largest_contig",
        "N50": "n50",
        "GC (%)": "gc_percent",
    }
    with open(report_path) as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                label = parts[0].strip()
                val = parts[1].strip()
                for prefix, key in key_map.items():
                    if label.startswith(prefix) and key not in metrics:
                        try:
                            metrics[key] = float(val) if "." in val else int(val)
                        except ValueError:
                            pass
    return metrics if metrics else None


def _parse_busco_dir(busco_dir: str) -> dict | None:
    """Parse BUSCO short_summary file from result directory."""
    import os, re
    if not os.path.isdir(busco_dir):
        return None
    for root, dirs, files in os.walk(busco_dir):
        for fname in files:
            if fname.startswith("short_summary"):
                with open(os.path.join(root, fname)) as f:
                    text = f.read()
                busco_match = re.search(
                    r"C:([\d.]+)%\[S:([\d.]+)%,D:([\d.]+)%\],F:([\d.]+)%,M:([\d.]+)%",
                    text
                )
                if busco_match:
                    return {
                        "complete": float(busco_match.group(1)),
                        "single_copy": float(busco_match.group(2)),
                        "duplicated": float(busco_match.group(3)),
                        "fragmented": float(busco_match.group(4)),
                        "missing": float(busco_match.group(5)),
                    }
    return None


@router.get("/samples/{sample_id}/crispr")
def get_crispr_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.models import CRISPRResult
    _check_sample(sample_id, db)
    return db.query(CRISPRResult).filter(CRISPRResult.sample_id == sample_id).all()


@router.get("/samples/{sample_id}/defense-systems")
def get_defense_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.models import DefenseFinderResult
    _check_sample(sample_id, db)
    return db.query(DefenseFinderResult).filter(DefenseFinderResult.sample_id == sample_id).all()


@router.get("/samples/{sample_id}/ice")
def get_ice_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.models import ICEResult
    _check_sample(sample_id, db)
    return db.query(ICEResult).filter(ICEResult.sample_id == sample_id).all()


@router.get("/samples/{sample_id}/integrons")
def get_integron_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_sample(sample_id, db)
    return db.query(IntegronResult).filter(IntegronResult.sample_id == sample_id).all()


@router.get("/samples/{sample_id}/point-mutations")
def get_point_mutation_results(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_sample(sample_id, db)
    return db.query(PointMutationResult).filter(PointMutationResult.sample_id == sample_id).all()


@router.get("/samples/{sample_id}/args/concordance")
def get_arg_concordance(sample_id: uuid.UUID, db: Session = Depends(get_db)):
    """Multi-database ARG concordance view.

    Returns ARGs grouped by gene name with detection status across
    AMRFinderPlus, ResFinder, and CARD/RGI databases.
    """
    from app.models.models import ARGResult

    _check_sample(sample_id, db)

    amr_results = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    resfinder_results = db.query(ResFinderResult).filter(ResFinderResult.sample_id == sample_id).all()
    rgi_results = db.query(RGIResult).filter(RGIResult.sample_id == sample_id).all()

    # Build concordance by normalized gene name
    concordance = {}

    for r in amr_results:
        key = r.gene.lower()
        if key not in concordance:
            concordance[key] = {"gene": r.gene, "drug_class": r.drug_class, "amrfinderplus": None, "resfinder": None, "rgi": None}
        concordance[key]["amrfinderplus"] = {"identity": r.identity, "coverage": r.coverage}

    for r in resfinder_results:
        key = r.gene.lower()
        if key not in concordance:
            concordance[key] = {"gene": r.gene, "drug_class": r.drug_class or r.phenotype, "amrfinderplus": None, "resfinder": None, "rgi": None}
        concordance[key]["resfinder"] = {"identity": r.identity, "coverage": r.coverage}

    for r in rgi_results:
        key = r.gene.lower()
        if key not in concordance:
            concordance[key] = {"gene": r.gene, "drug_class": r.drug_class, "amrfinderplus": None, "resfinder": None, "rgi": None}
        concordance[key]["rgi"] = {"identity": r.identity, "coverage": r.coverage, "cut_off": r.cut_off}

    return list(concordance.values())


# ---------------------------------------------------------------------------
# Project-level comparative analysis endpoints
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/comparative/pangenome")
def start_pangenome(
    project_id: uuid.UUID,
    sample_ids: Optional[List[str]] = None,
    db: Session = Depends(get_db),
):
    """Start Panaroo pan-genome analysis for project samples."""
    project = _check_project(project_id, db)
    ids = sample_ids or _get_completed_sample_ids(project_id, db)
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 completed samples")

    job = _create_comparative_job(project_id, "pangenome", ids, db)

    from app.core.pangenome import run_pangenome
    run_pangenome.delay(str(project_id), str(job.id), ids)
    return {"job_id": str(job.id), "status": "started", "sample_count": len(ids)}


@router.post("/projects/{project_id}/comparative/snp-tree")
def start_snp_tree(
    project_id: uuid.UUID,
    reference_sample_id: Optional[str] = None,
    run_gubbins: bool = True,
    sample_ids: Optional[List[str]] = None,
    db: Session = Depends(get_db),
):
    """Start Snippy core-genome SNP phylogeny for project samples."""
    project = _check_project(project_id, db)
    ids = sample_ids or _get_completed_sample_ids(project_id, db)
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 completed samples")

    params = {"reference_sample_id": reference_sample_id, "run_gubbins": run_gubbins}
    job = _create_comparative_job(project_id, "snp_tree", ids, db, params)

    from app.core.snp_phylogeny import run_snp_phylogeny
    run_snp_phylogeny.delay(str(project_id), str(job.id), ids, reference_sample_id, run_gubbins)
    return {"job_id": str(job.id), "status": "started", "sample_count": len(ids)}


@router.post("/projects/{project_id}/comparative/mashtree")
def start_mashtree(
    project_id: uuid.UUID,
    sample_ids: Optional[List[str]] = None,
    db: Session = Depends(get_db),
):
    """Start Mashtree phylogenomic distance tree for project samples."""
    project = _check_project(project_id, db)
    ids = sample_ids or _get_completed_sample_ids(project_id, db)
    if len(ids) < 3:
        raise HTTPException(status_code=400, detail="Need at least 3 completed samples")

    job = _create_comparative_job(project_id, "mashtree", ids, db)

    from app.core.mashtree import run_mashtree
    run_mashtree.delay(str(project_id), str(job.id), ids)
    return {"job_id": str(job.id), "status": "started", "sample_count": len(ids)}


@router.get("/projects/{project_id}/comparative/jobs")
def list_comparative_jobs(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """List all comparative analysis jobs for a project."""
    _check_project(project_id, db)
    jobs = db.query(ComparativeAnalysisJob).filter(
        ComparativeAnalysisJob.project_id == project_id
    ).order_by(ComparativeAnalysisJob.started_at.desc()).all()
    return jobs


@router.get("/projects/{project_id}/comparative/jobs/{job_id}")
def get_comparative_job(project_id: uuid.UUID, job_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get details of a specific comparative analysis job."""
    job = db.query(ComparativeAnalysisJob).filter(
        ComparativeAnalysisJob.id == job_id,
        ComparativeAnalysisJob.project_id == project_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/projects/{project_id}/comparative/pangenome/latest")
def get_latest_pangenome(project_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_project(project_id, db)
    result = db.query(PangenomeResult).filter(
        PangenomeResult.project_id == project_id
    ).order_by(PangenomeResult.created_at.desc()).first()
    if not result:
        raise HTTPException(status_code=404, detail="No pan-genome result available")
    return result


@router.get("/projects/{project_id}/comparative/snp-tree/latest")
def get_latest_snp_tree(project_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_project(project_id, db)
    result = db.query(SNPPhylogenyResult).filter(
        SNPPhylogenyResult.project_id == project_id
    ).order_by(SNPPhylogenyResult.created_at.desc()).first()
    if not result:
        raise HTTPException(status_code=404, detail="No SNP phylogeny result available")
    return result


@router.get("/projects/{project_id}/comparative/mashtree/latest")
def get_latest_mashtree(project_id: uuid.UUID, db: Session = Depends(get_db)):
    _check_project(project_id, db)
    result = db.query(MashtreeResult).filter(
        MashtreeResult.project_id == project_id
    ).order_by(MashtreeResult.created_at.desc()).first()
    if not result:
        raise HTTPException(status_code=404, detail="No Mashtree result available")
    return result


@router.get("/projects/{project_id}/comparative/tree/{job_id}/newick")
def get_tree_newick(project_id: uuid.UUID, job_id: uuid.UUID, db: Session = Depends(get_db)):
    """Download Newick tree file for a comparative analysis."""
    job = db.query(ComparativeAnalysisJob).filter(
        ComparativeAnalysisJob.id == job_id,
        ComparativeAnalysisJob.project_id == project_id,
    ).first()
    if not job or not job.result_dir:
        raise HTTPException(status_code=404, detail="Job not found")

    # Find newick file
    for fname in os.listdir(job.result_dir):
        if fname.endswith(".nwk") or fname.endswith(".tre"):
            return FileResponse(
                os.path.join(job.result_dir, fname),
                media_type="text/plain",
                filename=fname,
            )
    raise HTTPException(status_code=404, detail="Newick file not found")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_sample(sample_id, db):
    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return sample


def _check_project(project_id, db):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _get_completed_sample_ids(project_id, db) -> List[str]:
    from app.models.models import SampleStatus
    samples = db.query(Sample).filter(
        Sample.project_id == project_id,
        Sample.status == SampleStatus.complete,
    ).all()
    return [str(s.id) for s in samples]


def _create_comparative_job(project_id, analysis_type, sample_ids, db, parameters=None):
    job = ComparativeAnalysisJob(
        project_id=project_id,
        analysis_type=analysis_type,
        status=JobStatus.pending,
        sample_ids=sample_ids,
        parameters=parameters,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
