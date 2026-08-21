import csv
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import PlasmidResult, ARGResult

logger = logging.getLogger(__name__)

CONDA_MOBSUITE = "radar-mobsuite"


def run_mob_recon(sample_id: str, assembly_path: str, db, threads: int = 4) -> List[PlasmidResult]:
    """Run MOB-recon for plasmid reconstruction and typing.

    Identifies plasmid contigs, classifies replicon types and mobility,
    then cross-references ARGs to mark plasmid-borne genes.
    """
    logger.info(f"Running MOB-recon for sample {sample_id}")

    # Delete existing results to allow re-runs
    db.query(PlasmidResult).filter(PlasmidResult.sample_id == sample_id).delete()
    db.commit()

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "plasmid")
    os.makedirs(results_dir, exist_ok=True)
    outdir = os.path.join(results_dir, "mob_recon_out")

    cmd = [
        "conda", "run", "-n", CONDA_MOBSUITE,
        "mob_recon",
        "-i", assembly_path,
        "-o", outdir,
        "-n", str(threads),
        "--force",
    ]

    logger.info(f"MOB-recon command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        raise RuntimeError(f"MOB-recon failed: {result.stderr[-2000:]}")

    results = []
    plasmid_contigs = {}  # contig_id -> cluster_id

    # Parse contig_report.txt
    contig_report = os.path.join(outdir, "contig_report.txt")
    if os.path.exists(contig_report):
        with open(contig_report) as f:
            reader = csv.DictReader(f, delimiter="\t")
            seen_clusters = set()
            for row in reader:
                mol_type = row.get("molecule_type", "")
                if mol_type != "plasmid":
                    continue

                contig_id = row.get("contig_id", "")
                cluster_id = row.get("primary_cluster_id", row.get("cluster_id", ""))

                # Map contig name to cluster — strip extra info from contig name
                # Contig IDs may look like "2 length=167432 depth=1.47x circular=true"
                contig_short = contig_id.split()[0] if contig_id else ""
                if contig_short:
                    plasmid_contigs[contig_short] = cluster_id

                if cluster_id in seen_clusters:
                    continue
                seen_clusters.add(cluster_id)

                replicon = row.get("rep_type(s)", "-")
                mob_type = row.get("relaxase_type(s)", "-")
                mpf_type = row.get("mpf_type", "-")
                mobility = row.get("predicted_mobility", "").strip("-").strip()
                mash_id = row.get("mash_neighbor_identification", "")
                mash_dist_str = row.get("mash_neighbor_distance", "")
                mash_dist = None
                if mash_dist_str and mash_dist_str not in ("-", ""):
                    try:
                        mash_dist = float(mash_dist_str)
                    except ValueError:
                        pass

                # Infer mobility from relaxase + MPF when predicted_mobility is empty
                has_relaxase = mob_type not in ("-", "", None)
                has_mpf = mpf_type not in ("-", "", None)
                if not mobility:
                    if has_relaxase and has_mpf:
                        mobility = "conjugative"
                    elif has_relaxase:
                        mobility = "mobilizable"
                    else:
                        mobility = "non-mobilizable"

                pr = PlasmidResult(
                    sample_id=sample_id,
                    plasmid_id=cluster_id,
                    mob_type=mob_type if mob_type != "-" else None,
                    replicon=replicon if replicon != "-" else None,
                    predicted_transferability=(mobility in ("conjugative", "mobilizable")),
                    predicted_mobility=mobility,
                    mash_neighbor_identification=mash_id if mash_id not in ("-", "") else None,
                    mash_neighbor_distance=mash_dist,
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
                arg.contig_type = f"plasmid ({plasmid_contigs[arg.contig]})"
                updated += 1
            elif arg.contig and not arg.on_prophage:
                arg.contig_type = "chromosome"
        db.commit()
        logger.info(f"Updated {updated} ARGs as plasmid-borne")

    logger.info(f"MOB-recon found {len(results)} plasmids for sample {sample_id}")
    return results
