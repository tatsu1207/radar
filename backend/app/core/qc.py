import json
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import SampleFile, PairType, SequencingPlatform

logger = logging.getLogger(__name__)

CONDA_FASTP = "radar"


def run_fastp(sample_id: str, input_files: List[str], db=None, threads: int = 4) -> dict:
    """Run fastp for adapter trimming and quality filtering.

    Args:
        sample_id: UUID of the sample
        input_files: List of input FASTQ file paths
        db: SQLAlchemy session

    Returns:
        Dict with QC summary metrics
    """
    logger.info(f"Running fastp QC for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "qc")
    os.makedirs(results_dir, exist_ok=True)

    # Separate files by pair type
    r1_files = []
    r2_files = []
    long_files = []
    has_pacbio = False

    if db:
        sample_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
        for sf in sample_files:
            if sf.pair == PairType.R1:
                r1_files.append(sf.file_path)
            elif sf.pair == PairType.R2:
                r2_files.append(sf.file_path)
            elif sf.pair == PairType.long_read:
                long_files.append(sf.file_path)
                if sf.platform == SequencingPlatform.pacbio:
                    has_pacbio = True
    else:
        # Fallback: guess from filenames
        for f in input_files:
            if "_R1" in f:
                r1_files.append(f)
            elif "_R2" in f:
                r2_files.append(f)
            else:
                long_files.append(f)

    html_report = os.path.join(results_dir, "fastp_report.html")
    json_report = os.path.join(results_dir, "fastp_report.json")
    trimmed_files = []

    # PacBio HiFi alone is sufficient for assembly — Illumina reads are ignored
    if has_pacbio:
        r1_files, r2_files = [], []

    if r1_files and r2_files:
        # Paired-end Illumina
        r1_out = os.path.join(results_dir, "trimmed_R1.fastq.gz")
        r2_out = os.path.join(results_dir, "trimmed_R2.fastq.gz")

        cmd = [
            "conda", "run", "-n", CONDA_FASTP,
            "fastp",
            "-i", r1_files[0],
            "-I", r2_files[0],
            "-o", r1_out,
            "-O", r2_out,
            "--html", html_report,
            "--json", json_report,
            "--thread", str(threads),
            "--qualified_quality_phred", "20",
            "--length_required", "50",
            "--detect_adapter_for_pe",
            "--correction",
            "--cut_front", "--cut_tail",
            "--cut_window_size", "4",
            "--cut_mean_quality", "20",
        ]

        logger.info(f"fastp command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

        if result.returncode != 0:
            raise RuntimeError(f"fastp failed: {result.stderr[-2000:]}")

        trimmed_files = [r1_out, r2_out]

    elif long_files:
        # Long-read QC report only (no trimming for long reads — Chopper handles that)
        lr_out = os.path.join(results_dir, "pacbio_passthrough.fastq.gz")

        cmd = [
            "conda", "run", "-n", CONDA_FASTP,
            "fastp",
            "-i", long_files[0],
            "-o", lr_out,
            "--html", html_report,
            "--json", json_report,
            "--disable_adapter_trimming",
            "--disable_quality_filtering",
            "--disable_length_filtering",
            "--thread", str(threads),
        ]

        logger.info(f"fastp command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

        if result.returncode != 0:
            raise RuntimeError(f"fastp failed: {result.stderr[-2000:]}")

        trimmed_files = [lr_out]

    else:
        raise ValueError("No FASTQ files found for QC")

    # Parse JSON report for summary stats
    summary = {"trimmed_files": trimmed_files, "stderr": result.stderr[-3000:]}

    if os.path.exists(json_report):
        with open(json_report) as f:
            summary["stats"] = json.load(f)

    logger.info(f"fastp QC complete for sample {sample_id}")
    return summary


def _samtools_cmd() -> List[str]:
    """samtools from the radar env, else the copy that ships with radar-plassembler."""
    import shutil
    if shutil.which("samtools"):
        return ["samtools"]
    return ["conda", "run", "-n", "radar-plassembler", "samtools"]


def convert_bam_long_reads(sample_id: str, db, threads: int = 4) -> List[str]:
    """Convert long-read BAM inputs (e.g. PacBio HiFi unaligned BAM) to FASTQ.gz.

    fastp, Chopper, Flye, Plassembler and Medaka all need FASTQ, so the
    SampleFile is repointed at the converted file and RADAR's copy of the BAM is
    removed (uploads are copies/hard links, so the user's original is untouched).
    If the platform was not set at upload, it is detected from the BAM header.

    Returns the converted FASTQ paths (empty when there was nothing to convert).
    """
    from app.api.file_manager import _detect_platform_from_bam

    converted = []
    sample_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
    for sf in sample_files:
        if sf.pair != PairType.long_read or not sf.file_path.lower().endswith(".bam"):
            continue

        bam = sf.file_path
        fastq = bam[: -len(".bam")] + ".fastq.gz"
        if sf.platform is None:
            sf.platform = _detect_platform_from_bam(bam)

        logger.info(f"Converting long-read BAM to FASTQ: {bam} -> {fastq}")
        tmp = fastq + ".tmp.gz"
        cmd = _samtools_cmd() + ["fastq", "-@", str(threads), "-c", "6", "-0", tmp, bam]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if result.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise RuntimeError(f"samtools fastq failed for {bam}: {result.stderr[-2000:]}")
        os.rename(tmp, fastq)
        os.remove(bam)

        sf.file_path = fastq
        sf.file_type = ".fastq.gz"
        sf.file_size = os.path.getsize(fastq)
        db.commit()
        converted.append(fastq)
    return converted
