import csv
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import VFDBResult

logger = logging.getLogger(__name__)

CONDA_BLAST = "radar-blast"  # ABRicate/BLAST tools


def run_vfdb(
    sample_id: str,
    assembly_path: str,
    db,
    min_identity: float = 80.0,
    min_coverage: float = 60.0,
    threads: int = 4,
) -> List[VFDBResult]:
    """Run ABRicate with VFDB database for virulence factor screening.

    Complements AMRFinderPlus virulence detection with the comprehensive
    Virulence Factor Database.
    """
    logger.info(f"Running ABRicate VFDB for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "vfdb")
    os.makedirs(results_dir, exist_ok=True)

    output_file = os.path.join(results_dir, "vfdb_results.tsv")

    cmd = [
        "conda", "run", "-n", CONDA_BLAST,
        "abricate",
        "--db", "vfdb",
        "--minid", str(min_identity),
        "--mincov", str(min_coverage),
        assembly_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"ABRicate VFDB failed: {result.stderr[-1000:]}")

    # Write output
    with open(output_file, "w") as f:
        f.write(result.stdout)

    # Delete existing results for re-runs
    db.query(VFDBResult).filter(VFDBResult.sample_id == sample_id).delete()
    db.commit()

    results = _parse_abricate_output(sample_id, output_file)

    for r in results:
        db.add(r)
    db.commit()

    logger.info(f"VFDB found {len(results)} virulence factors for sample {sample_id}")
    return results


def _parse_abricate_output(sample_id: str, output_file: str) -> List[VFDBResult]:
    """Parse ABRicate tab-separated output."""
    results = []

    if not os.path.exists(output_file):
        return results

    with open(output_file) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            results.append(VFDBResult(
                sample_id=sample_id,
                gene=row.get("GENE", ""),
                product=row.get("PRODUCT", ""),
                vf_class=row.get("RESISTANCE", ""),  # ABRicate uses RESISTANCE column for VF class
                identity=_safe_float(row.get("%IDENTITY")),
                coverage=_safe_float(row.get("%COVERAGE")),
                contig=row.get("SEQUENCE", ""),
                start=_safe_int(row.get("START")),
                end=_safe_int(row.get("END")),
                accession=row.get("ACCESSION", ""),
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
