import csv
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import ARGResult, VirulenceResult

logger = logging.getLogger(__name__)

CONDA_AMRFINDER = "radar"


def run_amrfinderplus(sample_id: str, assembly_path: str, db, threads: int = 4) -> List[ARGResult]:
    """Run NCBI AMRFinderPlus for ARG detection.

    Args:
        sample_id: UUID of the sample
        assembly_path: Path to the assembly FASTA
        db: SQLAlchemy session

    Returns:
        List of ARGResult records created
    """
    logger.info(f"Running AMRFinderPlus for sample {sample_id}")

    # Delete existing results to allow re-runs (cascade deletes promoter/rbs)
    old_args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    for a in old_args:
        from app.models.models import PromoterResult, RBSResult
        db.query(PromoterResult).filter(PromoterResult.arg_result_id == a.id).delete()
        db.query(RBSResult).filter(RBSResult.arg_result_id == a.id).delete()
    db.query(ARGResult).filter(ARGResult.sample_id == sample_id).delete()
    db.query(VirulenceResult).filter(VirulenceResult.sample_id == sample_id).delete()
    db.commit()

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "amr")
    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, "amrfinderplus.tsv")

    cmd = [
        "conda", "run", "-n", CONDA_AMRFINDER,
        "amrfinder",
        "-n", assembly_path,
        "-o", output_path,
        "--plus",
        "--threads", str(threads),
    ]

    logger.info(f"AMRFinderPlus command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        raise RuntimeError(f"AMRFinderPlus failed: {result.stderr[-2000:]}")

    # Parse TSV output
    results = []
    seen_args = set()  # (gene, contig, start, end) to deduplicate
    seen_vfs = set()
    if os.path.exists(output_path):
        with open(output_path) as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                element_type = row.get("Element type", row.get("Type", ""))
                element_subtype = row.get("Element subtype", row.get("Subtype", ""))

                # Only keep AMR, STRESS, and VIRULENCE entries
                if element_type not in ("AMR", "STRESS", "VIRULENCE"):
                    continue

                gene_name = row.get("Gene symbol", row.get("Element symbol", row.get("Sequence name", "unknown")))
                drug_class = row.get("Class", "")
                subclass = row.get("Subclass", "")
                if subclass and subclass != drug_class:
                    drug_class = f"{drug_class}; {subclass}" if drug_class else subclass

                contig = row.get("Contig id", "")
                start = _safe_int(row.get("Start", ""))
                end = _safe_int(row.get("Stop", ""))
                identity = _safe_float(row.get("% Identity to reference sequence", row.get("% Identity to reference", "")))
                coverage = _safe_float(row.get("% Coverage of reference sequence", row.get("% Coverage of reference", "")))
                method = row.get("Method", "")

                if element_type == "VIRULENCE":
                    vf_key = (gene_name, contig, start, end)
                    if vf_key in seen_vfs:
                        continue
                    seen_vfs.add(vf_key)
                    seq_name = row.get("Sequence name", "")
                    vf = VirulenceResult(
                        sample_id=sample_id,
                        gene=gene_name,
                        description=seq_name if seq_name != gene_name else None,
                        category=drug_class or "virulence",
                        identity=identity,
                        coverage=coverage,
                        contig=contig,
                        start=start,
                        end=end,
                        database="amrfinderplus",
                    )
                    db.add(vf)
                    continue

                arg_key = (gene_name, contig, start, end)
                if arg_key in seen_args:
                    continue
                seen_args.add(arg_key)

                arg = ARGResult(
                    sample_id=sample_id,
                    gene=gene_name,
                    drug_class=drug_class,
                    mechanism=element_subtype or method,
                    identity=identity,
                    coverage=coverage,
                    contig=contig,
                    start=start,
                    end=end,
                    database="amrfinderplus",
                    on_plasmid=False,  # Updated later by plasmid analysis
                )
                db.add(arg)
                results.append(arg)

    db.commit()
    logger.info(f"AMRFinderPlus found {len(results)} ARGs for sample {sample_id}")
    return results


def _safe_int(val: str) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val: str) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
