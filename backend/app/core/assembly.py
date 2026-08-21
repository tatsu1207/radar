import json
import logging
import os
import shutil
import subprocess
from typing import List, Optional

from app.config import settings
from app.models.models import SampleFile, PairType

logger = logging.getLogger(__name__)

CONDA_SPADES = "radar"
CONDA_FLYE = "radar"
CONDA_MEDAKA = "radar-medaka"
CONDA_POLYPOLISH = "radar"
CONDA_QUAST = "radar-quast"
CONDA_BUSCO = "radar-busco"


def run_assembly(sample_id: str, input_files: List[str], db=None, threads: int = 4) -> str:
    """Run genome assembly using the appropriate strategy.

    - Short-read only (R1+R2): SPAdes
    - Long-read only: Flye (--nano-hq for ONT, --pacbio-hifi for PacBio)
    - Hybrid (short + long): Flye -> Medaka -> Polypolish

    Args:
        sample_id: UUID of the sample
        input_files: List of input FASTQ file paths
        db: SQLAlchemy session
        threads: Number of threads

    Returns:
        Path to the assembly FASTA file
    """
    r1, r2, long_read = _resolve_read_files(sample_id, input_files, db)

    # Detect platform from database
    platform = "ont"
    if db and long_read:
        from app.models.models import SequencingPlatform
        sample_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
        for sf in sample_files:
            if sf.pair == PairType.long_read and sf.platform == SequencingPlatform.pacbio:
                platform = "pacbio"
                break

    if r1 and r2 and long_read:
        return _run_hybrid_assembly(sample_id, r1, r2, long_read, threads)
    elif r1 and r2:
        return _run_spades(sample_id, r1, r2, threads)
    elif long_read:
        return _run_flye(sample_id, long_read, threads, platform=platform)
    else:
        raise ValueError("No suitable read files found for assembly")


def _run_spades(sample_id: str, r1: str, r2: str, threads: int) -> str:
    """Run SPAdes for short-read-only assembly."""
    logger.info(f"Running SPAdes (short-read) for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    os.makedirs(results_dir, exist_ok=True)
    outdir = os.path.join(results_dir, "spades_out")

    if os.path.exists(outdir):
        shutil.rmtree(outdir)

    cmd = [
        "conda", "run", "-n", CONDA_SPADES,
        "spades.py",
        "--isolate",
        "-1", r1,
        "-2", r2,
        "-o", outdir,
        "-t", str(threads),
    ]

    logger.info(f"SPAdes command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=14400)

    if result.returncode != 0:
        raise RuntimeError(f"SPAdes failed: {result.stderr[-2000:]}")

    # SPAdes outputs scaffolds.fasta
    scaffolds = os.path.join(outdir, "scaffolds.fasta")
    contigs = os.path.join(outdir, "contigs.fasta")
    spades_output = scaffolds if os.path.exists(scaffolds) else contigs

    if not os.path.exists(spades_output):
        raise RuntimeError(f"SPAdes output not found at {spades_output}")

    final_assembly = os.path.join(results_dir, "assembly.fasta")
    shutil.copy2(spades_output, final_assembly)

    logger.info(f"SPAdes assembly complete for sample {sample_id}")
    return final_assembly


def _run_flye(sample_id: str, long_read: str, threads: int, platform: str = "ont") -> str:
    """Run Flye for long-read-only assembly."""
    logger.info(f"Running Flye (long-read, {platform}) for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    os.makedirs(results_dir, exist_ok=True)
    outdir = os.path.join(results_dir, "flye_out")

    if os.path.exists(outdir):
        shutil.rmtree(outdir)

    flye_mode = "--pacbio-hifi" if platform == "pacbio" else "--nano-hq"

    cmd = [
        "conda", "run", "-n", CONDA_FLYE,
        "flye",
        flye_mode, long_read,
        "--out-dir", outdir,
        "--threads", str(threads),
    ]

    logger.info(f"Flye command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=14400)

    if result.returncode != 0:
        raise RuntimeError(f"Flye failed: {result.stderr[-2000:]}")

    flye_assembly = os.path.join(outdir, "assembly.fasta")
    if not os.path.exists(flye_assembly):
        raise RuntimeError(f"Flye output not found at {flye_assembly}")

    final_assembly = os.path.join(results_dir, "assembly.fasta")
    shutil.copy2(flye_assembly, final_assembly)

    logger.info(f"Flye assembly complete for sample {sample_id}")
    return final_assembly


def _run_hybrid_assembly(
    sample_id: str, r1: str, r2: str, long_read: str, threads: int
) -> str:
    """Run hybrid assembly: Flye -> Medaka -> Polypolish.

    1. Flye: long-read assembly (produces contiguous contigs)
    2. Medaka: long-read polishing (corrects systematic errors)
    3. Polypolish: short-read polishing (fixes remaining base errors)
    """
    logger.info(f"Running hybrid assembly (Flye+Medaka+Polypolish) for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    os.makedirs(results_dir, exist_ok=True)

    # ── Step 1: Flye long-read assembly ──
    logger.info("Hybrid step 1/3: Flye")
    flye_dir = os.path.join(results_dir, "flye_out")
    if os.path.exists(flye_dir):
        shutil.rmtree(flye_dir)

    cmd_flye = [
        "conda", "run", "-n", CONDA_FLYE,
        "flye",
        "--nano-hq", long_read,
        "--out-dir", flye_dir,
        "--threads", str(threads),
    ]

    result = subprocess.run(cmd_flye, capture_output=True, text=True, timeout=14400)
    if result.returncode != 0:
        raise RuntimeError(f"Flye failed: {result.stderr[-2000:]}")

    flye_assembly = os.path.join(flye_dir, "assembly.fasta")
    if not os.path.exists(flye_assembly):
        raise RuntimeError("Flye output not found")

    # ── Step 2: Medaka long-read polishing ──
    # Medaka v2.x: medaka inference → medaka sequence (replaces old medaka_polish)
    logger.info("Hybrid step 2/3: Medaka")
    medaka_dir = os.path.join(results_dir, "medaka_out")
    if os.path.exists(medaka_dir):
        shutil.rmtree(medaka_dir)
    os.makedirs(medaka_dir, exist_ok=True)

    medaka_hdf = os.path.join(medaka_dir, "consensus_probs.hdf")
    medaka_assembly = os.path.join(medaka_dir, "consensus.fasta")
    medaka_ok = False

    # Step 2a: medaka inference (align reads + run neural network)
    cmd_inference = [
        "conda", "run", "-n", CONDA_MEDAKA,
        "medaka", "inference",
        long_read, flye_assembly, medaka_hdf,
        "--threads", str(threads),
    ]
    result = subprocess.run(cmd_inference, capture_output=True, text=True, timeout=7200)

    if result.returncode == 0 and os.path.exists(medaka_hdf):
        # Step 2b: medaka sequence (decode HDF → consensus FASTA)
        cmd_sequence = [
            "conda", "run", "-n", CONDA_MEDAKA,
            "medaka", "sequence", medaka_hdf, flye_assembly, medaka_assembly,
        ]
        result = subprocess.run(cmd_sequence, capture_output=True, text=True, timeout=3600)
        if result.returncode == 0 and os.path.exists(medaka_assembly):
            medaka_ok = True

    if not medaka_ok:
        logger.warning(f"Medaka failed (using Flye output directly): {result.stderr[-500:]}")
        medaka_assembly = flye_assembly

    # ── Step 3: Polypolish short-read polishing ──
    logger.info("Hybrid step 3/3: Polypolish")
    polypolish_dir = os.path.join(results_dir, "polypolish_out")
    os.makedirs(polypolish_dir, exist_ok=True)

    # Align short reads with BWA
    aligned_r1 = os.path.join(polypolish_dir, "aligned_R1.sam")
    aligned_r2 = os.path.join(polypolish_dir, "aligned_R2.sam")

    # Index
    cmd_index = [
        "conda", "run", "-n", CONDA_POLYPOLISH,
        "bwa", "index", medaka_assembly,
    ]
    subprocess.run(cmd_index, capture_output=True, text=True, timeout=600)

    # Align R1
    cmd_bwa_r1 = [
        "conda", "run", "-n", CONDA_POLYPOLISH,
        "bwa", "mem", "-t", str(threads), "-a", medaka_assembly, r1,
    ]
    with open(aligned_r1, "w") as f:
        result = subprocess.run(cmd_bwa_r1, stdout=f, stderr=subprocess.PIPE, text=True, timeout=3600)

    # Align R2
    cmd_bwa_r2 = [
        "conda", "run", "-n", CONDA_POLYPOLISH,
        "bwa", "mem", "-t", str(threads), "-a", medaka_assembly, r2,
    ]
    with open(aligned_r2, "w") as f:
        result = subprocess.run(cmd_bwa_r2, stdout=f, stderr=subprocess.PIPE, text=True, timeout=3600)

    # Polypolish filter
    filtered_r1 = os.path.join(polypolish_dir, "filtered_R1.sam")
    filtered_r2 = os.path.join(polypolish_dir, "filtered_R2.sam")

    cmd_filter = [
        "conda", "run", "-n", CONDA_POLYPOLISH,
        "polypolish", "filter",
        "--in1", aligned_r1,
        "--in2", aligned_r2,
        "--out1", filtered_r1,
        "--out2", filtered_r2,
    ]
    subprocess.run(cmd_filter, capture_output=True, text=True, timeout=1800)

    # Polypolish polish
    polished = os.path.join(polypolish_dir, "polished.fasta")
    sam_r1 = filtered_r1 if os.path.exists(filtered_r1) else aligned_r1
    sam_r2 = filtered_r2 if os.path.exists(filtered_r2) else aligned_r2

    cmd_polish = [
        "conda", "run", "-n", CONDA_POLYPOLISH,
        "polypolish", "polish",
        medaka_assembly,
        sam_r1,
        sam_r2,
    ]

    result = subprocess.run(cmd_polish, capture_output=True, text=True, timeout=3600)

    if result.returncode == 0 and result.stdout.strip():
        with open(polished, "w") as f:
            f.write(result.stdout)
        final_src = polished
    else:
        logger.warning(f"Polypolish failed (using Medaka output): {result.stderr[-500:]}")
        final_src = medaka_assembly

    # Copy to standard location
    final_assembly = os.path.join(results_dir, "assembly.fasta")
    shutil.copy2(final_src, final_assembly)

    # Clean up large SAM files
    for f in [aligned_r1, aligned_r2, filtered_r1, filtered_r2]:
        if os.path.exists(f):
            os.remove(f)

    logger.info(f"Hybrid assembly complete for sample {sample_id}")
    return final_assembly


def _resolve_read_files(sample_id: str, input_files: List[str], db) -> tuple:
    """Resolve R1, R2, and long-read file paths (prefer trimmed/filtered)."""
    r1 = r2 = long_read = None
    qc_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "qc")

    # Prefer trimmed/filtered files from QC step
    trimmed_r1 = os.path.join(qc_dir, "trimmed_R1.fastq.gz")
    trimmed_r2 = os.path.join(qc_dir, "trimmed_R2.fastq.gz")
    filtered_long = os.path.join(qc_dir, "filtered_long.fastq.gz")
    trimmed_long = os.path.join(qc_dir, "trimmed_long.fastq.gz")

    if os.path.exists(trimmed_r1):
        r1 = trimmed_r1
    if os.path.exists(trimmed_r2):
        r2 = trimmed_r2
    if os.path.exists(filtered_long):
        long_read = filtered_long
    elif os.path.exists(trimmed_long):
        long_read = trimmed_long

    # Fallback to original files for any that weren't resolved from QC
    if db and (not r1 or not r2 or not long_read):
        sample_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
        for sf in sample_files:
            if sf.pair == PairType.R1 and not r1:
                r1 = sf.file_path
            elif sf.pair == PairType.R2 and not r2:
                r2 = sf.file_path
            elif sf.pair == PairType.long_read and not long_read:
                long_read = sf.file_path

    return r1, r2, long_read


def run_quast(sample_id: str, assembly_path: str, threads: int = 4) -> dict:
    """Run QUAST for assembly quality assessment."""
    logger.info(f"Running QUAST for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    quast_dir = os.path.join(results_dir, "quast")

    cmd = [
        "conda", "run", "-n", CONDA_QUAST,
        "quast",
        assembly_path,
        "-o", quast_dir,
        "--min-contig", "200",
        "-t", str(threads),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        logger.warning(f"QUAST failed (non-critical): {result.stderr[-1000:]}")
        return {}

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
    """Run BUSCO for assembly completeness assessment."""
    logger.info(f"Running BUSCO for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    busco_dir = os.path.join(results_dir, "busco")

    cmd = [
        "conda", "run", "-n", CONDA_BUSCO,
        "busco",
        "-i", assembly_path,
        "-o", "busco_result",
        "--out_path", busco_dir,
        "-m", "genome",
        "-l", "bacteria_odb10",
        "--cpu", str(threads),
        "-f",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        logger.warning(f"BUSCO failed (non-critical): {result.stderr[-1000:]}")
        return {}

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
