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
from app.models.models import Sample, SampleStatus

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


def compute_synteny_for_samples(sample_ids: List[str], db) -> Dict:
    """Compute all-vs-all synteny scores for selected samples.

    Returns:
        {
            "samples": ["name1", "name2", ...],
            "sample_ids": ["id1", "id2", ...],
            "synteny_matrix": [[1.0, 0.95, ...], ...],
            "shared_genes_matrix": [[5000, 4200, ...], ...],
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

    return {
        "samples": [s.name for s, _ in sample_info],
        "sample_ids": [str(s.id) for s, _ in sample_info],
        "synteny_matrix": synteny_matrix,
        "shared_genes_matrix": shared_matrix,
    }
