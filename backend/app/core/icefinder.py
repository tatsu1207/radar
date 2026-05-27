import csv
import json
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import ICEResult

logger = logging.getLogger(__name__)

CONDA_ICE = "radar"


def run_icefinder(
    sample_id: str,
    assembly_path: str,
    db,
    threads: int = 4,
) -> List[ICEResult]:
    """Run ICEfinder for integrative and conjugative element detection.

    Detects ICEs, IMEs (integrative mobilizable elements),
    CIMEs (cis-mobilizable elements), and AICEs (actinomycete ICEs).
    """
    logger.info(f"Running ICEfinder for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "icefinder")
    os.makedirs(results_dir, exist_ok=True)

    # ICEfinder requires GenBank format — use Bakta output or convert
    gbk_path = _get_or_convert_gbk(sample_id, assembly_path, results_dir)
    if not gbk_path:
        logger.warning("No GenBank file available for ICEfinder, skipping")
        return []

    output_file = os.path.join(results_dir, "ICEfinder_results.tsv")

    cmd = [
        "conda", "run", "-n", CONDA_ICE,
        "ICEfinder",
        "-i", gbk_path,
        "-o", results_dir,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        # ICEfinder may not be available as CLI — try VICEdb/ICEberg approach
        logger.warning(f"ICEfinder CLI failed, trying alternative: {result.stderr[-300:]}")
        return _run_ice_blast_approach(sample_id, assembly_path, db, results_dir, threads)

    # Delete existing results for re-runs
    db.query(ICEResult).filter(ICEResult.sample_id == sample_id).delete()
    db.commit()

    results = _parse_icefinder(sample_id, results_dir)

    for r in results:
        db.add(r)
    db.commit()

    logger.info(f"ICEfinder found {len(results)} ICEs for sample {sample_id}")
    return results


def _run_ice_blast_approach(
    sample_id: str,
    assembly_path: str,
    db,
    results_dir: str,
    threads: int,
) -> List[ICEResult]:
    """Fallback: BLAST against ICEberg database for ICE detection."""
    iceberg_db = os.environ.get(
        "RADAR_ICEBERG_DB",
        os.path.join(os.path.dirname(settings.RESULTS_DIR), "databases", "iceberg_db"),
    )

    if not os.path.exists(iceberg_db):
        logger.info("ICEberg database not found, skipping ICE detection")
        return []

    output_file = os.path.join(results_dir, "ice_blast.tsv")

    cmd = [
        "conda", "run", "-n", CONDA_ICE,
        "blastn",
        "-query", assembly_path,
        "-db", iceberg_db,
        "-out", output_file,
        "-outfmt", "6 qseqid sseqid pident length qstart qend sstart send evalue bitscore stitle",
        "-evalue", "1e-10",
        "-num_threads", str(threads),
        "-max_target_seqs", "5",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        logger.warning(f"ICEberg BLAST failed: {result.stderr[-300:]}")
        return []

    db.query(ICEResult).filter(ICEResult.sample_id == sample_id).delete()
    db.commit()

    results = _parse_ice_blast(sample_id, output_file)

    for r in results:
        db.add(r)
    db.commit()

    return results


def _parse_icefinder(sample_id: str, results_dir: str) -> List[ICEResult]:
    """Parse ICEfinder output."""
    results = []

    for fname in os.listdir(results_dir):
        if not fname.endswith(".tsv") and not fname.endswith(".txt"):
            continue
        fpath = os.path.join(results_dir, fname)
        try:
            with open(fpath) as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    ice_type = row.get("Type", row.get("type", "ICE"))
                    results.append(ICEResult(
                        sample_id=sample_id,
                        ice_id=row.get("ICE_id", row.get("ID", "")),
                        ice_type=ice_type,
                        contig=row.get("Contig", row.get("Replicon", "")),
                        start=_safe_int(row.get("Start", row.get("start"))),
                        end=_safe_int(row.get("End", row.get("end"))),
                        length=_safe_int(row.get("Length", row.get("length"))),
                        integrase=row.get("Integrase", None),
                        arg_genes=None,
                        nearest_trna=row.get("tRNA", None),
                    ))
        except Exception:
            continue

    return results


def _parse_ice_blast(sample_id: str, blast_file: str) -> List[ICEResult]:
    """Parse BLAST results against ICEberg database."""
    results = []
    if not os.path.exists(blast_file):
        return results

    seen = set()
    with open(blast_file) as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 11:
                continue
            qseqid, sseqid, pident, length = parts[0], parts[1], float(parts[2]), int(parts[3])
            qstart, qend = int(parts[4]), int(parts[5])
            stitle = parts[10] if len(parts) > 10 else sseqid

            # Filter: >80% identity, >1000bp alignment
            if pident < 80 or length < 1000:
                continue

            key = f"{qseqid}:{qstart}-{qend}"
            if key in seen:
                continue
            seen.add(key)

            results.append(ICEResult(
                sample_id=sample_id,
                ice_id=sseqid,
                ice_type="ICE",
                contig=qseqid,
                start=qstart,
                end=qend,
                length=abs(qend - qstart) + 1,
                integrase=None,
                arg_genes=None,
                nearest_trna=None,
            ))

    return results


def _get_or_convert_gbk(sample_id: str, assembly_path: str, results_dir: str) -> str:
    """Get GenBank file from Bakta or return None."""
    bakta_gbk = os.path.join(settings.RESULTS_DIR, str(sample_id), "bakta", "annotation.gbff")
    if os.path.exists(bakta_gbk):
        return bakta_gbk
    return None


def _safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
