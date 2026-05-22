import csv
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import ProphageResult, ARGResult

logger = logging.getLogger(__name__)

CONDA_GENOMAD = "radar-genomad"
GENOMAD_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "databases", "genomad_db")


def run_genomad(sample_id: str, assembly_path: str, db, threads: int = 4) -> List[ProphageResult]:
    """Run geNomad for prophage and plasmid detection.

    Identifies viral/prophage regions in the assembly, then cross-references
    ARGs to mark prophage-borne genes.
    """
    logger.info(f"Running geNomad for sample {sample_id}")

    # Delete existing results to allow re-runs
    from app.models.models import ProphageResult as PR
    db.query(PR).filter(PR.sample_id == sample_id).delete()
    db.commit()

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "genomad")
    os.makedirs(results_dir, exist_ok=True)

    # Determine database path
    db_path = GENOMAD_DB
    env_db = os.environ.get("RADAR_GENOMAD_DB")
    if env_db and os.path.isdir(env_db):
        db_path = env_db

    if not os.path.isdir(db_path):
        raise RuntimeError(f"geNomad database not found at {db_path}. Run: genomad download-database <path>")

    cmd = [
        "conda", "run", "-n", CONDA_GENOMAD,
        "genomad", "end-to-end",
        assembly_path,
        results_dir,
        db_path,
        "--threads", str(threads),
        "--cleanup",
    ]

    logger.info(f"geNomad command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

    if result.returncode != 0:
        raise RuntimeError(f"geNomad failed: {result.stderr[-2000:]}")

    # Parse virus summary
    assembly_name = os.path.splitext(os.path.basename(assembly_path))[0]
    summary_dir = os.path.join(results_dir, f"{assembly_name}_summary")
    virus_summary = os.path.join(summary_dir, f"{assembly_name}_virus_summary.tsv")

    results = []
    prophage_regions = []  # (contig, start, end) for ARG cross-reference

    if os.path.exists(virus_summary):
        with open(virus_summary) as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                seq_name = row.get("seq_name", "")
                coords = row.get("coordinates", "")
                length = int(row.get("length", 0))
                virus_score = float(row.get("virus_score", 0))
                taxonomy = row.get("taxonomy", "")
                n_hallmarks = int(row.get("n_hallmarks", 0))

                # Parse contig and coordinates from seq_name like "1|provirus_548465_598752"
                contig = seq_name.split("|")[0] if "|" in seq_name else seq_name
                start = end = None
                if coords and "-" in coords:
                    parts = coords.split("-")
                    try:
                        start = int(parts[0])
                        end = int(parts[1])
                    except ValueError:
                        pass

                if start and end:
                    prophage_regions.append((contig, start, end))

                pr = ProphageResult(
                    sample_id=sample_id,
                    contig=contig,
                    start=start,
                    end=end,
                    length=length,
                    virus_score=virus_score,
                    taxonomy=taxonomy,
                    n_hallmarks=n_hallmarks,
                )
                db.add(pr)
                results.append(pr)

    db.commit()

    # Cross-reference: mark ARGs in prophage regions
    if prophage_regions:
        arg_results = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
        updated = 0
        for arg in arg_results:
            if not arg.contig or arg.start is None:
                continue
            for p_contig, p_start, p_end in prophage_regions:
                if arg.contig == p_contig and p_start <= arg.start <= p_end:
                    arg.on_prophage = True
                    arg.contig_type = "prophage"
                    updated += 1
                    break
        db.commit()
        logger.info(f"Updated {updated} ARGs as prophage-borne")

    # Also find ARGs near prophage boundaries (within 5kb)
    if prophage_regions:
        arg_results = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
        for pr in results:
            nearby = []
            for arg in arg_results:
                if not arg.contig or arg.start is None or arg.contig != pr.contig:
                    continue
                if pr.start and pr.end:
                    if pr.start <= arg.start <= pr.end:
                        nearby.append({"gene": arg.gene, "drug_class": arg.drug_class, "distance_bp": 0})
                    else:
                        dist = min(abs(arg.start - pr.end), abs(pr.start - arg.start))
                        if dist <= 5000:
                            nearby.append({"gene": arg.gene, "drug_class": arg.drug_class, "distance_bp": dist})
            if nearby:
                pr.nearby_args = nearby
        db.commit()

    logger.info(f"geNomad found {len(results)} prophage regions for sample {sample_id}")
    return results
