import logging
import os
import re
import subprocess
from typing import List

from app.config import settings
from app.models.models import CRISPRResult

logger = logging.getLogger(__name__)

CONDA_CRISPR = "radar"


def run_crisprcasfinder(
    sample_id: str,
    assembly_path: str,
    db,
    threads: int = 4,
) -> List[CRISPRResult]:
    """Run minced for CRISPR array detection.

    Detects CRISPR arrays, identifies repeat/spacer structure.
    """
    logger.info(f"Running minced (CRISPR detection) for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "crispr")
    os.makedirs(results_dir, exist_ok=True)

    txt_output = os.path.join(results_dir, "crispr_minced.txt")
    gff_output = os.path.join(results_dir, "crispr_minced.gff")

    cmd = [
        "conda", "run", "-n", CONDA_CRISPR,
        "minced",
        assembly_path,
        txt_output,
        gff_output,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"minced failed: {result.stderr[-1000:]}")

    # Delete existing results for re-runs
    db.query(CRISPRResult).filter(CRISPRResult.sample_id == sample_id).delete()
    db.commit()

    results = _parse_minced(sample_id, txt_output)

    for r in results:
        db.add(r)
    db.commit()

    logger.info(f"minced found {len(results)} CRISPR arrays for sample {sample_id}")
    return results


def _parse_minced(sample_id: str, txt_path: str) -> List[CRISPRResult]:
    """Parse minced text output for CRISPR arrays."""
    results = []

    if not os.path.exists(txt_path):
        return results

    current_contig = ""
    crispr_id = ""
    start = None
    end = None
    num_spacers = 0
    repeat_length = None
    spacer_length = None

    with open(txt_path) as f:
        for line in f:
            line = line.strip()

            # Sequence header: "Sequence 'contig_name' (length bp)"
            seq_match = re.match(r"Sequence '([^']+)'", line)
            if seq_match:
                current_contig = seq_match.group(1)
                continue

            # CRISPR header: "CRISPR 1   Range: 12345 - 67890"
            crispr_match = re.match(r"CRISPR (\d+)\s+Range:\s+(\d+)\s+-\s+(\d+)", line)
            if crispr_match:
                # Save previous CRISPR if any
                if crispr_id and num_spacers > 0:
                    results.append(CRISPRResult(
                        sample_id=sample_id,
                        crispr_id=crispr_id,
                        contig=current_contig,
                        start=start,
                        end=end,
                        cas_type=None,
                        cas_genes=None,
                        num_spacers=num_spacers,
                        repeat_length=repeat_length,
                        spacer_length=spacer_length,
                        evidence_level=None,
                    ))

                crispr_num = crispr_match.group(1)
                crispr_id = f"{current_contig}_CRISPR_{crispr_num}"
                start = int(crispr_match.group(2))
                end = int(crispr_match.group(3))
                num_spacers = 0
                repeat_length = None
                spacer_length = None
                continue

            # Repeat/Spacer lines contain the actual sequences
            # Format: "POSITION    REPEAT_SEQ    SPACER_SEQ"
            if line and not line.startswith("Repeats") and not line.startswith("-") and not line.startswith("Sequence"):
                parts = line.split()
                if len(parts) >= 2 and parts[0].isdigit():
                    repeat_seq = parts[1] if len(parts) >= 2 else ""
                    spacer_seq = parts[2] if len(parts) >= 3 else ""
                    if repeat_seq:
                        repeat_length = len(repeat_seq)
                    if spacer_seq:
                        spacer_length = len(spacer_seq)
                        num_spacers += 1

    # Save last CRISPR
    if crispr_id and num_spacers > 0:
        results.append(CRISPRResult(
            sample_id=sample_id,
            crispr_id=crispr_id,
            contig=current_contig,
            start=start,
            end=end,
            cas_type=None,
            cas_genes=None,
            num_spacers=num_spacers,
            repeat_length=repeat_length,
            spacer_length=spacer_length,
            evidence_level=None,
        ))

    return results
