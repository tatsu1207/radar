import logging
import os
import subprocess

from app.config import settings
from app.models.models import SampleFile, PairType

logger = logging.getLogger(__name__)

CONDA_ENV = "radar"


def run_filtlong(sample_id: str, input_files: list[str], db=None, threads: int = 4) -> dict:
    """Run Chopper for long-read quality filtering.

    Filters and trims reads by quality score and minimum length.
    """
    logger.info(f"Running Chopper for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "qc")
    os.makedirs(results_dir, exist_ok=True)

    long_file = None

    if db:
        sample_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
        for sf in sample_files:
            if sf.pair == PairType.long_read:
                long_file = sf.file_path
    else:
        for f in input_files:
            if "_R1" not in f and "_R2" not in f:
                long_file = f

    if not long_file:
        raise ValueError("No long-read file found for Chopper")

    # Auto-fix: if .gz file is actually plain text, gzip it in place
    # Also handle case where a previous failed run left the uncompressed file
    if long_file.endswith(".gz") and not os.path.exists(long_file):
        plain_path = long_file[:-3]
        if os.path.exists(plain_path):
            logger.info(f"Found uncompressed {plain_path}, compressing to {long_file}")
            subprocess.run(f"gzip -c {plain_path} > {long_file}", shell=True, check=True)
            os.remove(plain_path)

    if long_file.endswith(".gz") and os.path.exists(long_file):
        with open(long_file, "rb") as f:
            magic = f.read(2)
        if magic != b'\x1f\x8b':  # not a valid gzip header
            logger.info(f"File {long_file} has .gz extension but is plain text — compressing")
            tmp_path = long_file + ".tmp"
            os.rename(long_file, tmp_path)
            subprocess.run(f"gzip -c {tmp_path} > {long_file}", shell=True, check=True)
            os.remove(tmp_path)

    output_path = os.path.join(results_dir, "filtered_long.fastq.gz")

    # chopper -i reads gzip natively; pipe output through gzip
    full_cmd = (
        f"set -o pipefail; "
        f"conda run -n {CONDA_ENV} chopper -q 10 --minlength 1000 --threads {threads} -i {long_file} "
        f"| gzip > {output_path}"
    )

    logger.info(f"Chopper command: {full_cmd}")
    result = subprocess.run(
        full_cmd, shell=True, capture_output=True, text=True, timeout=7200,
        executable="/bin/bash",
    )

    if result.returncode != 0:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise RuntimeError(f"Chopper failed: {result.stderr[-2000:]}")

    # Verify the gzip file is valid
    verify = subprocess.run(
        ["gzip", "-t", output_path], capture_output=True, text=True
    )
    if verify.returncode != 0:
        os.remove(output_path)
        raise RuntimeError(f"Chopper output is corrupt gzip: {verify.stderr}")

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("Chopper produced empty output")

    logger.info(f"Chopper complete for sample {sample_id}: {output_path}")
    return {"filtered_file": output_path, "stderr": result.stderr[-3000:]}
