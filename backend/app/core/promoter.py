import logging
import os
import subprocess
import uuid

from Bio import SeqIO

from app.config import settings
from app.models.models import ARGResult, PromoterResult

logger = logging.getLogger(__name__)

UPSTREAM_BP = 500


def run_bprom(sample_id: str, assembly_path: str, db, threads: int = 4):
    """Run BPROM promoter prediction on upstream regions of detected ARGs.

    For each ARG, extracts 500bp upstream from the assembly, runs BPROM,
    and stores LDF score, TF binding site count, promoter-to-ARG distance,
    and UP element AT-rich ratio.
    """
    logger.info(f"Running BPROM promoter analysis for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "promoter")
    os.makedirs(results_dir, exist_ok=True)

    # Load assembly
    contigs = {}
    for record in SeqIO.parse(assembly_path, "fasta"):
        contigs[record.id] = record

    # Get ARGs for this sample
    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    if not args:
        logger.info(f"No ARGs found for sample {sample_id}, skipping promoter analysis")
        return

    # Delete existing promoter results to allow re-runs
    for arg in args:
        db.query(PromoterResult).filter(PromoterResult.arg_result_id == arg.id).delete()
    db.commit()

    results = []
    for arg in args:
        if not arg.contig or arg.start is None:
            continue

        contig_record = contigs.get(arg.contig)
        if not contig_record:
            continue

        seq = str(contig_record.seq)

        # Extract upstream region
        upstream_start = max(0, arg.start - UPSTREAM_BP)
        upstream_end = arg.start
        if upstream_start >= upstream_end:
            continue
        upstream_seq = seq[upstream_start:upstream_end]

        if len(upstream_seq) < 50:
            continue

        # Write temp FASTA with 60-char line wrapping (BPROM requires it)
        temp_fasta = os.path.join(results_dir, f"upstream_{arg.id}.fasta")
        with open(temp_fasta, "w") as f:
            f.write(f">upstream_{arg.gene}\n")
            for i in range(0, len(upstream_seq), 60):
                f.write(upstream_seq[i:i+60] + "\n")

        # Run BPROM
        temp_out = os.path.join(results_dir, f"bprom_{arg.id}.txt")
        try:
            env = os.environ.copy()
            # TSS_DATA must point to directory containing bs.list, five.mat, ldfb.tss
            if "TSS_DATA" not in env:
                bprom_path = subprocess.run(
                    ["which", "bprom"], capture_output=True, text=True
                ).stdout.strip()
                if bprom_path:
                    bprom_dir = os.path.dirname(bprom_path)
                    # Check if data files are in the same dir as binary
                    if os.path.exists(os.path.join(bprom_dir, "ldfb.tss")):
                        env["TSS_DATA"] = bprom_dir

            result = subprocess.run(
                ["bprom", temp_fasta, temp_out],
                capture_output=True, text=True, timeout=60, env=env
            )
            # BPROM writes to the output file; also capture stdout/stderr
            output = ""
            if os.path.exists(temp_out):
                with open(temp_out) as f:
                    output = f.read()
            if not output:
                output = result.stdout + result.stderr

            # Parse BPROM output
            # Format: "Promoter Pos:    471 LDF-  1.81"
            #         " -10 box at pos.  456 CGGAAATAT Score    33"
            #         "phoB:  TTTATTAA at position     466 Score -   8"
            import re
            ldf_score = None
            tf_count = 0
            promoter_distance = None

            for line in output.splitlines():
                line_stripped = line.strip()
                # Match "Promoter Pos:  NNN LDF-  N.NN" (take first/best promoter)
                m = re.search(r'Promoter Pos:\s+(\d+)\s+LDF-?\s+([\d.]+)', line_stripped)
                if m and ldf_score is None:
                    pos = int(m.group(1))
                    ldf_score = float(m.group(2))
                    promoter_distance = len(upstream_seq) - pos
                # Count TF binding site lines (format: "sitename: SEQUENCE at position")
                if re.match(r'\s*\w+:\s+[ACGT]+ at position', line_stripped):
                    tf_count += 1

            # UP element AT-rich ratio: 20bp upstream of predicted promoter
            up_at_ratio = None
            if promoter_distance is not None:
                prom_pos_in_upstream = len(upstream_seq) - promoter_distance
                up_start = max(0, prom_pos_in_upstream - 20)
                up_end = prom_pos_in_upstream
                if up_end > up_start:
                    up_region = upstream_seq[up_start:up_end]
                    at_count = sum(1 for c in up_region.upper() if c in "AT")
                    up_at_ratio = at_count / len(up_region) if up_region else None

            pr = PromoterResult(
                arg_result_id=arg.id,
                ldf_score=ldf_score,
                tf_binding_sites=tf_count,
                promoter_distance=promoter_distance,
                up_element_at_ratio=up_at_ratio,
            )
            db.add(pr)
            results.append(pr)

        except subprocess.TimeoutExpired:
            logger.warning(f"BPROM timed out for ARG {arg.gene}")
        except FileNotFoundError:
            logger.warning("BPROM binary not found, skipping promoter analysis")
            break
        finally:
            if os.path.exists(temp_fasta):
                os.remove(temp_fasta)

    db.commit()
    logger.info(f"BPROM analysis complete for sample {sample_id}: {len(results)} promoters analyzed")
