import csv
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import PlasmidResult, ARGResult

logger = logging.getLogger(__name__)

CONDA_PLASMID = "radar-plasmid"


def run_mob_recon(sample_id: str, assembly_path: str, db, threads: int = 4) -> List[PlasmidResult]:
    """Run MOB-recon for plasmid reconstruction and typing.

    Args:
        sample_id: UUID of the sample
        assembly_path: Path to the assembly FASTA
        db: SQLAlchemy session

    Returns:
        List of PlasmidResult records created
    """
    logger.info(f"Running MOB-recon for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "plasmid")
    os.makedirs(results_dir, exist_ok=True)
    outdir = os.path.join(results_dir, "mob_recon_out")

    cmd = [
        "conda", "run", "-n", CONDA_PLASMID,
        "mob_recon",
        "--infile", assembly_path,
        "--outdir", outdir,
        "--num_threads", str(threads),
        "--force",
    ]

    logger.info(f"MOB-recon command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        raise RuntimeError(f"MOB-recon failed: {result.stderr[-2000:]}")

    results = []
    plasmid_contigs = set()

    # Parse contig_report.txt
    contig_report = os.path.join(outdir, "contig_report.txt")
    if os.path.exists(contig_report):
        with open(contig_report) as f:
            reader = csv.DictReader(f, delimiter="\t")
            seen_clusters = set()
            for row in reader:
                cluster_id = row.get("cluster_id", "")
                if not cluster_id or cluster_id == "chromosome":
                    continue

                contig_id = row.get("contig_id", "")
                if contig_id:
                    plasmid_contigs.add(contig_id)

                if cluster_id in seen_clusters:
                    continue
                seen_clusters.add(cluster_id)

                pr = PlasmidResult(
                    sample_id=sample_id,
                    plasmid_id=cluster_id,
                    mob_type=row.get("mash_nearest_neighbor", ""),
                    replicon=row.get("rep_type(s)", ""),
                    predicted_transferability=row.get("predicted_mobility", "") == "conjugative",
                )
                db.add(pr)
                results.append(pr)

    db.commit()

    # Cross-reference: update ARG results on plasmid contigs
    if plasmid_contigs:
        arg_results = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
        updated = 0
        for arg in arg_results:
            if arg.contig and arg.contig in plasmid_contigs:
                arg.on_plasmid = True
                updated += 1
        db.commit()
        logger.info(f"Updated {updated} ARGs as plasmid-borne")

    logger.info(f"MOB-recon found {len(results)} plasmids for sample {sample_id}")
    return results
