"""Pangenome analysis using Prodigal protein hashing.

Builds a gene presence/absence matrix across selected samples by hashing
Prodigal protein sequences. Generates data for circular pangenome
visualization (BRIG-style rings) and core/accessory genome stats.
"""

import hashlib
import logging
import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.models.models import Sample, ARGResult, VirulenceResult

logger = logging.getLogger(__name__)


def _get_prodigal_faa(sample_id: str) -> Optional[str]:
    faa = os.path.join(settings.RESULTS_DIR, str(sample_id), "prodigal", "genes.faa")
    return faa if os.path.exists(faa) else None


def _parse_prodigal_header(header: str):
    """Parse Prodigal FASTA header: >contig_N # start # end # strand # ..."""
    parts = header.split(" # ")
    if len(parts) < 4:
        return None
    try:
        gene_name = parts[0].strip()
        name_parts = gene_name.rsplit("_", 1)
        contig = name_parts[0] if len(name_parts) > 1 else gene_name
        start = int(parts[1].strip())
        end = int(parts[2].strip())
        strand = int(parts[3].strip())
        return contig, start, end, strand
    except (ValueError, IndexError):
        return None


def _load_genes(faa_path: str) -> List[Dict]:
    """Load genes from Prodigal .faa with hash, position, and sequence length."""
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
                        contig, start, end, strand = parsed
                        genes.append({
                            "hash": md5,
                            "contig": contig,
                            "start": start,
                            "end": end,
                            "strand": strand,
                            "length": len(seq),
                        })
                current_header = line[1:]
                current_seq = []
            else:
                current_seq.append(line)

        if current_header and current_seq:
            seq = "".join(current_seq)
            md5 = hashlib.md5(seq.encode()).hexdigest()
            parsed = _parse_prodigal_header(current_header)
            if parsed:
                contig, start, end, strand = parsed
                genes.append({
                    "hash": md5,
                    "contig": contig,
                    "start": start,
                    "end": end,
                    "strand": strand,
                    "length": len(seq),
                })

    genes.sort(key=lambda g: (g["contig"], g["start"]))
    return genes


def compute_pangenome(sample_ids: List[str], db) -> Dict:
    """Compute pangenome for selected samples.

    Returns:
        {
            "reference": {"name": ..., "sample_id": ..., "total_length": ..., "gene_count": ...},
            "samples": [{"name": ..., "sample_id": ..., "gene_count": ..., "shared_with_ref": ...}],
            "stats": {"total_genes": ..., "core": ..., "accessory": ..., "unique": ...},
            "rings": {
                "reference_genes": [{"start": ..., "end": ..., "hash": ..., "type": ...}],
                "sample_rings": [
                    {"name": ..., "segments": [{"start": ..., "end": ..., "present": true/false}]}
                ]
            },
            "gene_frequency": [{"count": N, "genes": M}]  # how many genes in N samples
        }
    """
    # Load all samples
    sample_info = []
    for sid in sample_ids:
        s = db.query(Sample).filter(Sample.id == sid).first()
        if not s:
            continue
        faa = _get_prodigal_faa(str(s.id))
        if not faa:
            continue
        genes = _load_genes(faa)
        if genes:
            sample_info.append((s, genes))

    if len(sample_info) < 2:
        return {"error": "Need at least 2 samples with Prodigal annotations."}

    # Use first sample as reference (largest genome)
    sample_info.sort(key=lambda x: len(x[1]), reverse=True)
    ref_sample, ref_genes = sample_info[0]

    # Build hash sets for all samples
    sample_hashes = []
    for s, genes in sample_info:
        sample_hashes.append((s, set(g["hash"] for g in genes), genes))

    # All unique gene hashes across all samples
    all_hashes = set()
    hash_count = defaultdict(int)  # hash -> number of samples containing it
    for _, hashes, _ in sample_hashes:
        all_hashes.update(hashes)
        for h in hashes:
            hash_count[h] += 1

    n_samples = len(sample_info)
    total_genes = len(all_hashes)
    core_genes = sum(1 for h, c in hash_count.items() if c == n_samples)
    unique_genes = sum(1 for h, c in hash_count.items() if c == 1)
    accessory_genes = total_genes - core_genes - unique_genes

    # Get ARG and VF genes for the reference to highlight in the ring
    ref_arg_contigs = {}  # (contig, start, end) -> gene_name
    ref_vf_contigs = {}
    args = db.query(ARGResult).filter(ARGResult.sample_id == ref_sample.id).all()
    for a in args:
        if a.contig and a.start and a.end:
            ref_arg_contigs[(a.contig, a.start, a.end)] = a.gene
    vfs = db.query(VirulenceResult).filter(VirulenceResult.sample_id == ref_sample.id).all()
    for v in vfs:
        if hasattr(v, 'contig') and v.contig and hasattr(v, 'start') and v.start:
            ref_vf_contigs[(v.contig, v.start, getattr(v, 'end', v.start + 100))] = v.gene

    # Build reference ring with gene positions (linearized across contigs)
    ref_hash_set = sample_hashes[0][1]
    contig_offsets = {}
    offset = 0
    seen_contigs = []
    for g in ref_genes:
        if g["contig"] not in contig_offsets:
            contig_offsets[g["contig"]] = offset
            seen_contigs.append(g["contig"])
        # Update offset to end of this gene
        gene_end = contig_offsets[g["contig"]] + g["end"]
        if gene_end > offset:
            offset = gene_end

    total_length = offset

    # Reference gene features
    reference_features = []
    for g in ref_genes:
        abs_start = contig_offsets[g["contig"]] + g["start"]
        abs_end = contig_offsets[g["contig"]] + g["end"]

        # Determine gene type
        gene_type = "core" if hash_count[g["hash"]] == n_samples else "accessory"

        # Check if it's an ARG or VF
        is_arg = False
        is_vf = False
        arg_name = None
        for (c, s, e), name in ref_arg_contigs.items():
            if g["contig"] == c and abs(g["start"] - s) < 100:
                is_arg = True
                arg_name = name
                break
        if not is_arg:
            for (c, s, e), name in ref_vf_contigs.items():
                if g["contig"] == c and abs(g["start"] - s) < 100:
                    is_vf = True
                    arg_name = name
                    break

        reference_features.append({
            "start": abs_start,
            "end": abs_end,
            "hash": g["hash"],
            "strand": g["strand"],
            "type": "arg" if is_arg else "vf" if is_vf else gene_type,
            "name": arg_name,
            "n_samples": hash_count[g["hash"]],
        })

    # Build comparison rings (one per non-reference sample)
    sample_rings = []
    for s, hashes, genes in sample_hashes[1:]:
        # For each reference gene, check if this sample has it
        segments = []
        for feat in reference_features:
            segments.append({
                "start": feat["start"],
                "end": feat["end"],
                "present": feat["hash"] in hashes,
            })
        shared = sum(1 for seg in segments if seg["present"])
        sample_rings.append({
            "name": s.name,
            "sample_id": str(s.id),
            "gene_count": len(genes),
            "shared_with_ref": shared,
            "segments": segments,
        })

    # Gene frequency distribution
    freq_dist = defaultdict(int)
    for h, c in hash_count.items():
        freq_dist[c] += 1
    gene_frequency = [{"count": k, "genes": v} for k, v in sorted(freq_dist.items())]

    return {
        "reference": {
            "name": ref_sample.name,
            "sample_id": str(ref_sample.id),
            "total_length": total_length,
            "gene_count": len(ref_genes),
        },
        "samples": [
            {"name": s.name, "sample_id": str(s.id), "gene_count": len(genes)}
            for s, genes in sample_info
        ],
        "stats": {
            "total_genes": total_genes,
            "core": core_genes,
            "accessory": accessory_genes,
            "unique": unique_genes,
            "n_samples": n_samples,
        },
        "rings": {
            "reference_features": reference_features,
            "sample_rings": sample_rings,
            "total_length": total_length,
        },
        "gene_frequency": gene_frequency,
    }
