import csv
import logging
import os
import subprocess
from typing import Optional

from app.config import settings
from app.models.models import SpeciesResult

logger = logging.getLogger(__name__)

CONDA_BLAST = "radar"
CONDA_SKANI = "radar"
CONDA_GTDBTK = "radar"

DB_16S = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "databases", "16S", "16S_ribosomal_RNA")
DB_SKANI = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "databases", "skani")

ANI_THRESHOLD = 95.0  # Below this, fall back to GTDB-Tk


def run_species_id(sample_id: str, assembly_path: str, db, threads: int = 4) -> Optional[SpeciesResult]:
    """Identify species using skani ANI against GTDB.
    Falls back to 16S BLAST if skani DB is unavailable.
    """
    logger.info(f"Running species identification for sample {sample_id}")

    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "species")
    os.makedirs(results_dir, exist_ok=True)

    # Try skani first
    sr = _run_skani(sample_id, assembly_path, results_dir, db, threads)

    if not sr:
        # Fall back to 16S BLAST
        logger.info("skani unavailable, falling back to 16S BLAST")
        sr = _run_blast_16s(sample_id, assembly_path, results_dir, db, threads)

    return sr


def _run_skani(sample_id, assembly_path, results_dir, db, threads) -> Optional[SpeciesResult]:
    """Run skani search against GTDB sketch database."""
    output_path = os.path.join(results_dir, "skani_results.tsv")

    skani_db = os.environ.get("RADAR_SKANI_DB", DB_SKANI)
    # Find the sketch directory
    sketch_dir = None
    for candidate in [skani_db, os.path.join(skani_db, "skani-gtdb-r220-sketch"), os.path.join(skani_db, "skani_gtdb_r226-v0.3")]:
        if os.path.isdir(candidate):
            sketch_dir = candidate
            break

    if not sketch_dir:
        logger.warning(f"skani database not found at {skani_db}")
        return None

    cmd = [
        "conda", "run", "-n", CONDA_SKANI,
        "skani", "search",
        assembly_path,
        "-d", sketch_dir,
        "-o", output_path,
        "-t", str(threads),
        "-n", "5",
    ]

    logger.info(f"skani command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        logger.warning("skani not found")
        return None

    if result.returncode != 0:
        logger.warning(f"skani failed: {result.stderr[-500:]}")
        return None

    # Parse results
    # Columns: Ref_file  Query_file  ANI  Align_fraction_ref  Align_fraction_query  Ref_name  Query_name
    top_hits = []
    if os.path.exists(output_path):
        with open(output_path) as f:
            for line in f:
                if line.startswith("Ref_file"):
                    continue
                parts = line.strip().split("\t")
                if len(parts) < 3:
                    continue
                ref_file = parts[0]
                ani = float(parts[2])
                ref_name = parts[5] if len(parts) > 5 else ""
                # Extract species from Ref_name (e.g., "NZ_CP033092.2 Escherichia coli DSM 30083 ...")
                species = _species_from_ref_name(ref_name)
                if not species:
                    # Fallback to accession from path
                    species = _species_from_gtdb_path(ref_file)
                top_hits.append({
                    "species": species,
                    "identity": ani,
                    "ref_file": os.path.basename(ref_file),
                })

    if not top_hits:
        return None

    best = top_hits[0]

    old = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    if old:
        db.delete(old)
        db.flush()

    sr = SpeciesResult(
        sample_id=sample_id,
        species=best["species"],
        identity=best["identity"],
        method="skani",
        top_hits=top_hits[:5],
    )
    db.add(sr)
    db.commit()

    logger.info(f"skani species ID: {best['species']} (ANI={best['identity']}%)")
    return sr


def _run_gtdbtk(sample_id, assembly_path, results_dir, db, threads) -> Optional[SpeciesResult]:
    """Run GTDB-Tk classify_wf for phylogenetic placement."""
    gtdbtk_dir = os.path.join(results_dir, "gtdbtk")
    os.makedirs(gtdbtk_dir, exist_ok=True)

    # GTDB-Tk needs a batch file
    batch_file = os.path.join(gtdbtk_dir, "batchfile.tsv")
    with open(batch_file, "w") as f:
        f.write(f"{assembly_path}\t{sample_id}\n")

    # Check GTDBTK_DATA_PATH
    gtdbtk_data = os.environ.get("GTDBTK_DATA_PATH", "")
    if not gtdbtk_data or not os.path.isdir(gtdbtk_data):
        logger.warning("GTDBTK_DATA_PATH not set or not found, skipping GTDB-Tk")
        return None

    cmd = [
        "conda", "run", "-n", CONDA_GTDBTK,
        "gtdbtk", "classify_wf",
        "--batchfile", batch_file,
        "--out_dir", gtdbtk_dir,
        "--cpus", str(threads),
        "--skip_ani_screen",
    ]

    logger.info(f"GTDB-Tk command: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    except FileNotFoundError:
        logger.warning("GTDB-Tk not found")
        return None

    if result.returncode != 0:
        logger.warning(f"GTDB-Tk failed: {result.stderr[-500:]}")
        return None

    # Parse summary
    for summary_file in ["gtdbtk.bac120.summary.tsv", "gtdbtk.ar53.summary.tsv"]:
        summary_path = os.path.join(gtdbtk_dir, summary_file)
        if not os.path.exists(summary_path):
            continue
        with open(summary_path) as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                classification = row.get("classification", "")
                ani = row.get("fastani_ani", row.get("closest_genome_ani", ""))

                # Parse classification: d__Bacteria;p__Proteobacteria;...;s__Escherichia coli
                species = _parse_gtdbtk_classification(classification)
                if not species:
                    continue

                old = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
                if old:
                    db.delete(old)
                    db.flush()

                sr = SpeciesResult(
                    sample_id=sample_id,
                    species=species,
                    identity=float(ani) if ani else None,
                    method="gtdbtk",
                    top_hits=[{"species": species, "classification": classification, "identity": float(ani) if ani else None}],
                )
                db.add(sr)
                db.commit()

                logger.info(f"GTDB-Tk species ID: {species}")
                return sr

    return None


def _run_blast_16s(sample_id, assembly_path, results_dir, db, threads) -> Optional[SpeciesResult]:
    """Fallback: 16S rRNA BLAST against NCBI 16S database."""
    output_path = os.path.join(results_dir, "blast_16s.tsv")

    db_path = os.environ.get("RADAR_16S_DB", DB_16S)
    if not os.path.exists(db_path + ".nsq") and not os.path.exists(db_path + ".nin"):
        logger.warning(f"16S database not found at {db_path}")
        return None

    cmd = [
        "conda", "run", "-n", CONDA_BLAST,
        "blastn",
        "-query", assembly_path,
        "-db", db_path,
        "-outfmt", "6 qseqid sseqid pident length qcovs stitle",
        "-max_target_seqs", "10",
        "-evalue", "1e-10",
        "-num_threads", str(threads),
        "-perc_identity", "90",
        "-out", output_path,
    ]

    logger.info(f"16S BLAST command: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        logger.warning(f"16S BLAST failed: {result.stderr[-500:]}")
        return None

    seen_species = {}
    if os.path.exists(output_path):
        with open(output_path) as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) < 6:
                    continue
                sseqid, pident, length, stitle = parts[1], float(parts[2]), int(parts[3]), parts[5]
                species_name = _extract_species_from_title(stitle)
                if not species_name:
                    continue
                if species_name not in seen_species or pident > seen_species[species_name]["pident"]:
                    seen_species[species_name] = {
                        "species": species_name, "pident": pident,
                        "length": length, "accession": sseqid,
                    }

    if not seen_species:
        return None

    ranked = sorted(seen_species.values(), key=lambda x: (-x["pident"], -x["length"]))
    best = ranked[0]

    old = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    if old:
        db.delete(old)
        db.flush()

    sr = SpeciesResult(
        sample_id=sample_id,
        species=best["species"],
        identity=best["pident"],
        alignment_length=best["length"],
        accession=best["accession"],
        method="blast_16s",
        top_hits=[{"species": h["species"], "identity": h["pident"], "accession": h["accession"]} for h in ranked[:5]],
    )
    db.add(sr)
    db.commit()

    logger.info(f"16S BLAST species ID: {best['species']} ({best['pident']}%)")
    return sr


def _species_from_ref_name(ref_name: str) -> str:
    """Extract species name from skani Ref_name field.

    Input: 'NZ_CP033092.2 Escherichia coli DSM 30083 = JCM 1649 chromosome, complete genome'
    Output: 'Escherichia coli'

    Input: 'NZ_PTRE01000104.1 Escherichia sp. MOD1-EC7003 ...'
    Output: 'Escherichia sp.'
    """
    if not ref_name:
        return ""
    # Split on whitespace; first token is the accession, rest is description
    words = ref_name.strip().split()
    if len(words) < 3:
        return ""
    # Skip the accession (first word), genus is second, species epithet is third
    genus = words[1]
    epithet = words[2]
    # Sanity check: genus should start uppercase, epithet lowercase or "sp."
    if not genus[0].isupper():
        return ""
    if epithet in ("sp.", "sp"):
        return f"{genus} sp."
    if epithet[0].isupper():
        # Not a species epithet (might be strain name), return genus only
        return f"{genus} sp."
    return f"{genus} {epithet}"


def _species_from_gtdb_path(ref_path: str) -> str:
    """Extract species name from GTDB reference path/filename (fallback)."""
    basename = os.path.basename(ref_path)
    return basename.split("_genomic")[0] if "_genomic" in basename else basename


def _parse_gtdbtk_classification(classification: str) -> str:
    """Parse GTDB-Tk classification string to species name.

    Input: 'd__Bacteria;p__Proteobacteria;c__Gammaproteobacteria;o__Enterobacterales;f__Enterobacteriaceae;g__Escherichia;s__Escherichia coli'
    Output: 'Escherichia coli'
    """
    if not classification:
        return ""
    parts = classification.split(";")
    for p in reversed(parts):
        if p.startswith("s__") and len(p) > 3:
            return p[3:]
        if p.startswith("g__") and len(p) > 3:
            return p[3:] + " sp."
    return ""


def _extract_species_from_title(stitle: str) -> str:
    """Extract genus + species from BLAST subject title."""
    words = stitle.strip().split()
    if len(words) >= 2:
        genus, species = words[0], words[1]
        if species.startswith("strain") or species.startswith("ATCC"):
            return genus + " sp."
        return f"{genus} {species}"
    return ""
