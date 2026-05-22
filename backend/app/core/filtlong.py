import logging
import os
import subprocess

from app.config import settings
from app.models.models import SampleFile, PairType

logger = logging.getLogger(__name__)

CONDA_FILTLONG = "radar-filtlong"


def run_filtlong(sample_id: str, input_files: list[str], db=None, threads: int = 4) -> dict:
    """Run Filtlong for ONT long-read quality filtering.

    Filters reads by quality, keeping the best reads up to a target coverage.
    If Illumina reads are available, uses them as a reference for quality estimation.
    """
    logger.info(f"Running Filtlong for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "qc")
    os.makedirs(results_dir, exist_ok=True)

    long_file = None
    r1_file = None
    r2_file = None

    if db:
        sample_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
        for sf in sample_files:
            if sf.pair == PairType.long_read:
                long_file = sf.file_path
            elif sf.pair == PairType.R1:
                r1_file = sf.file_path
            elif sf.pair == PairType.R2:
                r2_file = sf.file_path
    else:
        for f in input_files:
            if "_R1" in f:
                r1_file = f
            elif "_R2" in f:
                r2_file = f
            else:
                long_file = f

    if not long_file:
        raise ValueError("No long-read file found for Filtlong")

    output_path = os.path.join(results_dir, "filtered_long.fastq.gz")

    cmd = ["conda", "run", "-n", CONDA_FILTLONG, "filtlong"]

    # Use Illumina reads as reference if available
    if r1_file and r2_file:
        cmd.extend(["-1", r1_file, "-2", r2_file])

    cmd.extend([
        "--min_length", "1000",
        "--keep_percent", "90",
        long_file,
    ])

    # Pipe through gzip
    full_cmd = " ".join(cmd) + f" | gzip > {output_path}"

    logger.info(f"Filtlong command: {full_cmd}")
    result = subprocess.run(
        full_cmd, shell=True, capture_output=True, text=True, timeout=7200
    )

    if result.returncode != 0:
        raise RuntimeError(f"Filtlong failed: {result.stderr[-2000:]}")

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("Filtlong produced empty output")

    logger.info(f"Filtlong complete for sample {sample_id}: {output_path}")
    return {"filtered_file": output_path, "stderr": result.stderr[-3000:]}
