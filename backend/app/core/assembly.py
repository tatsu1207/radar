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
CONDA_PLASSEMBLER = "radar-plassembler"
PLASSEMBLER_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "databases", "plassembler_db")


def run_assembly(sample_id: str, input_files: List[str], db=None, threads: int = 4) -> str:
    """Run genome assembly using the appropriate strategy.

    - Short-read only (R1+R2): SPAdes
    - PacBio HiFi: Flye --pacbio-hifi -> Plassembler -> dnaapler (always alone; Illumina reads are ignored)
    - Hybrid (Illumina + ONT): Flye -> Plassembler -> dnaapler -> Medaka -> Polypolish
    - ONT only: Flye --nano-hq -> Plassembler -> dnaapler -> Medaka

    Plassembler recovers small plasmids that Flye often misses; the ones not
    already in the Flye assembly are added before polishing. dnaapler then rotates
    circular contigs to start at dnaA/repA/terL.

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

    if long_read and platform == "pacbio":
        assembly = _run_flye(sample_id, long_read, threads, platform=platform)
    elif r1 and r2 and long_read:
        assembly = _run_hybrid_assembly(sample_id, r1, r2, long_read, threads)
    elif r1 and r2:
        assembly = _run_spades(sample_id, r1, r2, threads)
    elif long_read:
        assembly = _run_flye(sample_id, long_read, threads, platform=platform)
    else:
        raise ValueError("No suitable read files found for assembly")

    _normalise_assembly(assembly)
    return assembly


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
    """Run Flye for long-read-only assembly (ONT: Flye -> Medaka; PacBio HiFi: Flye)."""
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

    final_src = _add_plassembler_plasmids(long_read, None, None, flye_assembly, results_dir,
                                          threads, platform=platform)
    final_src = _rotate_contigs(final_src, results_dir, threads)

    # ONT-only: polish with Medaka (HiFi reads don't need long-read polishing)
    if platform == "ont":
        final_src = _run_medaka(long_read, final_src, results_dir, threads)

    final_assembly = os.path.join(results_dir, "assembly.fasta")
    shutil.copy2(final_src, final_assembly)

    logger.info(f"Flye assembly complete for sample {sample_id}")
    return final_assembly


def _run_medaka(long_read: str, draft: str, results_dir: str, threads: int) -> str:
    """Polish a draft assembly with Medaka. Returns the polished FASTA path,
    or the draft path unchanged if Medaka fails (non-critical)."""
    medaka_dir = os.path.join(results_dir, "medaka_out")

    # --bacteria picks the bacterial methylation-aware model, but only works when
    # read headers carry basecaller model info (recent Dorado output). Older reads
    # are rejected, so retry with medaka's automatic model selection.
    polished = os.path.join(medaka_dir, "consensus.fasta")
    for extra in (["--bacteria"], []):
        if os.path.exists(medaka_dir):
            shutil.rmtree(medaka_dir)
        cmd = [
            "conda", "run", "-n", CONDA_MEDAKA,
            "medaka_consensus",
            "-i", long_read,
            "-d", draft,
            "-o", medaka_dir,
            "-t", str(threads),
            *extra,
        ]
        logger.info(f"Medaka command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if result.returncode == 0 and os.path.exists(polished) and os.path.getsize(polished) > 0:
            return polished

    logger.warning(f"Medaka failed (using unpolished draft): {result.stderr[-500:]}")
    return draft


def _run_hybrid_assembly(
    sample_id: str, r1: str, r2: str, long_read: str, threads: int
) -> str:
    """Run hybrid assembly: Flye -> Plassembler -> Medaka -> Polypolish.

    1. Flye: long-read assembly (produces contiguous contigs)
    2. Plassembler: adds small plasmids missing from the Flye assembly, so they are
       polished too and their short reads are not pulled onto the chromosome;
       dnaapler then rotates circular contigs to start at dnaA/repA/terL
    3. Medaka: long-read polishing (corrects systematic errors)
    4. Polypolish: short-read polishing (fixes remaining base errors)
    """
    logger.info(f"Running hybrid assembly (Flye+Plassembler+Medaka+Polypolish) for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    os.makedirs(results_dir, exist_ok=True)

    # ── Step 1: Flye long-read assembly ──
    logger.info("Hybrid step 1/4: Flye")
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

    # ── Step 2: Plassembler (small plasmids Flye missed) ──
    logger.info("Hybrid step 2/4: Plassembler")
    draft = _add_plassembler_plasmids(long_read, r1, r2, flye_assembly, results_dir, threads)
    draft = _rotate_contigs(draft, results_dir, threads)

    # ── Step 3: Medaka long-read polishing ──
    logger.info("Hybrid step 3/4: Medaka")
    medaka_assembly = _run_medaka(long_read, draft, results_dir, threads)

    # ── Step 4: Polypolish short-read polishing ──
    logger.info("Hybrid step 4/4: Polypolish")
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


def _add_plassembler_plasmids(
    long_read: str, r1: Optional[str], r2: Optional[str], draft: str,
    results_dir: str, threads: int, platform: str = "ont",
) -> str:
    """Run Plassembler on the reads and append plasmids not already in the Flye
    assembly (no >=90%-covering hit). Returns the merged FASTA path, or the draft
    unchanged if Plassembler fails or adds nothing (non-critical).

    Circular plasmids are named plassembler_N; linear contigs (sometimes a piece of
    chromosome Flye dropped) plassembler_linear_N."""
    out = os.path.join(results_dir, "plassembler_out")
    merged = os.path.join(results_dir, "flye_plus_plasmids.fasta")

    mode, extra = "long", []
    if r1 and r2:
        mode, extra = "run", ["-1", r1, "-2", r2]
    if platform == "pacbio":
        extra += ["--pacbio_model", "pacbio-hifi"]
    has_db = os.path.isdir(PLASSEMBLER_DB) and any(
        f.endswith(".msh") for f in os.listdir(PLASSEMBLER_DB))
    db_args = ["-d", PLASSEMBLER_DB] if has_db else ["--skip_mash"]

    cmd = [
        "conda", "run", "-n", CONDA_PLASSEMBLER,
        "plassembler", mode,
        "-l", long_read, *extra,
        "--flye_directory", os.path.dirname(draft),
        "-o", out, "-t", str(threads), *db_args, "-f",
    ]
    logger.info(f"Plassembler command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning(f"Plassembler failed (using the Flye assembly): {e}")
        return draft
    if result.returncode != 0:
        logger.warning(f"Plassembler failed (using the Flye assembly): {result.stderr[-500:]}")
        return draft

    plasmids = _read_fasta(os.path.join(out, "plassembler_plasmids.fasta"))
    if not plasmids:
        logger.info("Plassembler found no plasmids")
        return draft

    # Plasmids already present in the Flye assembly (>=90% of their length aligned)
    cmd_map = [
        "conda", "run", "-n", CONDA_PLASSEMBLER,
        "minimap2", "-x", "asm5", "-c", draft,
        os.path.join(out, "plassembler_plasmids.fasta"),
    ]
    result = subprocess.run(cmd_map, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        logger.warning(f"minimap2 failed (using the Flye assembly): {result.stderr[-500:]}")
        return draft
    aligned, lengths = {}, {}
    for line in result.stdout.splitlines():
        f = line.split("\t")
        if len(f) >= 4:
            aligned[f[0]] = aligned.get(f[0], 0) + int(f[3]) - int(f[2])
            lengths[f[0]] = int(f[1])
    in_flye = {k for k in aligned if aligned[k] >= 0.9 * lengths[k]}

    added = []
    for header, seq in plasmids:
        pid = header.split()[0]
        if pid in in_flye:
            continue
        circular = "circular=true" in header.lower()
        added.append(((f"plassembler_{pid}" if circular else f"plassembler_linear_{pid}"), seq))
    logger.info(f"Plassembler: {len(plasmids)} contig(s), {len(added)} not in the Flye assembly added")
    if not added:
        return draft

    shutil.copy2(draft, merged)
    with open(merged, "a") as fh:
        for name, seq in added:
            fh.write(f">{name}\n")
            for i in range(0, len(seq), 60):
                fh.write(seq[i:i + 60] + "\n")
    return merged


def _rotate_contigs(draft: str, results_dir: str, threads: int) -> str:
    """Rotate circular contigs with dnaapler so they start at dnaA (chromosome), repA
    (plasmid) or terL (phage) and no gene spans the contig end (such genes are reported
    as partial). Runs before polishing, so the former contig ends get polished as ordinary
    sequence. Linear contigs are skipped. Returns the draft unchanged on failure."""
    out = os.path.join(results_dir, "dnaapler_out")
    ignore = os.path.join(results_dir, "dnaapler_ignore.txt")

    linear = []
    info = os.path.join(results_dir, "flye_out", "assembly_info.txt")
    if os.path.exists(info):
        with open(info) as fh:
            for line in fh:
                f = line.rstrip("\n").split("\t")
                if not line.startswith("#") and len(f) > 3 and f[3] == "N":
                    linear.append(f[0])
    linear += [h.split()[0] for h, _ in _read_fasta(draft)
               if h.startswith("plassembler_linear_")]
    with open(ignore, "w") as fh:
        fh.writelines(n + "\n" for n in linear)

    cmd = [
        "conda", "run", "-n", CONDA_PLASSEMBLER,
        "dnaapler", "all",
        "-i", draft, "-o", out, "-p", "dnaapler",
        "-t", str(threads), "--ignore", ignore, "-f",
    ]
    logger.info(f"dnaapler command: {' '.join(cmd)}")
    rotated = os.path.join(out, "dnaapler_reoriented.fasta")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning(f"dnaapler failed (contigs not rotated): {e}")
        return draft
    if result.returncode != 0 or not os.path.exists(rotated) or os.path.getsize(rotated) == 0:
        logger.warning(f"dnaapler failed (contigs not rotated): {result.stderr[-500:]}")
        return draft
    return rotated


def _read_fasta(path: str) -> list:
    """Return [(header, sequence)] from a FASTA file ([] if missing)."""
    records = []
    if not os.path.exists(path):
        return records
    header, seq = None, []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(">"):
                if header is not None:
                    records.append((header, "".join(seq)))
                header, seq = line[1:], []
            elif line:
                seq.append(line)
    if header is not None:
        records.append((header, "".join(seq)))
    return records


def _normalise_assembly(path: str) -> None:
    """Rewrite the final assembly for the annotation tools: keep only contig names
    (Polypolish appends " polypolish", which makes MobileElementFinder fail) and order
    contigs longest first (MobileElementFinder can also fail when a small contig
    precedes the chromosome). Circular contigs are listed in circular.txt next to it."""
    records = _read_fasta(path)
    if not records:
        return
    records.sort(key=lambda r: len(r[1]), reverse=True)
    with open(path + ".tmp", "w") as fh:
        for header, seq in records:
            fh.write(f">{header.split()[0]}\n")
            for i in range(0, len(seq), 60):
                fh.write(seq[i:i + 60] + "\n")
    os.replace(path + ".tmp", path)

    # Circularity: Flye's assembly_info.txt plus circular Plassembler plasmids
    results_dir = os.path.dirname(path)
    circular = set()
    info = os.path.join(results_dir, "flye_out", "assembly_info.txt")
    if os.path.exists(info):
        with open(info) as fh:
            for line in fh:
                f = line.rstrip("\n").split("\t")
                if len(f) > 3 and f[3] == "Y":
                    circular.add(f[0])
    names = [h.split()[0] for h, _ in records]
    with open(os.path.join(results_dir, "circular.txt"), "w") as fh:
        for n in names:
            if n in circular or (n.startswith("plassembler_") and not n.startswith("plassembler_linear_")):
                fh.write(n + "\n")


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
