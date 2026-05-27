import logging
import os
import subprocess

from app.config import settings
from app.models.models import BaktaAnnotation

logger = logging.getLogger(__name__)

CONDA_BAKTA = "radar"
BAKTA_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "databases", "bakta_db", "db-light",
)


def run_bakta(sample_id: str, assembly_path: str, db, threads: int = 4) -> BaktaAnnotation:
    """Run Bakta genome annotation on the assembly.

    Produces GFF3, GenBank, and FAA outputs needed for downstream
    comparative genomics (Panaroo pan-genome, etc.).
    """
    logger.info(f"Running Bakta for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "bakta")
    os.makedirs(results_dir, exist_ok=True)

    prefix = "annotation"
    gff_path = os.path.join(results_dir, f"{prefix}.gff3")
    gbk_path = os.path.join(results_dir, f"{prefix}.gbff")
    faa_path = os.path.join(results_dir, f"{prefix}.faa")

    # Determine database path
    db_path = os.environ.get("RADAR_BAKTA_DB", BAKTA_DB)
    if not os.path.isdir(db_path):
        raise RuntimeError(
            f"Bakta database not found at {db_path}. "
            "Run: bakta_db download --output <path>"
        )

    # Run Bakta
    cmd = [
        "conda", "run", "-n", CONDA_BAKTA,
        "bakta",
        "--db", db_path,
        "--output", results_dir,
        "--prefix", prefix,
        "--threads", str(threads),
        "--skip-plot",
        "--skip-trna",
        "--skip-tmrna",
        "--skip-rrna",
        "--skip-ncrna",
        "--skip-ncrna-region",
        "--skip-crispr",
        "--skip-pseudo",
        "--skip-sorf",
        "--skip-gap",
        "--skip-ori",
        assembly_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"Bakta failed: {result.stderr[-1000:]}")

    # Parse annotation summary from tsv
    tsv_path = os.path.join(results_dir, f"{prefix}.tsv")
    counts = _parse_annotation_counts(tsv_path)

    # Delete existing result for re-runs
    existing = db.query(BaktaAnnotation).filter(
        BaktaAnnotation.sample_id == sample_id
    ).first()
    if existing:
        db.delete(existing)
        db.commit()

    annotation = BaktaAnnotation(
        sample_id=sample_id,
        gff_path=gff_path if os.path.exists(gff_path) else None,
        gbk_path=gbk_path if os.path.exists(gbk_path) else None,
        faa_path=faa_path if os.path.exists(faa_path) else None,
        cds_count=counts.get("cds", 0),
        rrna_count=counts.get("rrna", 0),
        trna_count=counts.get("trna", 0),
        ncrna_count=counts.get("ncrna", 0),
        crispr_count=counts.get("crispr", 0),
        hypothetical_count=counts.get("hypothetical", 0),
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)

    logger.info(
        f"Bakta complete for {sample_id}: "
        f"{counts.get('cds', 0)} CDS, {counts.get('trna', 0)} tRNA"
    )
    return annotation


def _parse_annotation_counts(tsv_path: str) -> dict:
    """Parse Bakta TSV output to count feature types."""
    counts = {
        "cds": 0, "rrna": 0, "trna": 0, "ncrna": 0,
        "crispr": 0, "hypothetical": 0,
    }
    if not os.path.exists(tsv_path):
        return counts

    with open(tsv_path) as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.strip().split("\t")
            if len(parts) < 2:
                continue
            feat_type = parts[1].lower()
            if feat_type == "cds":
                counts["cds"] += 1
                # Check for hypothetical
                product = parts[6] if len(parts) > 6 else ""
                if "hypothetical" in product.lower():
                    counts["hypothetical"] += 1
            elif feat_type == "trna":
                counts["trna"] += 1
            elif feat_type == "rrna":
                counts["rrna"] += 1
            elif feat_type in ("ncrna", "ncrna-region"):
                counts["ncrna"] += 1
            elif feat_type == "crispr":
                counts["crispr"] += 1

    return counts
