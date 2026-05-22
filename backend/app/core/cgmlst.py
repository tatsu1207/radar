import json
import logging
import os
import subprocess
from typing import Optional

from app.config import settings
from app.models.models import CgMLSTResult, SpeciesResult

logger = logging.getLogger(__name__)

CONDA_CGMLST = "radar-cgmlst"

CGMLST_SCHEMAS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "databases", "cgmlst_schemas",
)

# Species to schema mapping (Enterobase / pubMLST schemas)
SPECIES_SCHEMA_MAP = {
    "escherichia coli": "ecoli",
    "salmonella enterica": "salmonella",
    "klebsiella pneumoniae": "klebsiella",
    "listeria monocytogenes": "listeria",
    "campylobacter jejuni": "campylobacter",
    "staphylococcus aureus": "saureus",
}


def run_cgmlst(
    sample_id: str,
    assembly_path: str,
    db,
    threads: int = 4,
) -> Optional[CgMLSTResult]:
    """Run chewBBACA cgMLST allelic profiling.

    Uses species-specific cgMLST schemas for high-resolution typing.
    """
    logger.info(f"Running cgMLST for sample {sample_id}")

    # Determine species
    species_result = db.query(SpeciesResult).filter(
        SpeciesResult.sample_id == sample_id
    ).first()

    if not species_result or not species_result.species:
        logger.info(f"No species ID for sample {sample_id}, skipping cgMLST")
        return None

    species_lower = species_result.species.lower()
    schema_key = None
    for sp_pattern, key in SPECIES_SCHEMA_MAP.items():
        if sp_pattern in species_lower:
            schema_key = key
            break

    if not schema_key:
        logger.info(f"No cgMLST schema for {species_result.species}")
        return None

    schema_dir = os.path.join(
        os.environ.get("RADAR_CGMLST_SCHEMAS", CGMLST_SCHEMAS),
        schema_key,
    )
    if not os.path.isdir(schema_dir):
        logger.warning(f"cgMLST schema not found at {schema_dir}")
        return None

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "cgmlst")
    os.makedirs(results_dir, exist_ok=True)

    # Prepare input: chewBBACA expects a directory of FASTA files or a list file
    input_list = os.path.join(results_dir, "input_list.txt")
    with open(input_list, "w") as f:
        f.write(assembly_path + "\n")

    output_dir = os.path.join(results_dir, "chewbbaca_output")

    cmd = [
        "conda", "run", "-n", CONDA_CGMLST,
        "chewBBACA.py", "AlleleCall",
        "-i", input_list,
        "-g", schema_dir,
        "-o", output_dir,
        "--cpu", str(threads),
        "--no-inferred",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"chewBBACA failed: {result.stderr[-1000:]}")

    # Parse results
    allelic_profile, loci_found, loci_total = _parse_chewbbaca_output(output_dir)

    # Delete existing result for re-runs
    existing = db.query(CgMLSTResult).filter(
        CgMLSTResult.sample_id == sample_id
    ).first()
    if existing:
        db.delete(existing)
        db.commit()

    cgmlst = CgMLSTResult(
        sample_id=sample_id,
        schema_name=schema_key,
        allelic_profile=allelic_profile,
        loci_found=loci_found,
        loci_total=loci_total,
    )
    db.add(cgmlst)
    db.commit()
    db.refresh(cgmlst)

    logger.info(
        f"cgMLST for {sample_id}: {loci_found}/{loci_total} loci found "
        f"(schema: {schema_key})"
    )
    return cgmlst


def _parse_chewbbaca_output(output_dir: str):
    """Parse chewBBACA AlleleCall results."""
    allelic_profile = {}
    loci_found = 0
    loci_total = 0

    # Find the results_alleles.tsv in the most recent run folder
    results_file = None
    if os.path.isdir(output_dir):
        for d in sorted(os.listdir(output_dir), reverse=True):
            candidate = os.path.join(output_dir, d, "results_alleles.tsv")
            if os.path.exists(candidate):
                results_file = candidate
                break

    if not results_file:
        return allelic_profile, loci_found, loci_total

    with open(results_file) as f:
        header = f.readline().strip().split("\t")
        values = f.readline().strip().split("\t")

    if len(header) < 2 or len(values) < 2:
        return allelic_profile, loci_found, loci_total

    # Skip first column (FILE) — rest are loci
    loci = header[1:]
    alleles = values[1:]
    loci_total = len(loci)

    for locus, allele in zip(loci, alleles):
        allelic_profile[locus] = allele
        # Count exact allele calls (integer = found)
        try:
            int(allele)
            loci_found += 1
        except ValueError:
            pass  # LNF, ASM, etc. = not found

    return allelic_profile, loci_found, loci_total
