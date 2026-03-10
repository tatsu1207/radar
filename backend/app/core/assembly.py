import json
import logging
import os
import subprocess
from typing import List, Optional

from app.config import settings
from app.models.models import SampleFile, PairType

logger = logging.getLogger(__name__)

CONDA_ASSEMBLY = "radar-assembly"
CONDA_BUSCO = "radar-busco"


def run_unicycler(sample_id: str, input_files: List[str], db=None, threads: int = 4) -> str:
    """Run Unicycler for hybrid or short-read assembly.

    Args:
        sample_id: UUID of the sample
        input_files: List of input FASTQ file paths (trimmed)
        db: SQLAlchemy session

    Returns:
        Path to the assembly FASTA file
    """
    logger.info(f"Running Unicycler assembly for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    os.makedirs(results_dir, exist_ok=True)

    # Identify read files
    r1 = r2 = long_read = None
    qc_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "qc")

    # Prefer trimmed files from QC step
    trimmed_r1 = os.path.join(qc_dir, "trimmed_R1.fastq.gz")
    trimmed_r2 = os.path.join(qc_dir, "trimmed_R2.fastq.gz")
    trimmed_long = os.path.join(qc_dir, "trimmed_long.fastq.gz")

    if os.path.exists(trimmed_r1):
        r1 = trimmed_r1
    if os.path.exists(trimmed_r2):
        r2 = trimmed_r2
    if os.path.exists(trimmed_long):
        long_read = trimmed_long

    # Fallback to original files if trimmed not found
    if not r1 and db:
        sample_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
        for sf in sample_files:
            if sf.pair == PairType.R1 and not r1:
                r1 = sf.file_path
            elif sf.pair == PairType.R2 and not r2:
                r2 = sf.file_path
            elif sf.pair == PairType.long_read and not long_read:
                long_read = sf.file_path

    # Build unicycler command — clean stale output to prevent SPAdes reuse issues
    outdir = os.path.join(results_dir, "unicycler_out")
    if os.path.exists(outdir):
        import shutil
        shutil.rmtree(outdir)

    cmd = [
        "conda", "run", "-n", CONDA_ASSEMBLY,         "unicycler",
        "-o", outdir,
        "-t", str(threads),
    ]

    if r1 and r2 and long_read:
        # Hybrid assembly
        cmd.extend(["-1", r1, "-2", r2, "-l", long_read])
        logger.info("Running hybrid assembly (short + long reads)")
    elif r1 and r2:
        # Short-read only
        cmd.extend(["-1", r1, "-2", r2])
        logger.info("Running short-read assembly")
    elif long_read:
        # Long-read only
        cmd.extend(["-l", long_read])
        logger.info("Running long-read only assembly")
    else:
        raise ValueError("No suitable read files found for assembly")

    logger.info(f"Unicycler command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=14400)

    if result.returncode != 0:
        raise RuntimeError(f"Unicycler failed: {result.stderr[-2000:]}")

    # Unicycler output assembly
    assembly_path = os.path.join(outdir, "assembly.fasta")
    if not os.path.exists(assembly_path):
        raise RuntimeError(f"Assembly file not found at {assembly_path}")

    # Copy to standard location
    final_assembly = os.path.join(results_dir, "assembly.fasta")
    if assembly_path != final_assembly:
        import shutil
        shutil.copy2(assembly_path, final_assembly)

    logger.info(f"Unicycler assembly complete for sample {sample_id}: {final_assembly}")
    return final_assembly


def run_quast(sample_id: str, assembly_path: str, threads: int = 4) -> dict:
    """Run QUAST for assembly quality assessment.

    Args:
        sample_id: UUID of the sample
        assembly_path: Path to the assembly FASTA

    Returns:
        Dict with QUAST metrics
    """
    logger.info(f"Running QUAST for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    quast_dir = os.path.join(results_dir, "quast")

    cmd = [
        "conda", "run", "-n", CONDA_BUSCO,         "quast",
        assembly_path,
        "-o", quast_dir,
        "--min-contig", "200",
        "-t", str(threads),
    ]

    logger.info(f"QUAST command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        logger.warning(f"QUAST failed (non-critical): {result.stderr[-1000:]}")
        return {}

    # Parse QUAST report
    report_path = os.path.join(quast_dir, "report.tsv")
    metrics = {}
    if os.path.exists(report_path):
        with open(report_path) as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    metrics[parts[0]] = parts[1]

    logger.info(f"QUAST complete for sample {sample_id}")
    return metrics


def run_busco(sample_id: str, assembly_path: str, threads: int = 4) -> dict:
    """Run BUSCO for assembly completeness assessment.

    Args:
        sample_id: UUID of the sample
        assembly_path: Path to the assembly FASTA

    Returns:
        Dict with BUSCO metrics
    """
    logger.info(f"Running BUSCO for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    busco_dir = os.path.join(results_dir, "busco")

    cmd = [
        "conda", "run", "-n", CONDA_BUSCO,         "busco",
        "-i", assembly_path,
        "-o", "busco_result",
        "--out_path", busco_dir,
        "-m", "genome",
        "-l", "bacteria_odb10",
        "--cpu", str(threads),
        "-f",
    ]

    logger.info(f"BUSCO command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        logger.warning(f"BUSCO failed (non-critical): {result.stderr[-1000:]}")
        return {}

    # Parse BUSCO short summary
    summary = {"stderr": result.stderr[-1000:]}
    short_summary_dir = os.path.join(busco_dir, "busco_result")
    for root, dirs, files in os.walk(short_summary_dir):
        for fname in files:
            if fname.startswith("short_summary"):
                with open(os.path.join(root, fname)) as f:
                    summary["short_summary"] = f.read()
                break

    logger.info(f"BUSCO complete for sample {sample_id}")
    return summary
