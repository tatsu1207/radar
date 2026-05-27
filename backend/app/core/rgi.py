import csv
import json
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import RGIResult

logger = logging.getLogger(__name__)

CONDA_RGI = "radar"


def run_rgi(
    sample_id: str,
    assembly_path: str,
    db,
    threads: int = 4,
) -> List[RGIResult]:
    """Run CARD RGI on the assembly for resistance gene detection.

    Third ARG database alongside AMRFinderPlus and ResFinder.
    Uses BLAST and HMM models against the Comprehensive Antibiotic
    Resistance Database (CARD).
    """
    logger.info(f"Running RGI for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "rgi")
    os.makedirs(results_dir, exist_ok=True)

    output_prefix = os.path.join(results_dir, "rgi_output")
    output_file = f"{output_prefix}.txt"

    cmd = [
        "conda", "run", "-n", CONDA_RGI,
        "rgi", "main",
        "--input_sequence", assembly_path,
        "--output_file", output_prefix,
        "--input_type", "contig",
        "--num_threads", str(threads),
        "--clean",
        "--alignment_tool", "BLAST",
        "--local",
    ]

    # RGI --local expects localDB/ in the current working directory
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, cwd=project_root)
    if result.returncode != 0:
        raise RuntimeError(f"RGI failed: {result.stderr[-1000:]}")

    # Delete existing results for re-runs
    db.query(RGIResult).filter(RGIResult.sample_id == sample_id).delete()
    db.commit()

    results = _parse_rgi_output(sample_id, output_file)

    for r in results:
        db.add(r)
    db.commit()

    logger.info(f"RGI found {len(results)} genes for sample {sample_id}")
    return results


def _parse_rgi_output(sample_id: str, output_file: str) -> List[RGIResult]:
    """Parse RGI tab-separated output."""
    results = []

    if not os.path.exists(output_file):
        return results

    with open(output_file) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            results.append(RGIResult(
                sample_id=sample_id,
                gene=row.get("Best_Hit_ARO", ""),
                drug_class=row.get("Drug Class", ""),
                resistance_mechanism=row.get("Resistance Mechanism", ""),
                amr_gene_family=row.get("AMR Gene Family", ""),
                model_type=row.get("Model_type", ""),
                identity=_safe_float(row.get("Best_Identities")),
                coverage=_safe_float(row.get("Percentage Length of Reference Sequence")),
                contig=row.get("Contig", ""),
                start=_safe_int(row.get("Start")),
                end=_safe_int(row.get("Stop")),
                cut_off=row.get("Cut_Off", ""),
            ))

    return results


def _safe_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
