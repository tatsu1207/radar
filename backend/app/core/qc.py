import json
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import SampleFile, PairType

logger = logging.getLogger(__name__)

CONDA_QC = "radar-qc"


def run_bbduk(sample_id: str, input_files: List[str], db=None, threads: int = 4) -> dict:
    """Run BBDuk for adapter trimming and quality filtering.

    Args:
        sample_id: UUID of the sample
        input_files: List of input FASTQ file paths
        db: SQLAlchemy session

    Returns:
        Dict with QC summary metrics
    """
    logger.info(f"Running BBDuk QC for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "qc")
    os.makedirs(results_dir, exist_ok=True)

    # Separate files by pair type
    r1_files = []
    r2_files = []
    long_files = []

    if db:
        sample_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
        for sf in sample_files:
            if sf.pair == PairType.R1:
                r1_files.append(sf.file_path)
            elif sf.pair == PairType.R2:
                r2_files.append(sf.file_path)
            elif sf.pair == PairType.long_read:
                long_files.append(sf.file_path)
    else:
        # Fallback: guess from filenames
        for f in input_files:
            if "_R1" in f:
                r1_files.append(f)
            elif "_R2" in f:
                r2_files.append(f)
            else:
                long_files.append(f)

    stats_path = os.path.join(results_dir, "bbduk_stats.txt")
    trimmed_files = []

    # BBDuk adapter reference path
    adapter_ref = os.path.join(
        os.environ.get("CONDA_PREFIX", "/home/unnot/miniforge3/envs/radar-qc"),
        "opt", "bbmap-39.01-1", "resources", "adapters.fa"
    )
    # Fallback: find adapters.fa
    if not os.path.exists(adapter_ref):
        adapter_ref = "adapters"  # bbduk built-in reference name

    if r1_files and r2_files:
        # Paired-end Illumina
        r1_out = os.path.join(results_dir, "trimmed_R1.fastq.gz")
        r2_out = os.path.join(results_dir, "trimmed_R2.fastq.gz")

        cmd = [
            "conda", "run", "-n", CONDA_QC,
            "bbduk.sh",
            f"in1={r1_files[0]}",
            f"in2={r2_files[0]}",
            f"out1={r1_out}",
            f"out2={r2_out}",
            f"ref={adapter_ref}",
            "ktrim=r", "k=23", "mink=11", "hdist=1",
            "qtrim=r", "trimq=20",
            "minlen=50",
            f"stats={stats_path}",
            f"threads={threads}",
            "tpe", "tbo",
        ]

        logger.info(f"BBDuk command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

        if result.returncode != 0:
            raise RuntimeError(f"BBDuk failed: {result.stderr[-2000:]}")

        trimmed_files = [r1_out, r2_out]

    elif long_files:
        # Long-read quality filter (lighter filtering)
        lr_out = os.path.join(results_dir, "trimmed_long.fastq.gz")

        cmd = [
            "conda", "run", "-n", CONDA_QC,
            "bbduk.sh",
            f"in={long_files[0]}",
            f"out={lr_out}",
            "qtrim=r", "trimq=10",
            "minlen=200",
            f"stats={stats_path}",
            f"threads={threads}",
        ]

        logger.info(f"BBDuk command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

        if result.returncode != 0:
            raise RuntimeError(f"BBDuk failed: {result.stderr[-2000:]}")

        trimmed_files = [lr_out]

    else:
        raise ValueError("No FASTQ files found for QC")

    # Parse stats
    summary = {"trimmed_files": trimmed_files, "stderr": result.stderr[-3000:]}

    if os.path.exists(stats_path):
        with open(stats_path) as f:
            summary["stats"] = f.read()

    logger.info(f"BBDuk QC complete for sample {sample_id}")
    return summary
