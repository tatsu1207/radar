import logging
import os
import subprocess

from Bio import SeqIO

from app.config import settings
from app.models.models import ARGResult, RBSResult

logger = logging.getLogger(__name__)


def run_ostir(sample_id: str, assembly_path: str, db, threads: int = 4):
    """Run OSTIR for ribosome binding site analysis on detected ARGs.

    For each ARG, extracts -51bp to +19bp relative to the start codon,
    runs OSTIR, and stores expression level, dG_total, and dG_mRNA.
    """
    logger.info(f"Running OSTIR RBS analysis for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "rbs")
    os.makedirs(results_dir, exist_ok=True)

    # Load assembly
    contigs = {}
    for record in SeqIO.parse(assembly_path, "fasta"):
        contigs[record.id] = record

    # Get ARGs for this sample
    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    if not args:
        logger.info(f"No ARGs found for sample {sample_id}, skipping RBS analysis")
        return

    # Delete existing RBS results to allow re-runs
    for arg in args:
        db.query(RBSResult).filter(RBSResult.arg_result_id == arg.id).delete()
    db.commit()

    results = []
    for arg in args:
        if not arg.contig or arg.start is None:
            continue

        contig_record = contigs.get(arg.contig)
        if not contig_record:
            continue

        seq = str(contig_record.seq)

        # Extract -51 to +19 relative to start codon
        rbs_start = max(0, arg.start - 51)
        rbs_end = min(len(seq), arg.start + 19)
        rbs_seq = seq[rbs_start:rbs_end]

        if len(rbs_seq) < 30:
            continue

        # Run OSTIR
        try:
            import csv as _csv
            temp_csv = os.path.join(results_dir, f"ostir_{arg.id}.csv")
            cmd = [
                "conda", "run", "-n", "radar",
                "ostir",
                "-i", rbs_seq,
                "-t", "string",
                "-o", temp_csv,
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60
            )

            if result.returncode != 0:
                logger.warning(f"OSTIR failed for ARG {arg.gene}: {result.stderr[-500:]}")
                continue

            # Parse CSV output
            try:
                if os.path.exists(temp_csv):
                    with open(temp_csv) as f:
                        reader = _csv.DictReader(f)
                        for row in reader:
                            # Take the first start codon (highest expression)
                            expression = float(row.get("expression", 0))
                            dg_total = float(row.get("dG_total", 0))
                            dg_mrna = float(row.get("dG_mRNA", 0))

                            rr = RBSResult(
                                arg_result_id=arg.id,
                                expression=expression,
                                dg_total=dg_total,
                                dg_mrna=dg_mrna,
                            )
                            db.add(rr)
                            results.append(rr)
                            break  # first row only

            except (ValueError, IndexError, KeyError) as e:
                logger.warning(f"Failed to parse OSTIR output for ARG {arg.gene}: {e}")
            finally:
                if os.path.exists(temp_csv):
                    os.remove(temp_csv)

        except subprocess.TimeoutExpired:
            logger.warning(f"OSTIR timed out for ARG {arg.gene}")
        except FileNotFoundError:
            logger.warning("OSTIR not found, skipping RBS analysis")
            break

    db.commit()
    logger.info(f"OSTIR RBS analysis complete for sample {sample_id}: {len(results)} RBS sites analyzed")
