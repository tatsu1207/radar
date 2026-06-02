import csv
import logging
import os
import subprocess
from typing import Dict, List

from app.config import settings
from app.models.models import MobilityResult, ARGResult

logger = logging.getLogger(__name__)

PROXIMITY_THRESHOLD = 5000  # bp


def _find_nearby_args(contig: str, start: int, end: int, arg_results: List[ARGResult]) -> List[Dict]:
    """Find ARGs within PROXIMITY_THRESHOLD bp of a mobility element on the same contig."""
    nearby = []
    for arg in arg_results:
        if arg.contig != contig:
            continue
        if arg.start is None or arg.end is None:
            continue
        if arg.start <= end and arg.end >= start:
            distance = 0
        else:
            distance = min(abs(arg.start - end), abs(start - arg.end))
        if distance <= PROXIMITY_THRESHOLD:
            nearby.append({
                "gene": arg.gene,
                "drug_class": arg.drug_class,
                "distance_bp": max(0, distance),
                "start": arg.start,
                "end": arg.end,
            })
    return nearby


def run_mefinder(sample_id: str, assembly_path: str, db) -> List[MobilityResult]:
    """Run MobileElementFinder for mobile element detection.

    Args:
        sample_id: UUID of the sample
        assembly_path: Path to the assembly FASTA
        db: SQLAlchemy session

    Returns:
        List of MobilityResult records created
    """
    logger.info(f"Running MobileElementFinder for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "mobility")
    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, "mefinder_output")

    temp_dir = os.path.join(results_dir, "tmp")
    os.makedirs(temp_dir, exist_ok=True)

    cmd = [
        "conda", "run", "-n", "radar-mefinder",
        "mefinder", "find",
        "--contig", assembly_path,
        "--temp-dir", temp_dir,
        output_path,
    ]

    logger.info(f"MobileElementFinder command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        raise RuntimeError(f"MobileElementFinder failed: {result.stderr[-2000:]}")

    arg_results = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    results = []

    # mefinder appends .csv to the output path
    csv_path = output_path + ".csv"
    if os.path.exists(csv_path):
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                contig = row.get("contig", "")
                start = _safe_int(row.get("start", ""))
                end = _safe_int(row.get("end", ""))
                element_name = row.get("name", row.get("type", "unknown"))
                element_type = row.get("type", "mobile_element")

                nearby = []
                if start is not None and end is not None:
                    nearby = _find_nearby_args(contig, start, end, arg_results)

                mr = MobilityResult(
                    sample_id=sample_id,
                    element_type=element_type,
                    family=element_name,
                    contig=contig,
                    start=start,
                    end=end,
                    nearby_args=nearby if nearby else None,
                )
                db.add(mr)
                results.append(mr)

    db.commit()
    logger.info(f"MobileElementFinder found {len(results)} elements for sample {sample_id}")
    return results


def _safe_int(val: str):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
