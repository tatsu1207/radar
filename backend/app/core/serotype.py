import json
import logging
import os
import subprocess
from typing import Optional

from app.config import settings
from app.models.models import SerotypeResult, SpeciesResult

logger = logging.getLogger(__name__)

CONDA_SEROTYPE = "radar-sistr"

# Species patterns that trigger each serotyping tool
ECOLI_PATTERNS = ["escherichia coli", "e. coli"]
SALMONELLA_PATTERNS = ["salmonella"]
KLEBSIELLA_PATTERNS = ["klebsiella"]


def run_serotyping(
    sample_id: str,
    assembly_path: str,
    db,
    threads: int = 4,
) -> Optional[SerotypeResult]:
    """Run in silico serotyping based on species identification.

    Auto-selects the appropriate tool:
    - SerotypeFinder for E. coli (O:H typing)
    - SISTR for Salmonella (serovar prediction)
    - Kleborate for Klebsiella (K/O locus typing)
    """
    logger.info(f"Running serotyping for sample {sample_id}")

    # Get species ID
    species_result = db.query(SpeciesResult).filter(
        SpeciesResult.sample_id == sample_id
    ).first()

    if not species_result or not species_result.species:
        logger.info(f"No species ID for sample {sample_id}, skipping serotyping")
        return None

    species = species_result.species.lower()

    # Select tool based on species
    if any(p in species for p in ECOLI_PATTERNS):
        return _run_serotypefinder(sample_id, assembly_path, db, threads)
    elif any(p in species for p in SALMONELLA_PATTERNS):
        return _run_sistr(sample_id, assembly_path, db, threads)
    elif any(p in species for p in KLEBSIELLA_PATTERNS):
        return _run_kleborate(sample_id, assembly_path, db, threads)
    else:
        logger.info(f"No serotyping tool available for {species_result.species}")
        return None


def _run_serotypefinder(
    sample_id: str, assembly_path: str, db, threads: int
) -> Optional[SerotypeResult]:
    """Run SerotypeFinder for E. coli O:H typing."""
    logger.info(f"Running SerotypeFinder for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "serotype")
    os.makedirs(results_dir, exist_ok=True)

    cmd = [
        "conda", "run", "-n", CONDA_SEROTYPE,
        "serotypefinder",
        "-i", assembly_path,
        "-o", results_dir,
        "-x",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"SerotypeFinder failed: {result.stderr[-500:]}")

    # Parse results
    # Columns: Database  Gene  Serotype  Identity  Template/HSP  Contig  Position  Accession
    results_file = os.path.join(results_dir, "results_tab.tsv")
    o_antigen = None
    h_antigen = None

    if os.path.exists(results_file):
        with open(results_file) as f:
            for line in f:
                if line.startswith("#") or line.startswith("Database"):
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    db_name = parts[0].lower()
                    serotype_val = parts[2]  # Serotype column
                    if "o_type" in db_name:
                        o_antigen = serotype_val
                    elif "h_type" in db_name:
                        h_antigen = serotype_val

    serotype_str = f"{o_antigen}:{h_antigen}" if o_antigen and h_antigen else None
    return _save_result(sample_id, db, "serotypefinder",
                        serotype=serotype_str, o_antigen=o_antigen, h_antigen=h_antigen)


def _run_sistr(
    sample_id: str, assembly_path: str, db, threads: int
) -> Optional[SerotypeResult]:
    """Run SISTR for Salmonella serovar prediction."""
    logger.info(f"Running SISTR for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "serotype")
    os.makedirs(results_dir, exist_ok=True)

    output_file = os.path.join(results_dir, "sistr_output.json")

    cmd = [
        "conda", "run", "-n", CONDA_SEROTYPE,
        "sistr",
        "--qc",
        "-f", "json",
        "-o", output_file,
        "-t", str(threads),
        assembly_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"SISTR failed: {result.stderr[-500:]}")

    serovar = None
    o_antigen = None
    h_antigen = None
    details = {}

    if os.path.exists(output_file):
        with open(output_file) as f:
            data = json.load(f)
            if isinstance(data, list) and data:
                data = data[0]
            serovar = data.get("serovar", "")
            o_antigen = data.get("o_antigen", "")
            h_antigen = f"{data.get('h1', '')};{data.get('h2', '')}"
            details = {
                "serogroup": data.get("serogroup", ""),
                "cgmlst_subspecies": data.get("cgmlst_subspecies", ""),
                "qc_status": data.get("qc_status", ""),
            }

    return _save_result(sample_id, db, "sistr",
                        serotype=serovar, o_antigen=o_antigen, h_antigen=h_antigen,
                        serovar=serovar, details=details)


def _run_kleborate(
    sample_id: str, assembly_path: str, db, threads: int
) -> Optional[SerotypeResult]:
    """Run Kleborate for Klebsiella K/O locus typing."""
    logger.info(f"Running Kleborate for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "serotype")
    os.makedirs(results_dir, exist_ok=True)

    output_file = os.path.join(results_dir, "kleborate_output.tsv")

    cmd = [
        "conda", "run", "-n", CONDA_SEROTYPE,
        "kleborate",
        "-a", assembly_path,
        "-o", output_file,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Kleborate failed: {result.stderr[-500:]}")

    k_locus = None
    o_locus = None
    details = {}

    if os.path.exists(output_file):
        with open(output_file) as f:
            header = None
            for line in f:
                parts = line.strip().split("\t")
                if header is None:
                    header = parts
                    continue
                row = dict(zip(header, parts))
                k_locus = row.get("K_locus", "")
                o_locus = row.get("O_locus", "")
                details = {
                    "species": row.get("species", ""),
                    "ST": row.get("ST", ""),
                    "virulence_score": row.get("virulence_score", ""),
                    "resistance_score": row.get("resistance_score", ""),
                }
                break

    serotype_str = f"K{k_locus}:O{o_locus}" if k_locus and o_locus else None
    return _save_result(sample_id, db, "kleborate",
                        serotype=serotype_str, o_antigen=o_locus, k_locus=k_locus,
                        details=details)


def _save_result(sample_id, db, tool, serotype=None, o_antigen=None,
                 h_antigen=None, k_locus=None, serovar=None, details=None):
    """Save or update serotype result."""
    existing = db.query(SerotypeResult).filter(
        SerotypeResult.sample_id == sample_id
    ).first()
    if existing:
        db.delete(existing)
        db.commit()

    sr = SerotypeResult(
        sample_id=sample_id,
        tool=tool,
        serotype=serotype,
        o_antigen=o_antigen,
        h_antigen=h_antigen,
        k_locus=k_locus,
        serovar=serovar,
        details=details,
    )
    db.add(sr)
    db.commit()
    db.refresh(sr)

    logger.info(f"Serotyping ({tool}) for {sample_id}: {serotype}")
    return sr
