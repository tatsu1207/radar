import csv
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import DefenseFinderResult

logger = logging.getLogger(__name__)

CONDA_DEFENSE = "radar"


def run_defensefinder(
    sample_id: str,
    assembly_path: str,
    db,
    threads: int = 4,
) -> List[DefenseFinderResult]:
    """Run DefenseFinder for bacterial defense system detection.

    Detects restriction-modification (RM) systems, abortive infection (Abi),
    BREX, DISARM, Zorya, Thoeris, retrons, CBASS, and other defense systems.
    Also classifies CRISPR-Cas systems by subtype.
    """
    logger.info(f"Running DefenseFinder for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "defensefinder")
    os.makedirs(results_dir, exist_ok=True)

    # DefenseFinder requires protein sequences — run Prodigal first if needed
    proteins_path = _get_or_run_prodigal(sample_id, assembly_path, results_dir, threads)
    if not proteins_path:
        raise RuntimeError("Could not obtain protein sequences for DefenseFinder")

    cmd = [
        "conda", "run", "-n", CONDA_DEFENSE,
        "defense-finder", "run",
        proteins_path,
        "-o", results_dir,
        "--workers", str(threads),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"DefenseFinder failed: {result.stderr[-1000:]}")

    # Delete existing results for re-runs
    db.query(DefenseFinderResult).filter(
        DefenseFinderResult.sample_id == sample_id
    ).delete()
    db.commit()

    results = _parse_defensefinder(sample_id, results_dir)

    for r in results:
        db.add(r)
    db.commit()

    logger.info(f"DefenseFinder found {len(results)} defense systems for sample {sample_id}")
    return results


def _get_or_run_prodigal(sample_id: str, assembly_path: str, results_dir: str, threads: int) -> str:
    """Get protein FASTA from Bakta output or run Prodigal."""
    # Check Bakta output first
    bakta_faa = os.path.join(settings.RESULTS_DIR, str(sample_id), "bakta", "annotation.faa")
    if os.path.exists(bakta_faa):
        return bakta_faa

    # Check Prodigal output
    prodigal_faa = os.path.join(settings.RESULTS_DIR, str(sample_id), "prodigal", "genes.faa")
    if os.path.exists(prodigal_faa):
        return prodigal_faa

    # Run Prodigal
    prodigal_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "prodigal")
    os.makedirs(prodigal_dir, exist_ok=True)
    faa_path = os.path.join(prodigal_dir, "genes.faa")

    cmd = [
        "conda", "run", "-n", "radar",
        "prodigal",
        "-i", assembly_path,
        "-a", faa_path,
        "-p", "meta",
        "-q",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.warning(f"Prodigal failed: {result.stderr[-500:]}")
        return None

    return faa_path if os.path.exists(faa_path) else None


def _parse_defensefinder(sample_id: str, results_dir: str) -> List[DefenseFinderResult]:
    """Parse DefenseFinder output TSV files."""
    results = []

    # DefenseFinder produces defense_finder_systems.tsv
    systems_file = None
    for f in os.listdir(results_dir):
        if f.endswith("defense_finder_systems.tsv") or f == "defense_finder_systems.tsv":
            systems_file = os.path.join(results_dir, f)
            break

    if not systems_file or not os.path.exists(systems_file):
        # Try subdirectory
        for d in os.listdir(results_dir):
            candidate = os.path.join(results_dir, d, "defense_finder_systems.tsv")
            if os.path.exists(candidate):
                systems_file = candidate
                break

    if not systems_file or not os.path.exists(systems_file):
        return results

    # Also load genes file for gene details
    genes_by_system = _load_defense_genes(results_dir)

    with open(systems_file) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            sys_id = row.get("sys_id", "")
            system_type = row.get("type", row.get("sys_type", ""))
            subtype = row.get("subtype", "")

            gene_list = genes_by_system.get(sys_id, [])

            results.append(DefenseFinderResult(
                sample_id=sample_id,
                system_type=system_type,
                subtype=subtype or None,
                genes=gene_list if gene_list else None,
                contig=row.get("seq_id", None),
                start=_safe_int(row.get("start")),
                end=_safe_int(row.get("end")),
                protein_count=len(gene_list) if gene_list else _safe_int(row.get("protein_number")),
            ))

    return results


def _load_defense_genes(results_dir: str) -> dict:
    """Load defense_finder_genes.tsv and group by system ID."""
    genes_by_system = {}

    genes_file = None
    for f in os.listdir(results_dir):
        if "defense_finder_genes.tsv" in f:
            genes_file = os.path.join(results_dir, f)
            break
    if not genes_file:
        for d in os.listdir(results_dir):
            candidate = os.path.join(results_dir, d, "defense_finder_genes.tsv")
            if os.path.exists(candidate):
                genes_file = candidate
                break

    if not genes_file or not os.path.exists(genes_file):
        return genes_by_system

    with open(genes_file) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            sys_id = row.get("sys_id", "")
            gene_name = row.get("hit_id", row.get("gene_name", ""))
            if sys_id not in genes_by_system:
                genes_by_system[sys_id] = []
            genes_by_system[sys_id].append(gene_name)

    return genes_by_system


def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
