"""Additional ARG context annotations matching annotate_one.sh steps 8-16.

Steps:
  - Prodigal gene prediction
  - sRNA detection (Infernal/Rfam cmscan)
  - Operon structure prediction
  - Gene dosage (copy number)
  - Codon Adaptation Index (CAI)
  - GC content deviation
  - MLST
  - PointFinder (point mutations)
  - IntegronFinder
  - Cross-reference: update ARGResult with all context data
"""

import csv
import logging
import math
import os
import re
import subprocess
from collections import Counter, defaultdict
from typing import List, Optional

from Bio import SeqIO
from Bio.Seq import Seq

from app.config import settings
from app.models.models import ARGResult, MLSTResult, Sample

logger = logging.getLogger(__name__)

CONDA_PRODIGAL = "radar-prodigal"
CONDA_MLST = "radar-mlst"
CONDA_INTEGRON = "radar-integron"
PROXIMITY_BP = 5000


def run_prodigal(sample_id: str, assembly_path: str, threads: int = 4) -> dict:
    """Run Prodigal for gene prediction."""
    logger.info(f"Running Prodigal for sample {sample_id}")
    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "prodigal")
    os.makedirs(results_dir, exist_ok=True)
    gff_path = os.path.join(results_dir, "genes.gff")
    fna_path = os.path.join(results_dir, "genes.fna")

    if os.path.exists(gff_path) and os.path.exists(fna_path):
        return {"gff": gff_path, "fna": fna_path}

    cmd = [
        "conda", "run", "-n", CONDA_PRODIGAL,
        "prodigal", "-i", assembly_path,
        "-o", gff_path, "-f", "gff",
        "-d", fna_path, "-p", "meta",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Prodigal failed: {result.stderr[-500:]}")
    return {"gff": gff_path, "fna": fna_path}


def run_cmscan(sample_id: str, assembly_path: str, db, threads: int = 4) -> str:
    """Run Infernal cmscan against Rfam for sRNA detection.

    Instead of scanning the whole genome, extracts ±5kb flanking regions
    around each ARG, merges overlapping regions, and scans only those.
    Much faster than whole-genome scanning.
    """
    logger.info(f"Running cmscan (ARG flanks only) for sample {sample_id}")
    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "srna")
    os.makedirs(results_dir, exist_ok=True)
    tblout = os.path.join(results_dir, "cmscan_hits.tblout")

    rfam_cm = os.environ.get("RADAR_RFAM_CM",
        os.path.join(os.path.dirname(settings.RESULTS_DIR), "databases", "Rfam.cm"))

    if not os.path.exists(rfam_cm):
        logger.warning(f"Rfam.cm not found at {rfam_cm}, skipping sRNA detection")
        return tblout

    if os.path.exists(tblout):
        return tblout

    # Extract flanking regions around ARGs
    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    if not args:
        return tblout

    contigs = {r.id: r for r in SeqIO.parse(assembly_path, "fasta")}
    by_contig = defaultdict(list)
    for arg in args:
        if not arg.contig or arg.start is None or arg.end is None:
            continue
        if arg.contig not in contigs:
            continue
        clen = len(contigs[arg.contig].seq)
        by_contig[arg.contig].append((
            max(0, arg.start - PROXIMITY_BP),
            min(clen, arg.end + PROXIMITY_BP),
        ))

    # Merge overlapping intervals and write flanks FASTA
    flanks_fa = os.path.join(results_dir, "arg_flanks.fasta")
    with open(flanks_fa, "w") as fout:
        for contig_id, intervals in by_contig.items():
            intervals.sort()
            merged = [intervals[0]]
            for s, e in intervals[1:]:
                if s <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], e))
                else:
                    merged.append((s, e))
            for s, e in merged:
                seq = str(contigs[contig_id].seq[s:e])
                fout.write(f">{contig_id}:{s}-{e}\n{seq}\n")

    if not os.path.getsize(flanks_fa):
        return tblout

    cmd = [
        "cmscan", "--rfam", "--cut_ga", "--noali",
        "--tblout", tblout, "--cpu", str(threads),
        rfam_cm, flanks_fa,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        logger.warning(f"cmscan failed: {result.stderr[-500:]}")

    # Clean up flanks file
    if os.path.exists(flanks_fa):
        os.remove(flanks_fa)

    return tblout


def run_mlst(sample_id: str, assembly_path: str, db) -> Optional[MLSTResult]:
    """Run MLST typing."""
    logger.info(f"Running MLST for sample {sample_id}")
    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "mlst")
    os.makedirs(results_dir, exist_ok=True)
    mlst_tsv = os.path.join(results_dir, "mlst_results.tsv")

    cmd = [
        "conda", "run", "-n", CONDA_MLST,
        "env", "-u", "PERL5LIB", "-u", "PERL_LOCAL_LIB_ROOT",
        "mlst", assembly_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        logger.warning(f"MLST failed: {result.stderr[-500:]}")
        return None

    with open(mlst_tsv, "w") as f:
        f.write(result.stdout)

    parts = result.stdout.strip().split("\t")
    if len(parts) < 3:
        return None

    scheme = parts[1] if parts[1] != "-" else None
    st = parts[2] if parts[2] != "-" else None
    alleles = parts[3:] if len(parts) > 3 else []

    # Delete old
    db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).delete()
    db.flush()

    mr = MLSTResult(
        sample_id=sample_id,
        scheme=scheme,
        sequence_type=st,
        alleles=alleles if alleles else None,
    )
    db.add(mr)
    db.commit()
    logger.info(f"MLST: {scheme} ST{st}")
    return mr


def run_pointfinder(sample_id: str, assembly_path: str, species_hint: str = None, threads: int = 4) -> dict:
    """Run PointFinder for point mutation detection."""
    logger.info(f"Running PointFinder for sample {sample_id}")
    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "pointfinder")
    os.makedirs(results_dir, exist_ok=True)

    pointfinder_db = os.environ.get("RADAR_POINTFINDER_DB",
        os.path.join(os.path.dirname(settings.RESULTS_DIR), "databases", "pointfinder_db"))

    if not os.path.isdir(pointfinder_db):
        logger.warning("PointFinder DB not found, skipping")
        return {}

    # Determine species
    pf_species = _detect_pointfinder_species(sample_id, species_hint)
    if not pf_species:
        logger.info("No supported PointFinder species detected, skipping")
        return {}

    cmd = [
        "python3", "-m", "resfinder",
        "-ifa", assembly_path,
        "-o", results_dir,
        "-c", "-db_point", pointfinder_db,
        "-s", pf_species,
        "--ignore_missing_species",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    # Parse results
    mutations = {}
    point_results = os.path.join(results_dir, "PointFinder_results.txt")
    if os.path.exists(point_results):
        with open(point_results) as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                mutation = row.get("Mutation", row.get("mutation", ""))
                resistance = row.get("Resistance", row.get("resistance", ""))
                gene = row.get("Gene_name", row.get("gene_name", ""))
                if gene:
                    if gene not in mutations:
                        mutations[gene] = []
                    mutations[gene].append(f"{mutation}({resistance})")
    return mutations


def run_integron_finder(sample_id: str, assembly_path: str, db=None, threads: int = 4) -> list:
    """Run IntegronFinder and store results in database."""
    from app.models.models import IntegronResult

    logger.info(f"Running IntegronFinder for sample {sample_id}")
    results_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "integron")
    os.makedirs(results_dir, exist_ok=True)

    assembly_name = os.path.splitext(os.path.basename(assembly_path))[0]
    outdir = os.path.join(results_dir, f"Results_Integron_Finder_{assembly_name}")

    cmd = [
        "conda", "run", "-n", CONDA_INTEGRON,
        "integron_finder", "--local-max",
        "--cpu", str(threads),
        "--outdir", outdir,
        assembly_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

    # Parse integron file — group by integron_id to get full integron regions
    integron_data = {}  # integron_id -> {contig, type, elements, min_start, max_end}
    for root, dirs, files in os.walk(results_dir):
        for fname in files:
            if fname.endswith(".integrons"):
                with open(os.path.join(root, fname)) as f:
                    for line in f:
                        if line.startswith("#") or line.startswith("ID_integron"):
                            continue
                        parts = line.strip().split("\t")
                        if len(parts) < 11:
                            continue
                        try:
                            integ_id = parts[0]
                            contig = parts[1]
                            pos_beg = int(parts[3])
                            pos_end = int(parts[4])
                            integ_type = parts[10]  # complete, CALIN, In0
                            element_type = parts[7]  # attC, protein
                            annotation = parts[8]    # intI, protein, attC

                            if integ_id not in integron_data:
                                integron_data[integ_id] = {
                                    "contig": contig,
                                    "type": integ_type,
                                    "min_start": pos_beg,
                                    "max_end": pos_end,
                                    "cassettes": [],
                                }
                            d = integron_data[integ_id]
                            d["min_start"] = min(d["min_start"], pos_beg)
                            d["max_end"] = max(d["max_end"], pos_end)
                            if d["type"] == "CALIN" and integ_type != "CALIN":
                                d["type"] = integ_type
                            d["cassettes"].append({
                                "element": element_type,
                                "annotation": annotation,
                                "start": pos_beg,
                                "end": pos_end,
                            })
                        except (ValueError, IndexError):
                            pass

    # Save to database
    if db:
        db.query(IntegronResult).filter(IntegronResult.sample_id == sample_id).delete()
        db.commit()

        for integ_id, d in integron_data.items():
            rec = IntegronResult(
                sample_id=sample_id,
                integron_id=integ_id,
                integron_type=d["type"],
                contig=d["contig"],
                start=d["min_start"],
                end=d["max_end"],
                cassettes=d["cassettes"],
            )
            db.add(rec)
        db.commit()

    logger.info(f"IntegronFinder found {len(integron_data)} integrons for sample {sample_id}")
    return list(integron_data.values())


def annotate_arg_context(sample_id: str, assembly_path: str, db, threads: int = 4):
    """Run all context annotations and update ARGResult records.

    This is the main entry point that runs steps 8-16 from annotate_one.sh
    and cross-references everything back to each ARG.
    """
    logger.info(f"Running context annotations for sample {sample_id}")

    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    if not args:
        logger.info("No ARGs to annotate")
        return

    # Load assembly
    contigs = {r.id: str(r.seq) for r in SeqIO.parse(assembly_path, "fasta")}

    # Step 8: Prodigal
    try:
        prodigal_result = run_prodigal(sample_id, assembly_path, threads)
        gff_path = prodigal_result["gff"]
        fna_path = prodigal_result["fna"]
    except Exception as e:
        logger.warning(f"Prodigal failed: {e}")
        gff_path = fna_path = None

    # Step 9: sRNA
    try:
        tblout = run_cmscan(sample_id, assembly_path, db, threads)
    except Exception as e:
        logger.warning(f"cmscan failed: {e}")
        tblout = None

    # Step 14: MLST
    try:
        run_mlst(sample_id, assembly_path, db)
    except Exception as e:
        logger.warning(f"MLST failed: {e}")

    # Step 15: PointFinder
    try:
        point_mutations = run_pointfinder(sample_id, assembly_path, threads=threads)
    except Exception as e:
        logger.warning(f"PointFinder failed: {e}")
        point_mutations = {}

    # Step 16: IntegronFinder
    try:
        integrons = run_integron_finder(sample_id, assembly_path, threads)
    except Exception as e:
        logger.warning(f"IntegronFinder failed: {e}")
        integrons = []

    # ── Parse auxiliary data ──

    # Operon structure from Prodigal GFF
    gene_to_operon = {}
    if gff_path and os.path.exists(gff_path):
        gene_to_operon = _parse_operons(gff_path)

    # Gene dosage
    gene_counts = Counter(a.gene for a in args)

    # CAI reference codon usage
    w_table = {}
    if fna_path and os.path.exists(fna_path):
        w_table = _compute_cai_weights(fna_path)

    # Genome GC
    genome_seq = "".join(contigs.values())
    genome_gc = _gc_content(genome_seq)

    # sRNA hits
    srna_hits = _parse_srna_hits(tblout) if tblout and os.path.exists(tblout) else []

    # ── Update each ARG ──
    for arg in args:
        if not arg.contig or arg.start is None or arg.end is None:
            continue

        seq = contigs.get(arg.contig, "")
        if not seq:
            continue

        # Operon
        best_operon = _find_operon(arg.contig, arg.start, arg.end, gene_to_operon)
        if best_operon:
            arg.operon_size = best_operon[0]
            arg.operon_position = best_operon[1]

        # Gene dosage
        arg.gene_copies = gene_counts.get(arg.gene, 1)

        # CAI
        gene_seq = seq[arg.start - 1:arg.end] if arg.start > 0 else seq[:arg.end]
        if arg.mechanism and "-" in str(arg.mechanism):
            gene_seq = str(Seq(gene_seq).reverse_complement())
        arg.cai = _calc_cai(gene_seq, w_table)

        # Rare codons
        rare_pct, rare_clusters = _calc_rare_codons(gene_seq, w_table)
        arg.rare_codon_pct = rare_pct
        arg.rare_codon_clusters = rare_clusters

        # GC
        arg.gene_gc = _gc_content(gene_seq)
        arg.genome_gc = genome_gc
        if arg.gene_gc is not None and genome_gc is not None:
            arg.gc_deviation = arg.gene_gc - genome_gc

        # sRNA proximity
        nearest_srna, srna_dist = _find_nearest(
            arg.contig, arg.start, arg.end, [(s[0], s[1], s[2], s[3]) for s in srna_hits]
        )
        if nearest_srna:
            arg.nearest_srna = nearest_srna
            arg.nearest_srna_distance = srna_dist

        # Point mutations
        if arg.gene in point_mutations:
            arg.point_mutations = "; ".join(point_mutations[arg.gene])

        # Integron proximity
        for ic, istart, iend, itype in integrons:
            if ic != arg.contig:
                continue
            if arg.start <= iend and arg.end >= istart:
                arg.in_integron = True
                arg.nearest_integron_distance = 0
                arg.nearest_integron_type = itype
                break
            dist = min(abs(arg.start - iend), abs(istart - arg.end))
            if dist <= PROXIMITY_BP:
                if arg.nearest_integron_distance is None or dist < arg.nearest_integron_distance:
                    arg.nearest_integron_distance = dist
                    arg.nearest_integron_type = itype

    db.commit()
    logger.info(f"Context annotations complete for sample {sample_id}")


# ── Helper functions ──

def _parse_operons(gff_path: str, max_gap: int = 100) -> dict:
    """Parse Prodigal GFF and predict operons based on gene proximity + strand."""
    contig_genes = defaultdict(list)
    with open(gff_path) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) < 9 or parts[2] != "CDS":
                continue
            contig_genes[parts[0]].append((parts[0], int(parts[3]), int(parts[4]), parts[6]))

    gene_to_operon = {}
    for contig, genes in contig_genes.items():
        genes.sort(key=lambda x: x[1])
        current = [genes[0]]
        for i in range(1, len(genes)):
            prev, curr = genes[i - 1], genes[i]
            gap = curr[1] - prev[2]
            if curr[3] == prev[3] and 0 <= gap <= max_gap:
                current.append(curr)
            else:
                for pos, g in enumerate(current):
                    gene_to_operon[(g[0], g[1], g[2])] = (len(current), pos + 1)
                current = [curr]
        for pos, g in enumerate(current):
            gene_to_operon[(g[0], g[1], g[2])] = (len(current), pos + 1)
    return gene_to_operon


def _find_operon(contig, start, end, gene_to_operon):
    """Find operon info for an ARG by overlapping with predicted genes."""
    best_overlap = 0
    best = None
    for (gc, gs, ge), (size, pos) in gene_to_operon.items():
        if gc != contig:
            continue
        ov = max(0, min(end, ge) - max(start, gs))
        if ov > best_overlap:
            best_overlap = ov
            best = (size, pos)
    return best


CODON_TABLE = {
    'TTT': 'F', 'TTC': 'F', 'TTA': 'L', 'TTG': 'L', 'CTT': 'L', 'CTC': 'L', 'CTA': 'L', 'CTG': 'L',
    'ATT': 'I', 'ATC': 'I', 'ATA': 'I', 'ATG': 'M', 'GTT': 'V', 'GTC': 'V', 'GTA': 'V', 'GTG': 'V',
    'TCT': 'S', 'TCC': 'S', 'TCA': 'S', 'TCG': 'S', 'CCT': 'P', 'CCC': 'P', 'CCA': 'P', 'CCG': 'P',
    'ACT': 'T', 'ACC': 'T', 'ACA': 'T', 'ACG': 'T', 'GCT': 'A', 'GCC': 'A', 'GCA': 'A', 'GCG': 'A',
    'TAT': 'Y', 'TAC': 'Y', 'TAA': '*', 'TAG': '*', 'CAT': 'H', 'CAC': 'H', 'CAA': 'Q', 'CAG': 'Q',
    'AAT': 'N', 'AAC': 'N', 'AAA': 'K', 'AAG': 'K', 'GAT': 'D', 'GAC': 'D', 'GAA': 'E', 'GAG': 'E',
    'TGT': 'C', 'TGC': 'C', 'TGA': '*', 'TGG': 'W', 'CGT': 'R', 'CGC': 'R', 'CGA': 'R', 'CGG': 'R',
    'AGT': 'S', 'AGC': 'S', 'AGA': 'R', 'AGG': 'R', 'GGT': 'G', 'GGC': 'G', 'GGA': 'G', 'GGG': 'G',
}


def _compute_cai_weights(fna_path: str) -> dict:
    """Compute codon adaptation weights from Prodigal-predicted genes."""
    genome_codons = Counter()
    for rec in SeqIO.parse(fna_path, "fasta"):
        seq = str(rec.seq).upper().replace("U", "T")
        for i in range(0, len(seq) - 2, 3):
            c = seq[i:i + 3]
            if len(c) == 3 and all(b in "ACGT" for b in c):
                genome_codons[c] += 1

    aa_codons = defaultdict(list)
    for codon, aa in CODON_TABLE.items():
        if aa != "*":
            aa_codons[aa].append(codon)

    rscu = {}
    for aa, codons in aa_codons.items():
        total = sum(genome_codons.get(c, 0) for c in codons)
        n = len(codons)
        for c in codons:
            rscu[c] = (genome_codons.get(c, 0) / total * n) if total > 0 else 1.0

    w = {}
    for aa, codons in aa_codons.items():
        max_rscu = max(rscu.get(c, 0) for c in codons)
        for c in codons:
            w[c] = rscu[c] / max_rscu if max_rscu > 0 else 1.0
    return w


def _calc_cai(gene_seq: str, w_table: dict) -> Optional[float]:
    """Calculate Codon Adaptation Index for a gene."""
    if not w_table or not gene_seq:
        return None
    seq = gene_seq.upper().replace("U", "T")
    log_sum = 0.0
    count = 0
    for i in range(0, len(seq) - 2, 3):
        c = seq[i:i + 3]
        if len(c) != 3 or not all(b in "ACGT" for b in c):
            continue
        aa = CODON_TABLE.get(c, "*")
        if aa in ("*", "M", "W"):
            continue
        wc = w_table.get(c, 0)
        if wc > 0:
            log_sum += math.log(wc)
            count += 1
    return math.exp(log_sum / count) if count > 0 else None


def _calc_rare_codons(gene_seq: str, w_table: dict) -> tuple:
    """Count rare codons (w < 0.1) and clusters of consecutive rare codons.

    Returns (rare_codon_pct, rare_codon_clusters).
    """
    if not w_table or not gene_seq or len(gene_seq) < 6:
        return None, None
    seq = gene_seq.upper().replace("U", "T")
    rare = 0
    total = 0
    clusters = 0
    in_cluster = False
    for i in range(0, len(seq) - 2, 3):
        c = seq[i:i + 3]
        if len(c) != 3 or not all(b in "ACGT" for b in c):
            continue
        aa = CODON_TABLE.get(c, "*")
        if aa in ("*", "M", "W"):
            continue
        wc = w_table.get(c, 0)
        total += 1
        if wc < 0.1:
            rare += 1
            if not in_cluster:
                clusters += 1
                in_cluster = True
        else:
            in_cluster = False
    if total == 0:
        return None, None
    return rare / total, clusters


def _gc_content(seq: str) -> Optional[float]:
    """Calculate GC content of a sequence."""
    seq = seq.upper()
    total = sum(1 for c in seq if c in "ACGT")
    if total == 0:
        return None
    gc = sum(1 for c in seq if c in "GC")
    return gc / total


def _parse_srna_hits(tblout: str) -> list:
    """Parse Infernal cmscan tblout format.

    Query names are in format 'contig:start-end' (from flanking extraction).
    Converts positions back to absolute genome coordinates.
    """
    hits = []
    if not os.path.exists(tblout):
        return hits
    with open(tblout) as f:
        for line in f:
            if line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) < 18:
                continue
            target_name = fields[0]
            query_name = fields[2]  # e.g. "1:548465-598752"
            try:
                seq_from = int(fields[7])
                seq_to = int(fields[8])
            except (ValueError, IndexError):
                continue

            # Convert to absolute coordinates
            contig = query_name
            offset = 0
            if ":" in query_name:
                contig = query_name.split(":")[0]
                coords = query_name.split(":")[1]
                if "-" in coords:
                    try:
                        offset = int(coords.split("-")[0])
                    except ValueError:
                        pass

            s, e = min(seq_from, seq_to) + offset, max(seq_from, seq_to) + offset
            hits.append((contig, s, e, target_name))
    return hits


def _find_nearest(contig, start, end, elements):
    """Find nearest element to an ARG within PROXIMITY_BP."""
    best_name = None
    best_dist = None
    for ec, es, ee, name in elements:
        if ec != contig:
            continue
        if start <= ee and end >= es:
            return name, 0
        dist = min(abs(start - ee), abs(es - end))
        if dist <= PROXIMITY_BP and (best_dist is None or dist < best_dist):
            best_name = name
            best_dist = dist
    return best_name, best_dist


def _detect_pointfinder_species(sample_id: str, species_hint: str = None) -> str:
    """Detect PointFinder-supported species from skani/species results."""
    species_map = {
        "escherichia": "escherichia_coli",
        "salmonella": "salmonella",
        "campylobacter jejuni": "campylobacter_jejuni",
        "campylobacter coli": "campylobacter_coli",
        "staphylococcus aureus": "staphylococcus_aureus",
        "mycobacterium tuberculosis": "mycobacterium_tuberculosis",
        "enterococcus faecalis": "enterococcus_faecalis",
        "enterococcus faecium": "enterococcus_faecium",
        "klebsiella": "klebsiella",
        "neisseria gonorrhoeae": "neisseria_gonorrhoeae",
    }

    # Check skani results
    skani_tsv = os.path.join(settings.RESULTS_DIR, str(sample_id), "species", "skani_results.tsv")
    if os.path.exists(skani_tsv):
        with open(skani_tsv) as f:
            for line in f:
                lower = line.lower()
                for key, val in species_map.items():
                    if key in lower:
                        return val

    if species_hint:
        for key, val in species_map.items():
            if key in species_hint.lower():
                return val

    return ""
