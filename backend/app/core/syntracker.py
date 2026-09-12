"""Synteny conservation analysis using Prodigal protein hashing.

Computes pairwise synteny scores between isolates by:
1. Loading Prodigal protein predictions (genes.faa) for each sample
2. Hashing each protein sequence (MD5) to get position-independent gene IDs
3. Finding shared genes between each pair of samples
4. Computing gene-order concordance (synteny score) from positional correlation

This is fast (pure Python, no BLAST) and reuses existing pipeline output.
Works well for same-species comparisons where most genes are identical.
"""

import hashlib
import logging
import os
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.models.models import Sample, SampleStatus, ARGResult, MobilityResult, PlasmidResult

logger = logging.getLogger(__name__)


def _get_prodigal_faa(sample_id: str) -> Optional[str]:
    """Find Prodigal protein FASTA for a sample."""
    faa = os.path.join(settings.RESULTS_DIR, str(sample_id), "prodigal", "genes.faa")
    return faa if os.path.exists(faa) else None


def _load_gene_hashes(faa_path: str) -> List[Tuple[str, str, int, int, int]]:
    """Load proteins from Prodigal .faa and hash each sequence.

    Returns list of (md5_hash, contig, start, end, strand) tuples,
    ordered by genomic position (contig, start).
    """
    genes = []
    current_header = None
    current_seq = []

    with open(faa_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                if current_header and current_seq:
                    seq = "".join(current_seq)
                    md5 = hashlib.md5(seq.encode()).hexdigest()
                    parsed = _parse_prodigal_header(current_header)
                    if parsed:
                        genes.append((md5, *parsed))
                current_header = line[1:]
                current_seq = []
            else:
                current_seq.append(line)

        # Last entry
        if current_header and current_seq:
            seq = "".join(current_seq)
            md5 = hashlib.md5(seq.encode()).hexdigest()
            parsed = _parse_prodigal_header(current_header)
            if parsed:
                genes.append((md5, *parsed))

    # Sort by contig then start position
    genes.sort(key=lambda g: (g[1], g[2]))
    return genes


def _parse_prodigal_header(header: str) -> Optional[Tuple[str, int, int, int]]:
    """Parse Prodigal FASTA header to extract contig, start, end, strand.

    Format: contig_10_1 # 2 # 1078 # 1 # ID=1_1;...
    """
    parts = header.split(" # ")
    if len(parts) < 4:
        return None
    try:
        # Gene name contains contig info
        gene_name = parts[0].strip()
        # Extract contig: everything before the last _N (gene number)
        name_parts = gene_name.rsplit("_", 1)
        contig = name_parts[0] if len(name_parts) > 1 else gene_name

        start = int(parts[1].strip())
        end = int(parts[2].strip())
        strand = int(parts[3].strip())
        return contig, start, end, strand
    except (ValueError, IndexError):
        return None


def _compute_synteny_score(
    genes_a: List[Tuple[str, str, int, int, int]],
    genes_b: List[Tuple[str, str, int, int, int]],
) -> Tuple[float, int, int]:
    """Compute synteny conservation score between two gene sets.

    Finds shared genes (by protein hash), then measures how well their
    relative order is preserved using a concordance metric.

    Returns (synteny_score, shared_genes, total_comparisons).
    synteny_score ranges from 0.0 (completely rearranged) to 1.0 (perfect synteny).
    """
    # Build hash → position index for each genome
    # Position = sequential index in genome order (already sorted)
    hash_to_pos_a = {}
    for idx, (md5, contig, start, end, strand) in enumerate(genes_a):
        if md5 not in hash_to_pos_a:
            hash_to_pos_a[md5] = idx

    hash_to_pos_b = {}
    for idx, (md5, contig, start, end, strand) in enumerate(genes_b):
        if md5 not in hash_to_pos_b:
            hash_to_pos_b[md5] = idx

    # Find shared hashes (using first occurrence only)
    shared = set(hash_to_pos_a.keys()) & set(hash_to_pos_b.keys())
    n_shared = len(shared)

    if n_shared < 3:
        return 0.0, n_shared, 0

    # Get position pairs for shared genes
    shared_list = sorted(shared, key=lambda h: hash_to_pos_a[h])
    positions_a = [hash_to_pos_a[h] for h in shared_list]
    positions_b = [hash_to_pos_b[h] for h in shared_list]

    # Compute Kendall tau-like concordance
    # Count concordant vs discordant pairs
    concordant = 0
    discordant = 0
    n = len(positions_a)

    # Sample pairs if too many (>1000 shared genes is common)
    if n > 500:
        # Use a fast approximation: check adjacent pairs only
        for i in range(n - 1):
            if (positions_a[i + 1] - positions_a[i]) * (positions_b[i + 1] - positions_b[i]) > 0:
                concordant += 1
            else:
                discordant += 1
    else:
        for i in range(n):
            for j in range(i + 1, n):
                if (positions_a[j] - positions_a[i]) * (positions_b[j] - positions_b[i]) > 0:
                    concordant += 1
                else:
                    discordant += 1

    total = concordant + discordant
    if total == 0:
        return 1.0, n_shared, 0

    # Kendall tau: (concordant - discordant) / total, mapped to [0, 1]
    tau = (concordant - discordant) / total
    score = (tau + 1.0) / 2.0  # Map from [-1,1] to [0,1]

    return round(score, 4), n_shared, total


def _norm_contig(c) -> str:
    """FASTA identifier = text before the first whitespace.

    Tools disagree on what they store: AMRFinderPlus writes the ID only
    ("contig_1") while MobileElementFinder keeps the whole header
    ("contig_1 polypolish"), so a raw == comparison between an ARG contig and
    an MGE contig never matches and every ARG looks non-mobile.
    """
    return (c or "").split()[0] if c else ""


def _get_anchor_regions(sample_id: str, db, flanking: int = 20000) -> List[Tuple[str, int, int]]:
    """Get genomic regions around ARGs and mobile elements.

    Returns list of (contig, start, end) regions, merged if overlapping.
    """
    regions = []

    # ARG positions
    for a in db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all():
        if a.contig and a.start is not None and a.end is not None:
            regions.append((_norm_contig(a.contig), max(0, a.start - flanking), a.end + flanking))

    # Mobile element positions
    for m in db.query(MobilityResult).filter(MobilityResult.sample_id == sample_id).all():
        if m.contig and m.start is not None and m.end is not None:
            regions.append((_norm_contig(m.contig), max(0, m.start - flanking), m.end + flanking))

    if not regions:
        return []

    # Merge overlapping regions per contig
    by_contig = {}
    for contig, start, end in regions:
        if contig not in by_contig:
            by_contig[contig] = []
        by_contig[contig].append((start, end))

    merged = []
    for contig, intervals in by_contig.items():
        intervals.sort()
        cur_start, cur_end = intervals[0]
        for s, e in intervals[1:]:
            if s <= cur_end:
                cur_end = max(cur_end, e)
            else:
                merged.append((contig, cur_start, cur_end))
                cur_start, cur_end = s, e
        merged.append((contig, cur_start, cur_end))

    return merged


def _filter_genes_by_regions(
    genes: List[Tuple[str, str, int, int, int]],
    regions: List[Tuple[str, int, int]],
) -> List[Tuple[str, str, int, int, int]]:
    """Keep only genes that overlap with any anchor region."""
    if not regions:
        return genes

    filtered = []
    for gene in genes:
        md5, contig, start, end, strand = gene
        for r_contig, r_start, r_end in regions:
            if _norm_contig(contig) == r_contig and start < r_end and end > r_start:
                filtered.append(gene)
                break
    return filtered


def compute_synteny_for_samples(sample_ids: List[str], db, mode: str = "full", flanking: int = 20000) -> Dict:
    """Compute all-vs-all synteny scores for selected samples.

    Args:
        mode: "full" = entire genome, "regions" = only near ARGs/MGEs
        flanking: bp flanking distance around ARG/MGE anchors (default 20kb)

    Returns:
        {
            "samples": [...], "sample_ids": [...],
            "synteny_matrix": [[...]], "shared_genes_matrix": [[...]],
            "mode": "full" | "regions", "flanking": int,
        }
    """
    # Load samples and their protein hashes
    sample_info = []  # [(sample, genes)]
    for sid in sample_ids:
        s = db.query(Sample).filter(Sample.id == sid).first()
        if not s:
            continue
        faa = _get_prodigal_faa(str(s.id))
        if faa:
            genes = _load_gene_hashes(faa)
            if genes:
                if mode == "regions":
                    regions = _get_anchor_regions(str(s.id), db, flanking)
                    genes = _filter_genes_by_regions(genes, regions)
                if genes:
                    sample_info.append((s, genes))

    if len(sample_info) < 2:
        return {
            "samples": [s.name for s, _ in sample_info],
            "sample_ids": [str(s.id) for s, _ in sample_info],
            "synteny_matrix": [[1.0]] if sample_info else [],
            "shared_genes_matrix": [[0]] if sample_info else [],
            "message": "Need at least 2 samples with Prodigal annotations.",
        }

    n = len(sample_info)
    synteny_matrix = [[1.0] * n for _ in range(n)]
    shared_matrix = [[0] * n for _ in range(n)]

    for i in range(n):
        genes_i = sample_info[i][1]
        shared_matrix[i][i] = len(set(g[0] for g in genes_i))
        for j in range(i + 1, n):
            genes_j = sample_info[j][1]
            score, n_shared, _ = _compute_synteny_score(genes_i, genes_j)
            synteny_matrix[i][j] = score
            synteny_matrix[j][i] = score
            shared_matrix[i][j] = n_shared
            shared_matrix[j][i] = n_shared

    # Reorder by similarity (greedy nearest-neighbor) so most similar pairs are adjacent
    if n >= 3:
        visited = [False] * n
        order = [0]
        visited[0] = True
        for _ in range(n - 1):
            cur = order[-1]
            best_idx = -1
            best_score = -1.0
            for j in range(n):
                if not visited[j] and synteny_matrix[cur][j] > best_score:
                    best_score = synteny_matrix[cur][j]
                    best_idx = j
            if best_idx >= 0:
                order.append(best_idx)
                visited[best_idx] = True

        # Reorder sample_info, matrices
        sample_info = [sample_info[i] for i in order]
        new_syn = [[synteny_matrix[i][j] for j in order] for i in order]
        new_shared = [[shared_matrix[i][j] for j in order] for i in order]
        synteny_matrix = new_syn
        shared_matrix = new_shared

    # Build mobile ARGs table: ARGs within flanking distance of MGEs
    mobile_args_table = None
    if mode == "regions" and len(sample_info) >= 2:
        # For each sample, find ARGs near MGEs + plasmid replicon info
        sample_mobile_args = {}
        for s, genes in sample_info:
            sid = str(s.id)
            args = db.query(ARGResult).filter(ARGResult.sample_id == sid).all()
            mges = db.query(MobilityResult).filter(MobilityResult.sample_id == sid).all()
            plasmids = db.query(PlasmidResult).filter(PlasmidResult.sample_id == sid).all()

            # Build contig → plasmid replicon mapping
            contig_replicon = {}
            for p in plasmids:
                if p.replicon:
                    # MOB-recon assigns contigs to plasmid clusters
                    # Match via ARG contig_type which contains plasmid_id
                    for a in args:
                        if a.on_plasmid and a.contig_type and p.plasmid_id and p.plasmid_id in a.contig_type:
                            contig_replicon[_norm_contig(a.contig)] = p.replicon

            mobile = []
            for a in args:
                if not a.contig or a.start is None or a.end is None:
                    continue
                nearest_mge = None
                nearest_dist = float('inf')
                for m in mges:
                    if not m.contig or m.start is None or m.end is None:
                        continue
                    if _norm_contig(m.contig) != _norm_contig(a.contig):
                        continue
                    if m.end <= a.start:
                        dist = a.start - m.end
                    elif m.start >= a.end:
                        dist = m.start - a.end
                    else:
                        dist = 0
                    if dist < nearest_dist:
                        nearest_dist = dist
                        nearest_mge = m
                if nearest_mge and nearest_dist <= flanking:
                    replicon = contig_replicon.get(_norm_contig(a.contig), "")
                    mobile.append({
                        "gene": a.gene,
                        "drug_class": a.drug_class or "",
                        "mge_name": nearest_mge.element_type or nearest_mge.family or "IS",
                        "mge_distance": nearest_dist,
                        "contig": a.contig,
                        "on_plasmid": a.on_plasmid or False,
                        "replicon": replicon,
                    })
            sample_mobile_args[s.name] = mobile

        # Find shared mobile ARGs across strains
        all_mobile_genes = {}
        for name, mobile_list in sample_mobile_args.items():
            for m in mobile_list:
                key = m["gene"]
                if key not in all_mobile_genes:
                    all_mobile_genes[key] = {
                        "gene": m["gene"],
                        "drug_class": m["drug_class"],
                        "strains": [],
                        "mge_names": set(),
                        "replicons": set(),
                        "strain_replicons": {},  # strain_name -> replicon
                        "min_distance": m["mge_distance"],
                        "on_plasmid": False,
                    }
                all_mobile_genes[key]["strains"].append(name)
                all_mobile_genes[key]["mge_names"].add(m["mge_name"])
                all_mobile_genes[key]["min_distance"] = min(
                    all_mobile_genes[key]["min_distance"], m["mge_distance"]
                )
                if m["on_plasmid"]:
                    all_mobile_genes[key]["on_plasmid"] = True
                if m["replicon"]:
                    all_mobile_genes[key]["replicons"].add(m["replicon"])
                    all_mobile_genes[key]["strain_replicons"][name] = m["replicon"]

        # Convert to list, sorted by number of strains (shared first)
        mobile_args_list = []
        sample_names = [s.name for s, _ in sample_info]
        for info in sorted(all_mobile_genes.values(), key=lambda x: (-len(x["strains"]), x["gene"])):
            replicons = sorted(info["replicons"])
            # Check if the same replicon appears in multiple strains (same plasmid family)
            same_plasmid = False
            if len(info["strain_replicons"]) >= 2:
                rep_values = list(info["strain_replicons"].values())
                same_plasmid = len(set(rep_values)) < len(rep_values) or any(
                    rep_values.count(r) >= 2 for r in set(rep_values)
                )
                # Also check if any single replicon appears in 2+ strains
                from collections import Counter
                rep_counts = Counter(rep_values)
                same_plasmid = any(c >= 2 for c in rep_counts.values())

            mobile_args_list.append({
                "gene": info["gene"],
                "drug_class": info["drug_class"],
                "mge_names": sorted(info["mge_names"]),
                "min_distance": info["min_distance"],
                "on_plasmid": info["on_plasmid"],
                "replicons": replicons,
                "same_plasmid_family": same_plasmid,
                "strain_replicons": info["strain_replicons"],
                "strain_count": len(info["strains"]),
                "strains": info["strains"],
                "present_in": {name: name in info["strains"] for name in sample_names},
            })

        mobile_args_table = {
            "sample_names": sample_names,
            "genes": mobile_args_list,
            "flanking": flanking,
            "total_mobile_args": len(mobile_args_list),
            "shared_count": sum(1 for g in mobile_args_list if g["strain_count"] > 1),
        }

    # Build region diagrams when in regions mode
    # Use individual (non-merged) ARG/MGE anchors so each diagram region = exactly 2*flanking
    region_diagrams = None
    if mode == "regions" and len(sample_info) >= 2:
        region_diagrams = []
        for s, genes in sample_info:
            # Get individual anchor points (not merged)
            anchors = []
            for a in db.query(ARGResult).filter(ARGResult.sample_id == s.id).all():
                if a.contig and a.start is not None and a.end is not None:
                    mid = (a.start + a.end) // 2
                    anchors.append((_norm_contig(a.contig), max(0, mid - flanking), mid + flanking, a.gene, "arg"))
            for m in db.query(MobilityResult).filter(MobilityResult.sample_id == s.id).all():
                if m.contig and m.start is not None and m.end is not None:
                    mid = (m.start + m.end) // 2
                    anchors.append((_norm_contig(m.contig), max(0, mid - flanking), mid + flanking, m.element_type or m.family, "mge"))
            # Deduplicate overlapping anchors: keep the one with ARG priority
            # Sort by contig + start, skip if too close to previous
            anchors.sort(key=lambda x: (x[0], x[1]))
            deduped = []
            for anc in anchors:
                if deduped and anc[0] == deduped[-1][0] and anc[1] < deduped[-1][2]:
                    # Overlapping — keep ARG over MGE
                    if anc[4] == "arg" and deduped[-1][4] != "arg":
                        deduped[-1] = anc
                    continue
                deduped.append(anc)
            regions = [(a[0], a[1], a[2]) for a in deduped]
            sample_regions = []
            for r_contig, r_start, r_end in regions:
                region_genes = []
                for gene in genes:
                    md5, contig, start, end, strand = gene
                    if _norm_contig(contig) == r_contig and start < r_end and end > r_start:
                        # Check if this gene is an ARG or MGE
                        gene_type = "cds"
                        gene_name = None
                        for a in [x for x in db.query(ARGResult).filter(
                            ARGResult.sample_id == s.id
                        ).all() if _norm_contig(x.contig) == _norm_contig(contig)]:
                            if a.start is not None and abs(a.start - start) < 100:
                                gene_type = "arg"
                                gene_name = a.gene
                                break
                        if gene_type == "cds":
                            for m in [x for x in db.query(MobilityResult).filter(
                                MobilityResult.sample_id == s.id
                            ).all() if _norm_contig(x.contig) == _norm_contig(contig)]:
                                if m.start is not None and abs(m.start - start) < 100:
                                    gene_type = "mge"
                                    gene_name = m.element_type or m.family
                                    break
                        region_genes.append({
                            "start": start - r_start,  # relative to region start
                            "end": end - r_start,
                            "strand": strand,
                            "type": gene_type,
                            "name": gene_name,
                            "hash": md5,
                        })
                if region_genes:
                    sample_regions.append({
                        "contig": r_contig,
                        "region_start": r_start,
                        "region_end": r_end,
                        "length": r_end - r_start,
                        "genes": region_genes,
                    })
            region_diagrams.append({
                "name": s.name,
                "sample_id": str(s.id),
                "regions": sample_regions,
            })

    return {
        "samples": [s.name for s, _ in sample_info],
        "sample_ids": [str(s.id) for s, _ in sample_info],
        "synteny_matrix": synteny_matrix,
        "shared_genes_matrix": shared_matrix,
        "mode": mode,
        "flanking": flanking if mode == "regions" else None,
        "region_diagrams": region_diagrams,
        "mobile_args": mobile_args_table,
    }
