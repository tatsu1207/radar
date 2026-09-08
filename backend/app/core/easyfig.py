"""EasyFig-style synteny visualization using BLASTn alignments.

Runs pairwise BLASTn between selected assemblies and returns
alignment blocks for rendering as a synteny diagram.
"""

import logging
import os
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.models.models import Sample, ARGResult, VirulenceResult, MobilityResult, BacMetResult

logger = logging.getLogger(__name__)

CONDA_ENV = "radar"


def _get_assembly_path(sample_id: str) -> Optional[str]:
    asm = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly", "assembly.fasta")
    return asm if os.path.exists(asm) else None


def _get_assembly_lengths(fasta_path: str) -> List[Dict]:
    """Parse FASTA to get contig names and lengths."""
    contigs = []
    name = None
    length = 0
    with open(fasta_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                if name is not None:
                    contigs.append({"name": name, "length": length})
                name = line[1:].split()[0]
                length = 0
            else:
                length += len(line)
    if name is not None:
        contigs.append({"name": name, "length": length})
    # Sort by length descending
    contigs.sort(key=lambda c: c["length"], reverse=True)
    return contigs


def _run_blastn_pair(query_fasta: str, subject_fasta: str, threads: int = 4) -> List[Dict]:
    """Run BLASTn between two assemblies and return alignment blocks.

    Returns list of alignment blocks with coordinates in both genomes.
    """
    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False) as f:
        output_file = f.name

    try:
        cmd = [
            "conda", "run", "-n", CONDA_ENV,
            "blastn",
            "-query", query_fasta,
            "-subject", subject_fasta,
            "-outfmt", "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore",
            "-evalue", "1e-10",
            "-max_target_seqs", "10000",
            "-num_threads", str(threads),
            "-out", output_file,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.warning(f"BLASTn failed: {result.stderr[:300]}")
            return []

        blocks = []
        if os.path.exists(output_file):
            with open(output_file) as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) < 12:
                        continue
                    length = int(parts[3])
                    if length < 2000:  # Skip small alignments
                        continue
                    identity = float(parts[2])
                    qstart, qend = int(parts[6]), int(parts[7])
                    sstart, send = int(parts[8]), int(parts[9])
                    # Determine if alignment is inverted
                    inverted = sstart > send
                    blocks.append({
                        "query_contig": parts[0],
                        "subject_contig": parts[1],
                        "identity": round(identity, 1),
                        "length": length,
                        "query_start": qstart,
                        "query_end": qend,
                        "subject_start": min(sstart, send),
                        "subject_end": max(sstart, send),
                        "inverted": inverted,
                    })

        # Sort by query position
        blocks.sort(key=lambda b: (b["query_contig"], b["query_start"]))
        return blocks

    finally:
        if os.path.exists(output_file):
            os.unlink(output_file)


def compute_easyfig(sample_ids: List[str], db, threads: int = 4) -> Dict:
    """Compute pairwise BLASTn alignments for synteny visualization.

    Accepts 2-4 sample IDs. Returns genome info and alignment blocks
    for each adjacent pair.

    Returns:
        {
            "genomes": [
                {
                    "sample_name": "OE_025",
                    "sample_id": "...",
                    "contigs": [{"name": "contig_1", "length": 5000000}, ...],
                    "total_length": 5200000,
                },
                ...
            ],
            "alignments": [
                {
                    "query_idx": 0,  # index into genomes array
                    "subject_idx": 1,
                    "blocks": [
                        {
                            "query_contig": "contig_1",
                            "subject_contig": "contig_1",
                            "identity": 99.5,
                            "length": 50000,
                            "query_start": 100,
                            "query_end": 50100,
                            "subject_start": 200,
                            "subject_end": 50200,
                            "inverted": false,
                        },
                        ...
                    ],
                },
                ...
            ],
        }
    """
    # Load samples and assemblies
    sample_info = []
    for sid in sample_ids:
        s = db.query(Sample).filter(Sample.id == sid).first()
        if not s:
            continue
        asm = _get_assembly_path(str(s.id))
        if asm:
            contigs = _get_assembly_lengths(asm)
            total = sum(c["length"] for c in contigs)
            sample_info.append({
                "sample": s,
                "assembly": asm,
                "contigs": contigs,
                "total_length": total,
            })

    if len(sample_info) < 2:
        return {"genomes": [], "alignments": [],
                "message": "Need at least 2 samples with assemblies."}

    # Reorder by genome size (largest first) — simple, fast, no extra BLAST
    # Previous similarity-based reordering added 6+ BLAST runs and 30+ seconds
    sample_info.sort(key=lambda x: x["total_length"], reverse=True)

    genomes = []
    for info in sample_info:
        sid = info["sample"].id
        features = []

        # ARGs
        for a in db.query(ARGResult).filter(ARGResult.sample_id == sid).all():
            if a.contig and a.start is not None and a.end is not None:
                features.append({
                    "type": "arg", "name": a.gene, "contig": a.contig,
                    "start": a.start, "end": a.end,
                })

        # Virulence factors
        for v in db.query(VirulenceResult).filter(VirulenceResult.sample_id == sid).all():
            if hasattr(v, 'contig') and v.contig and hasattr(v, 'start') and v.start is not None:
                features.append({
                    "type": "vf", "name": v.gene, "contig": v.contig,
                    "start": v.start, "end": getattr(v, 'end', v.start + 500),
                })

        # Mobile elements (IS elements)
        for m in db.query(MobilityResult).filter(MobilityResult.sample_id == sid).all():
            if m.contig and m.start is not None and m.end is not None:
                features.append({
                    "type": "mge", "name": m.element_type or m.family or "IS",
                    "contig": m.contig, "start": m.start, "end": m.end,
                })

        # Metal/biocide resistance (BacMet)
        for b in db.query(BacMetResult).filter(BacMetResult.sample_id == sid).all():
            if hasattr(b, 'contig') and b.contig and hasattr(b, 'start') and b.start is not None:
                features.append({
                    "type": "mrg", "name": b.gene, "contig": b.contig,
                    "start": b.start, "end": getattr(b, 'end', b.start + 500),
                })

        genomes.append({
            "sample_name": info["sample"].name,
            "sample_id": str(info["sample"].id),
            "contigs": info["contigs"][:20],
            "total_length": info["total_length"],
            "features": features,
        })

    # Run pairwise BLASTn for adjacent pairs
    alignments = []
    for i in range(len(sample_info) - 1):
        j = i + 1
        blocks = _run_blastn_pair(
            sample_info[i]["assembly"],
            sample_info[j]["assembly"],
            threads=threads,
        )
        alignments.append({
            "query_idx": i,
            "subject_idx": j,
            "blocks": blocks,
        })

    return {"genomes": genomes, "alignments": alignments}


def _quick_similarity(fasta_a: str, fasta_b: str, threads: int = 4) -> int:
    """Quick BLASTn to estimate total aligned bases between two assemblies."""
    with tempfile.NamedTemporaryFile(suffix=".tsv", delete=False) as f:
        output_file = f.name
    try:
        cmd = [
            "conda", "run", "-n", CONDA_ENV,
            "blastn", "-query", fasta_a, "-subject", fasta_b,
            "-outfmt", "6 length",
            "-evalue", "1e-10", "-max_target_seqs", "5000",
            "-num_threads", str(threads),
            "-out", output_file,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return 0
        total = 0
        with open(output_file) as f:
            for line in f:
                v = line.strip()
                if v:
                    total += int(v)
        return total
    except Exception:
        return 0
    finally:
        if os.path.exists(output_file):
            os.unlink(output_file)


def _reorder_by_similarity(sample_info: list, threads: int) -> list:
    """Reorder samples so the most similar genomes are adjacent.

    Uses greedy nearest-neighbor: start with the first sample, always
    pick the most similar unvisited sample as next.
    """
    n = len(sample_info)
    if n <= 2:
        return sample_info

    # Compute all pairwise similarities
    sim = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            s = _quick_similarity(
                sample_info[i]["assembly"],
                sample_info[j]["assembly"],
                threads=threads,
            )
            sim[i][j] = s
            sim[j][i] = s

    # Greedy nearest-neighbor ordering
    visited = [False] * n
    order = [0]
    visited[0] = True
    for _ in range(n - 1):
        current = order[-1]
        best_idx = -1
        best_sim = -1
        for j in range(n):
            if not visited[j] and sim[current][j] > best_sim:
                best_sim = sim[current][j]
                best_idx = j
        if best_idx >= 0:
            order.append(best_idx)
            visited[best_idx] = True

    return [sample_info[i] for i in order]
