"""BacMet2 biocide and metal resistance gene detection.

Uses BLAST against the BacMet2 experimentally verified database to detect
genes conferring resistance to biocides, metals, and other non-antibiotic
antimicrobial compounds.

Database: http://bacmet.biomedicine.gu.se/
Reference: Pal et al. (2014) Nucleic Acids Res. 42:D845-D849
"""
import csv
import logging
import os
import subprocess
from typing import List

from app.config import settings
from app.models.models import BacMetResult

logger = logging.getLogger(__name__)

CONDA_BLAST = "radar-blast"

# Gene name patterns to compound mapping (common BacMet genes)
GENE_COMPOUND_MAP = {
    "ars": "Arsenic", "arz": "Arsenic",
    "cop": "Copper", "cue": "Copper", "cus": "Copper", "pco": "Copper",
    "mer": "Mercury",
    "czc": "Cadmium/Zinc/Cobalt", "cad": "Cadmium", "znt": "Zinc", "zit": "Zinc",
    "sil": "Silver",
    "pbr": "Lead",
    "chr": "Chromate",
    "nik": "Nickel", "rcn": "Nickel", "nrs": "Nickel",
    "tel": "Tellurium", "teh": "Tellurium", "ter": "Tellurium",
    "qac": "Quaternary ammonium", "smr": "Quaternary ammonium", "emr": "Biocide efflux",
    "acr": "Multidrug/Biocide efflux", "mdt": "Multidrug efflux", "tol": "Organic solvent",
    "bae": "Envelope stress/Biocide", "omp": "Outer membrane",
    "gol": "Gold", "ges": "Gold",
}


def _infer_compound(gene_name: str) -> str:
    """Infer compound from BacMet gene name prefix."""
    lower = gene_name.lower()
    for prefix, compound in GENE_COMPOUND_MAP.items():
        if lower.startswith(prefix):
            return compound
    return ""

BACMET_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "databases", "bacmet",
)


def _ensure_bacmet_db() -> str:
    """Download and index BacMet2 database if not present. Returns DB path."""
    db_dir = os.environ.get("RADAR_BACMET_DB", BACMET_DB)
    fasta_path = os.path.join(db_dir, "BacMet2_EXP_database.fasta")
    blast_db = os.path.join(db_dir, "BacMet2_EXP")

    if os.path.exists(blast_db + ".pin") or os.path.exists(blast_db + ".pdb"):
        return blast_db

    os.makedirs(db_dir, exist_ok=True)

    # Download BacMet2 experimentally verified nucleotide sequences
    if not os.path.exists(fasta_path):
        logger.info("Downloading BacMet2 EXP database...")
        url = "http://bacmet.biomedicine.gu.se/download/BacMet2_EXP_database.fasta"
        cmd = ["curl", "-sfL", "-o", fasta_path, url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0 or not os.path.exists(fasta_path):
            raise RuntimeError(f"Failed to download BacMet2 database: {result.stderr}")

    # Build BLAST database (protein sequences)
    logger.info("Building BacMet2 BLAST database...")
    cmd = [
        "conda", "run", "-n", CONDA_BLAST,
        "makeblastdb",
        "-in", fasta_path,
        "-dbtype", "prot",
        "-out", blast_db,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"makeblastdb failed: {result.stderr}")

    return blast_db


def run_bacmet(
    sample_id: str,
    assembly_path: str,
    db,
    threads: int = 4,
    identity_threshold: float = 80.0,
    coverage_threshold: float = 70.0,
) -> List[BacMetResult]:
    """Run blastp of Prodigal proteins against BacMet2 EXP database."""
    logger.info(f"Running BacMet2 for sample {sample_id}")

    # Delete existing results for re-runs
    db.query(BacMetResult).filter(BacMetResult.sample_id == sample_id).delete()
    db.commit()

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "bacmet")
    os.makedirs(results_dir, exist_ok=True)
    output_path = os.path.join(results_dir, "bacmet_blast.tsv")

    # Use Prodigal protein output
    proteins_path = os.path.join(settings.RESULTS_DIR, str(sample_id), "prodigal", "genes.faa")
    if not os.path.exists(proteins_path):
        logger.warning("No Prodigal protein output found, skipping BacMet2")
        return []

    try:
        blast_db = _ensure_bacmet_db()
    except Exception as e:
        logger.warning(f"BacMet2 database not available: {e}")
        return []

    cmd = [
        "conda", "run", "-n", CONDA_BLAST,
        "blastp",
        "-query", proteins_path,
        "-db", blast_db,
        "-out", output_path,
        "-outfmt", "6 qseqid sseqid pident length qstart qend sstart send evalue bitscore slen stitle",
        "-evalue", "1e-10",
        "-num_threads", str(threads),
        "-max_target_seqs", "1",
    ]

    logger.info(f"BacMet2 blastp command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

    if result.returncode != 0:
        raise RuntimeError(f"BacMet2 blastp failed: {result.stderr[-1000:]}")

    # Parse Prodigal headers to map protein IDs to contig coordinates
    # Format: >contig_1_1 # 43 # 849 # -1 # ID=...
    protein_coords = {}
    try:
        with open(proteins_path) as fh:
            for line in fh:
                if line.startswith(">"):
                    hparts = line[1:].strip().split(" # ")
                    if len(hparts) >= 4:
                        prot_id = hparts[0].strip()
                        pstart = int(hparts[1].strip())
                        pend = int(hparts[2].strip())
                        # Contig name: strip the last _N (ORF number) from protein ID
                        contig = "_".join(prot_id.split("_")[:-1])
                        protein_coords[prot_id] = (contig, pstart, pend)
    except Exception:
        pass

    results = []
    seen = set()

    if os.path.exists(output_path):
        with open(output_path) as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) < 12:
                    continue

                qseqid = parts[0]  # Prodigal protein ID
                sseqid = parts[1]  # BacMet ID
                pident = float(parts[2])
                length = int(parts[3])
                slen = int(parts[10])
                stitle = parts[11]

                # Filter by identity and coverage
                if pident < identity_threshold:
                    continue
                coverage = (length / slen * 100) if slen > 0 else 0
                if coverage < coverage_threshold:
                    continue

                # Parse sseqid: "BAC0078|copA|sp|O32220|COPA_BACSU"
                gene_name = sseqid
                sid_parts = sseqid.split("|")
                if len(sid_parts) >= 2:
                    gene_name = sid_parts[1].strip()
                compound = _infer_compound(gene_name)

                # Map protein ID to contig coordinates
                contig, start, end = protein_coords.get(qseqid, (qseqid, None, None))

                # Deduplicate by gene + contig
                key = f"{gene_name}:{contig}"
                if key in seen:
                    continue
                seen.add(key)

                br = BacMetResult(
                    sample_id=sample_id,
                    gene=gene_name,
                    bacmet_id=sseqid.split("|")[0] if "|" in sseqid else sseqid,
                    compound=compound,
                    identity=round(pident, 1),
                    coverage=round(coverage, 1),
                    contig=contig,
                    start=start,
                    end=end,
                )
                db.add(br)
                results.append(br)

    db.commit()
    logger.info(f"BacMet2 found {len(results)} biocide/metal resistance genes for sample {sample_id}")
    return results
