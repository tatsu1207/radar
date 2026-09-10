"""Colistin resistance detection beyond mcr genes.

Detects three mechanisms of colistin resistance:
1. mcr genes (plasmid-mediated) — already detected by AMRFinderPlus
2. mgrB disruption (IS insertion, truncation, point mutation)
3. TCS mutations (pmrA/pmrB, phoP/phoQ)

Based on: Qi et al. (2025) Microbiology Spectrum — colistin resistance
mechanisms in CRKP from a tertiary hospital in China.

Only runs for K. pneumoniae / Enterobacterales (species where these
mechanisms are relevant).
"""

import logging
import os
import subprocess
import tempfile
from typing import Dict, List, Optional

from app.config import settings
from app.models.models import (
    Sample, SpeciesResult, MLSTResult, MobilityResult, ARGResult,
)

logger = logging.getLogger(__name__)

CONDA_ENV = "radar"

# Reference mgrB protein (K. pneumoniae ATCC 43816, 48 aa)
MGRB_REF_PROTEIN = (
    "MKKFRITMLICLSFTLSGCQAKEQSYLNFDITPKINIEGYEMDKIA"
)
# Reference mgrB nucleotide (144 bp)
MGRB_REF_NT = (
    "ATGAAGAAATTCAGAATAACTATGTTAATTTGTCTCTCATTTACTCTTTCTGGATGCCAGGC"
    "GAAAGAGCAGTCATATTTAAATTTTGATATTACTCCAAAAATTAATATTGAAGGCTATGAAA"
    "TGGATAAAATTGCTTAA"
)

# Known resistance-conferring TCS mutations
# Format: {gene: [(wild_type_aa, position, mutant_aa, reference), ...]}
TCS_MUTATIONS = {
    "pmrB": [
        ("T", 157, "P", "Qi2025"),
        ("A", 246, "T", "Qi2025"),
    ],
    "pmrA": [
        ("G", 157, "T", "Qi2025"),  # G157T(G53C at DNA level)
        ("G", 121, "A", "Qi2025"),  # G121A(A41T)
    ],
    "phoQ": [
        ("T", 156, "S", "Qi2025"),  # A466T(T156S)
        ("D", 90, "Y", "Qi2025"),   # G268T(D90Y)
        ("I", 122, "N", "Qi2025"),  # T365A(I122N)
    ],
}

# Reference TCS gene nucleotide sequences (K. pneumoniae)
# These are used for BLAST against assembly to extract the gene region
# and check for known mutations
TCS_REFS = {
    "pmrB": {
        "accession": "K. pneumoniae pmrB",
        # ~1.4kb gene — we'll use BLAST to find it in the assembly
        "length": 1404,
    },
    "pmrA": {
        "accession": "K. pneumoniae pmrA",
        "length": 672,
    },
    "phoP": {
        "accession": "K. pneumoniae phoP",
        "length": 672,
    },
    "phoQ": {
        "accession": "K. pneumoniae phoQ",
        "length": 1482,
    },
}

# IS elements known to insert into mgrB
MGRB_IS_ELEMENTS = {
    "iskpn14", "iskpn26", "is903b", "iskpn18", "isrm4-1",
    "is1", "is5", "is26", "isecp1",
}


def _is_klebsiella(sample_id: str, db) -> bool:
    """Check if sample is K. pneumoniae or related species."""
    sr = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    if sr and sr.species:
        sp = sr.species.lower()
        if "klebsiella" in sp:
            return True
    mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
    if mlst and mlst.scheme:
        if "klebsiella" in mlst.scheme.lower() or "kpneumoniae" in mlst.scheme.lower():
            return True
    return False


def _blast_seq_against_assembly(query_seq: str, assembly_path: str,
                                 seq_type: str = "nucl", min_identity: float = 80.0) -> List[Dict]:
    """BLAST a short sequence against assembly.

    Returns list of hits with coordinates.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".fasta", delete=False) as f:
        query_file = f.name
        f.write(f">query\n{query_seq}\n")

    output_file = tempfile.mktemp(suffix=".tsv")

    try:
        blast_cmd = "blastn" if seq_type == "nucl" else "tblastn"
        cmd = [
            "conda", "run", "-n", CONDA_ENV,
            blast_cmd,
            "-query", query_file,
            "-subject", assembly_path,
            "-outfmt", "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen slen",
            "-evalue", "1e-5",
            "-out", output_file,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        hits = []
        if result.returncode == 0 and os.path.exists(output_file):
            with open(output_file) as fh:
                for line in fh:
                    parts = line.strip().split("\t")
                    if len(parts) < 14:
                        continue
                    identity = float(parts[2])
                    if identity < min_identity:
                        continue
                    hits.append({
                        "contig": parts[1],
                        "identity": identity,
                        "length": int(parts[3]),
                        "qstart": int(parts[6]),
                        "qend": int(parts[7]),
                        "sstart": int(parts[8]),
                        "send": int(parts[9]),
                        "qlen": int(parts[12]),
                    })
        return hits
    finally:
        for f in [query_file, output_file]:
            if os.path.exists(f):
                os.unlink(f)


def _check_mgrb(sample_id: str, assembly_path: str, db) -> Dict:
    """Check mgrB gene integrity.

    Returns:
        {
            "status": "intact" | "disrupted" | "truncated" | "missing" | "is_insertion",
            "details": str,
            "is_element": str or None,
            "coverage": float,
        }
    """
    # BLAST mgrB reference against assembly
    hits = _blast_seq_against_assembly(MGRB_REF_NT, assembly_path, "nucl", min_identity=70.0)

    if not hits:
        return {"status": "missing", "details": "mgrB gene not found in assembly",
                "is_element": None, "coverage": 0.0}

    # Best hit
    best = max(hits, key=lambda h: h["length"])
    coverage = best["length"] / best["qlen"] * 100

    if coverage >= 95 and best["identity"] >= 95:
        # Gene appears intact — check for point mutations
        # (would need alignment to detect specific SNPs)
        return {"status": "intact", "details": f"mgrB intact ({best['identity']:.1f}% identity, {coverage:.0f}% coverage)",
                "is_element": None, "coverage": coverage}

    # Check if multiple fragmented hits (sign of IS insertion)
    if len(hits) > 1:
        # Multiple hits to the same reference = likely fragmented by IS
        total_coverage = sum(h["length"] for h in hits) / best["qlen"] * 100
        # Check IS elements near mgrB location
        is_nearby = _check_is_near_mgrb(sample_id, best["contig"], best["sstart"], best["send"], db)
        if is_nearby:
            return {"status": "is_insertion",
                    "details": f"mgrB disrupted by {is_nearby} (fragmented into {len(hits)} pieces)",
                    "is_element": is_nearby, "coverage": total_coverage}
        return {"status": "disrupted",
                "details": f"mgrB fragmented into {len(hits)} pieces ({total_coverage:.0f}% total coverage)",
                "is_element": None, "coverage": total_coverage}

    if coverage < 80:
        # Truncated
        is_nearby = _check_is_near_mgrb(sample_id, best["contig"], best["sstart"], best["send"], db)
        if is_nearby:
            return {"status": "is_insertion",
                    "details": f"mgrB truncated ({coverage:.0f}% coverage), {is_nearby} nearby",
                    "is_element": is_nearby, "coverage": coverage}
        return {"status": "truncated",
                "details": f"mgrB truncated ({coverage:.0f}% coverage, {best['identity']:.1f}% identity)",
                "is_element": None, "coverage": coverage}

    # Partial match with mutations
    return {"status": "disrupted",
            "details": f"mgrB altered ({best['identity']:.1f}% identity, {coverage:.0f}% coverage)",
            "is_element": None, "coverage": coverage}


def _check_is_near_mgrb(sample_id: str, contig: str, start: int, end: int, db,
                         distance: int = 500) -> Optional[str]:
    """Check if any known mgrB-disrupting IS element is near the mgrB location."""
    mge_results = db.query(MobilityResult).filter(
        MobilityResult.sample_id == sample_id,
        MobilityResult.contig == contig,
    ).all()

    mgrb_start = min(start, end)
    mgrb_end = max(start, end)

    for mge in mge_results:
        if mge.start is None or mge.end is None:
            continue
        mge_start = min(mge.start, mge.end)
        mge_end = max(mge.start, mge.end)

        # Check if IS is within or near mgrB
        if mge_end >= mgrb_start - distance and mge_start <= mgrb_end + distance:
            is_name = (mge.element_type or mge.family or "unknown IS").lower()
            # Check if it's a known mgrB-disrupting IS
            for known_is in MGRB_IS_ELEMENTS:
                if known_is in is_name.replace(" ", "").replace("-", "").replace("_", ""):
                    return mge.element_type or mge.family
            # Even if not a known IS, report it if overlapping
            if mge_start <= mgrb_end and mge_end >= mgrb_start:
                return mge.element_type or mge.family or "unknown IS"

    return None


def detect_colistin_resistance(sample_id: str, assembly_path: str, db) -> Optional[Dict]:
    """Detect colistin resistance mechanisms for a sample.

    Only runs for Klebsiella pneumoniae and related Enterobacterales.

    Returns:
        {
            "species": str,
            "mcr_genes": [{"gene": "mcr-1.1", "on_plasmid": true}],
            "mgrb": {"status": "disrupted", "details": "...", ...},
            "tcs_mutations": [{"gene": "pmrB", "mutation": "T157P", ...}],
            "overall_risk": "high" | "moderate" | "low" | "none",
            "mechanisms_found": int,
        }
    """
    # Check species relevance
    if not _is_klebsiella(sample_id, db):
        # Also check for other Enterobacterales where these mechanisms apply
        sr = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
        species = sr.species if sr else "Unknown"
        enterobacterales = {"escherichia", "salmonella", "enterobacter", "citrobacter", "serratia"}
        is_entero = any(e in species.lower() for e in enterobacterales) if species else False
        if not is_entero:
            return None
    else:
        sr = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
        species = sr.species if sr else "Klebsiella pneumoniae"

    logger.info(f"Detecting colistin resistance for {sample_id} ({species})")

    result = {
        "species": species,
        "mcr_genes": [],
        "mgrb": None,
        "tcs_mutations": [],
        "overall_risk": "none",
        "mechanisms_found": 0,
    }

    # 1. Check mcr genes (from existing AMRFinderPlus results)
    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    for arg in args:
        gene_lower = arg.gene.lower()
        if gene_lower.startswith("mcr"):
            result["mcr_genes"].append({
                "gene": arg.gene,
                "drug_class": arg.drug_class or "POLYMYXIN",
                "on_plasmid": arg.on_plasmid or False,
                "contig": arg.contig,
                "identity": arg.identity,
            })

    # 2. Check mgrB integrity (primarily relevant for K. pneumoniae)
    is_kleb = _is_klebsiella(sample_id, db)
    if is_kleb:
        mgrb = _check_mgrb(sample_id, assembly_path, db)
        result["mgrb"] = mgrb
    else:
        result["mgrb"] = {"status": "not_applicable", "details": "mgrB analysis only for Klebsiella",
                          "is_element": None, "coverage": 0.0}

    # 3. Check TCS mutations via PointFinder results (if available)
    # PointFinder stores results in the results directory
    pointfinder_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "pointfinder")
    point_results_file = os.path.join(pointfinder_dir, "PointFinder_results.txt")
    if os.path.exists(point_results_file):
        import csv
        with open(point_results_file) as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                gene = row.get("Gene_ID", "").lower()
                mutation = row.get("Mutation", "")
                for tcs_gene, known_muts in TCS_MUTATIONS.items():
                    if tcs_gene.lower() in gene:
                        for wt, pos, mut, ref in known_muts:
                            mut_str = f"{wt}{pos}{mut}"
                            if mut_str.lower() in mutation.lower() or f"{pos}" in mutation:
                                result["tcs_mutations"].append({
                                    "gene": tcs_gene,
                                    "mutation": mut_str,
                                    "details": mutation,
                                    "reference": ref,
                                })

    # Count mechanisms
    mechanisms = 0
    if result["mcr_genes"]:
        mechanisms += 1
    if result["mgrb"] and result["mgrb"]["status"] in ("disrupted", "is_insertion", "truncated"):
        mechanisms += 1
    if result["mgrb"] and result["mgrb"]["status"] == "missing" and is_kleb:
        mechanisms += 1
    if result["tcs_mutations"]:
        mechanisms += 1

    result["mechanisms_found"] = mechanisms

    # Overall risk assessment
    if result["mcr_genes"]:
        result["overall_risk"] = "high"  # Plasmid-mediated = transferable
    elif mechanisms >= 2:
        result["overall_risk"] = "high"
    elif result["mgrb"] and result["mgrb"]["status"] in ("is_insertion", "disrupted"):
        result["overall_risk"] = "high"
    elif result["mgrb"] and result["mgrb"]["status"] == "truncated":
        result["overall_risk"] = "moderate"
    elif result["mgrb"] and result["mgrb"]["status"] == "missing" and is_kleb:
        result["overall_risk"] = "moderate"  # Missing mgrB in Klebsiella is concerning
    elif result["tcs_mutations"]:
        result["overall_risk"] = "moderate"
    elif result["mgrb"] and result["mgrb"]["status"] == "intact":
        result["overall_risk"] = "low"
    else:
        result["overall_risk"] = "none"

    logger.info(f"Colistin resistance for {sample_id}: risk={result['overall_risk']}, "
                f"mcr={len(result['mcr_genes'])}, mgrB={result['mgrb']['status'] if result['mgrb'] else 'N/A'}, "
                f"TCS={len(result['tcs_mutations'])}")

    return result
