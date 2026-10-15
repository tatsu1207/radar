import logging
import os
import subprocess

from Bio import SeqIO
from Bio.Seq import Seq

from app.config import settings
from app.models.models import ARGResult, RBSResult

logger = logging.getLogger(__name__)

CONDA_OSTIR = "radar-ostir"  # ViennaRNA Python bindings for py3.11 conflict with mlst/perl in "radar"
UPSTREAM = 51    # bases before the start codon
DOWNSTREAM = 19  # bases from the start codon on (start codon included)
_STARTS = {"ATG", "GTG", "TTG"}
_STOPS = {"TAA", "TAG", "TGA"}


def rbs_window(seq: str, start: int, end: int):
    """Return (window, start_codon_position) for a gene at 1-based inclusive
    start..end, or None when its strand cannot be determined.

    The strand is inferred from the sequence (ARGResult stores none): a forward
    gene begins with a start codon at `start`, a reverse gene with the reverse
    complement of one at `end`; stop codons break ties. The window runs from
    UPSTREAM bases before the start codon to DOWNSTREAM bases into the gene, on
    the gene's strand; the returned position is 1-based within the window."""
    seq = seq.upper()
    s0, e0 = start - 1, end  # 0-based half-open
    rc = lambda x: str(Seq(x).reverse_complement())
    fwd = 2 * (seq[s0:s0 + 3] in _STARTS) + (seq[e0 - 3:e0] in _STOPS)
    rev = 2 * (rc(seq[e0 - 3:e0]) in _STARTS) + (rc(seq[s0:s0 + 3]) in _STOPS)
    if fwd < 2 and rev < 2 or fwd == rev:
        return None
    if fwd > rev:
        lo = max(0, s0 - UPSTREAM)
        return seq[lo:s0 + DOWNSTREAM], s0 - lo + 1
    hi = min(len(seq), e0 + UPSTREAM)
    return rc(seq[e0 - DOWNSTREAM:hi]), hi - e0 + 1


def run_ostir(sample_id: str, assembly_path: str, db, threads: int = 4):
    """Run OSTIR for ribosome binding site analysis on detected ARGs.

    For each ARG, extracts 51 bp upstream of the start codon to 19 bp into the
    gene (on the gene's strand), runs OSTIR for that start codon, and stores
    expression level, dG_total, and dG_mRNA.
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

        window = rbs_window(str(contig_record.seq), arg.start, arg.end or arg.start)
        if window is None:
            continue  # partial hit or no start codon: strand/start unknown
        rbs_seq, codon_pos = window

        if codon_pos < 21:
            continue  # too little upstream sequence for an RBS (contig edge)

        # Run OSTIR
        try:
            import csv as _csv
            temp_csv = os.path.join(results_dir, f"ostir_{arg.id}.csv")
            cmd = [
                "conda", "run", "-n", CONDA_OSTIR,
                "ostir",
                "-i", rbs_seq,
                "-t", "string",
                "-s", str(codon_pos),  # only the gene's own start codon
                "-e", str(codon_pos),
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
                            # One row: the gene's own start codon (-s/-e above)
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
