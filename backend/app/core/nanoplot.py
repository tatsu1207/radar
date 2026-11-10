"""Long-read QC report with NanoPlot (ONT and PacBio).

Output per sample, in results/<sample>/qc/:
  nanoplot_raw/       reads as uploaded (after BAM->FASTQ conversion for PacBio BAM)
  nanoplot_filtered/  ONT reads after Chopper (shows what the filtering removed)
each with NanoPlot-report.html (self-contained) and NanoStats.txt.
"""
import logging
import os

from app.config import settings
from app.core import proc

logger = logging.getLogger(__name__)

CONDA_ENV = "radar-nanoplot"
STAGES = ("raw", "filtered")


def nanoplot_dir(sample_id: str, stage: str) -> str:
    return os.path.join(settings.RESULTS_DIR, str(sample_id), "qc", f"nanoplot_{stage}")


def report_path(sample_id: str, stage: str) -> str:
    return os.path.join(nanoplot_dir(sample_id, stage), "NanoPlot-report.html")


def stats_path(sample_id: str, stage: str) -> str:
    return os.path.join(nanoplot_dir(sample_id, stage), "NanoStats.txt")


def run_nanoplot(sample_id: str, fastq: str, stage: str, threads: int = 4) -> str:
    """Run NanoPlot on one long-read FASTQ(.gz). Returns the report path.
    Raises RuntimeError on failure (callers treat it as non-critical)."""
    if stage not in STAGES:
        raise ValueError(f"Unknown NanoPlot stage: {stage}")
    out = nanoplot_dir(sample_id, stage)
    os.makedirs(out, exist_ok=True)
    cmd = [
        "conda", "run", "-n", CONDA_ENV,
        "NanoPlot",
        "--fastq", fastq,
        "--outdir", out,
        "--threads", str(threads),
        "--N50",                 # mark the read N50 in the length histograms
        "--loglength",           # log-scaled length plots (long tails are common)
        "--plots", "dot", "kde",
        "--title", f"{stage} long reads",
    ]
    logger.info(f"NanoPlot command: {' '.join(cmd)}")
    result = proc.run(cmd, capture_output=True, text=True, timeout=7200)
    report = report_path(sample_id, stage)
    if result.returncode != 0 or not os.path.exists(report):
        raise RuntimeError(f"NanoPlot failed: {result.stderr[-1000:]}")
    _remove_bulky_files(out)
    return report


def _remove_bulky_files(out: str) -> None:
    """The report embeds its plots, so the per-plot files are not needed; keep the
    report, NanoStats.txt and the log."""
    keep = {"NanoPlot-report.html", "NanoStats.txt"}
    for name in os.listdir(out):
        path = os.path.join(out, name)
        if name in keep or name.endswith(".log") or not os.path.isfile(path):
            continue
        if name.endswith((".png", ".html", ".fasta", ".pickle", ".feather")):
            os.remove(path)


def read_stats(sample_id: str, stage: str) -> dict:
    """Parse NanoStats.txt: the General summary metrics ({metric: value}) plus the
    read-quality cutoffs ({"Reads >Q10": "5000 (100.0%) 25.4Mb", ...})."""
    path = stats_path(sample_id, stage)
    stats = {}
    if not os.path.exists(path):
        return stats
    section = "summary"
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("General summary"):
                continue
            if line.startswith("Number, percentage"):
                section = "cutoffs"
                continue
            if line.startswith("Top 5"):
                break
            key, sep, value = line.partition(":")
            if not sep:
                continue
            if section == "cutoffs":
                stats[f"Reads {key.strip()}"] = value.strip()
            else:
                stats[key.strip()] = value.strip()
    return stats
