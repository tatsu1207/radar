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
            cmd = [
                "conda", "run", "-n", "radar-ostir",
                "ostir",
                "-i", rbs_seq,
                "-t", "string",
                "-p",
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60
            )

            if result.returncode != 0:
                logger.warning(f"OSTIR failed for ARG {arg.gene}: {result.stderr[-500:]}")
                continue

            # Parse tab-separated output
            try:
                lines = result.stdout.strip().splitlines()
                header = None
                data_line = None
                for line in lines:
                    fields = line.split()
                    if len(fields) >= 5 and "expression" in line.lower():
                        header = fields
                    elif header and len(fields) >= len(header) and fields[0] in ("ATG", "GTG", "TTG"):
                        data_line = fields
                        break  # take the first (highest expression) start codon

                if header and data_line:
                    col_map = {h.lower(): i for i, h in enumerate(header)}
                    expression = float(data_line[col_map.get("expression", 2)])
                    dg_total = float(data_line[col_map.get("dg_total", 4)])
                    dg_mrna = float(data_line[col_map.get("dg_mrna", 6)])

                    rr = RBSResult(
                        arg_result_id=arg.id,
                        expression=expression,
                        dg_total=dg_total,
                        dg_mrna=dg_mrna,
                    )
                    db.add(rr)
                    results.append(rr)

            except (ValueError, IndexError, KeyError) as e:
                logger.warning(f"Failed to parse OSTIR output for ARG {arg.gene}: {e}")

        except subprocess.TimeoutExpired:
            logger.warning(f"OSTIR timed out for ARG {arg.gene}")
        except FileNotFoundError:
            logger.warning("OSTIR not found, skipping RBS analysis")
            break

    db.commit()
    logger.info(f"OSTIR RBS analysis complete for sample {sample_id}: {len(results)} RBS sites analyzed")
