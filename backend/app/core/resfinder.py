import csv
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import ResFinderResult

logger = logging.getLogger(__name__)

CONDA_RESFINDER = "radar-resfinder"
RESFINDER_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "databases", "resfinder_db",
)


def run_resfinder(
    sample_id: str,
    assembly_path: str,
    db,
    min_identity: float = 80.0,
    min_coverage: float = 60.0,
    threads: int = 4,
) -> List[ResFinderResult]:
    """Run ResFinder on the assembly for resistance gene detection.

    Uses the ResFinder database as a second ARG screening source
    alongside AMRFinderPlus.
    """
    logger.info(f"Running ResFinder for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "resfinder")
    os.makedirs(results_dir, exist_ok=True)

    db_path = os.environ.get("RADAR_RESFINDER_DB", RESFINDER_DB)
    if not os.path.isdir(db_path):
        raise RuntimeError(
            f"ResFinder database not found at {db_path}. "
            "Clone: git clone https://bitbucket.org/genomicepidemiology/resfinder_db.git"
        )

    output_path = os.path.join(results_dir, "ResFinder_results_tab.txt")

    cmd = [
        "conda", "run", "-n", CONDA_RESFINDER,
        "python", "-m", "resfinder",
        "-ifa", assembly_path,
        "-o", results_dir,
        "-db_res", db_path,
        "--min_cov", str(min_coverage / 100),
        "--threshold", str(min_identity / 100),
        "-acq",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"ResFinder failed: {result.stderr[-1000:]}")

    # Delete existing results for re-runs
    db.query(ResFinderResult).filter(
        ResFinderResult.sample_id == sample_id
    ).delete()
    db.commit()

    results = _parse_resfinder_output(sample_id, results_dir)

    for r in results:
        db.add(r)
    db.commit()

    logger.info(f"ResFinder found {len(results)} genes for sample {sample_id}")
    return results


def _parse_resfinder_output(sample_id: str, results_dir: str) -> List[ResFinderResult]:
    """Parse ResFinder tab-separated output."""
    results = []
    tab_file = os.path.join(results_dir, "ResFinder_results_tab.txt")

    if not os.path.exists(tab_file):
        return results

    with open(tab_file) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            results.append(ResFinderResult(
                sample_id=sample_id,
                gene=row.get("Resistance gene", ""),
                drug_class=row.get("Phenotype", ""),
                phenotype=row.get("Phenotype", ""),
                identity=_safe_float(row.get("Identity")),
                coverage=_safe_float(row.get("Query / Template length")),
                contig=row.get("Contig", ""),
                start=_safe_int(row.get("Position in contig", "").split("..")[0] if ".." in row.get("Position in contig", "") else None),
                end=_safe_int(row.get("Position in contig", "").split("..")[-1] if ".." in row.get("Position in contig", "") else None),
                accession=row.get("Accession no.", ""),
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
