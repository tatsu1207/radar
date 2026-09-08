"""All-vs-all ANI comparison using skani triangle.

Computes pairwise Average Nucleotide Identity (ANI) for all completed
samples in a project. Uses skani triangle mode which is optimized for
many-vs-many comparisons.
"""

import logging
import os
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.db import SessionLocal
from app.models.models import Sample, SampleFile, SampleStatus

logger = logging.getLogger(__name__)

CONDA_ENV = "radar"


def _get_assembly_path(sample_id: str) -> Optional[str]:
    """Find assembly FASTA for a sample."""
    # Standard assembly output
    asm = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly", "assembly.fasta")
    if os.path.exists(asm):
        return asm
    return None


def _run_skani_triangle(sample_info: List[tuple], threads: int = 4) -> Dict:
    """Core function: run skani triangle on a list of (Sample, assembly_path) tuples."""
    if len(sample_info) < 2:
        return {
            "samples": [s.name for s, _ in sample_info],
            "sample_ids": [str(s.id) for s, _ in sample_info],
            "ani_matrix": [[100.0]] if sample_info else [],
            "af_matrix": [[1.0]] if sample_info else [],
            "message": "Need at least 2 samples with assemblies for comparison.",
        }

    n = len(sample_info)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        list_file = f.name
        for _, asm_path in sample_info:
            f.write(asm_path + "\n")

    output_file = tempfile.mktemp(suffix=".tsv")

    try:
        cmd = [
            "conda", "run", "-n", CONDA_ENV,
            "skani", "triangle",
            "-l", list_file,
            "-t", str(threads),
            "-o", output_file,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.error(f"skani triangle failed: {result.stderr[:500]}")
            raise RuntimeError(f"skani triangle failed: {result.stderr[:200]}")

        path_to_idx = {asm: i for i, (_, asm) in enumerate(sample_info)}

        ani_matrix = [[100.0] * n for _ in range(n)]
        af_matrix = [[1.0] * n for _ in range(n)]

        if os.path.exists(output_file):
            with open(output_file) as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("Ref_file"):
                        continue
                    parts = line.split("\t")
                    if len(parts) < 5:
                        continue
                    ref_path, query_path = parts[0], parts[1]
                    ani = float(parts[2])
                    af_ref, af_query = float(parts[3]), float(parts[4])
                    i = path_to_idx.get(ref_path)
                    j = path_to_idx.get(query_path)
                    if i is not None and j is not None:
                        ani_matrix[i][j] = round(ani, 4)
                        ani_matrix[j][i] = round(ani, 4)
                        af_matrix[i][j] = round(af_ref, 4)
                        af_matrix[j][i] = round(af_query, 4)

        return {
            "samples": [s.name for s, _ in sample_info],
            "sample_ids": [str(s.id) for s, _ in sample_info],
            "ani_matrix": ani_matrix,
            "af_matrix": af_matrix,
        }

    finally:
        for f in [list_file, output_file]:
            if os.path.exists(f):
                os.unlink(f)


def compute_project_ani(project_id: str, db, threads: int = 4) -> Dict:
    """Compute all-vs-all ANI for completed samples in a project."""
    samples = (
        db.query(Sample)
        .filter(Sample.project_id == project_id, Sample.status == SampleStatus.complete)
        .order_by(Sample.name)
        .all()
    )
    sample_info = [(s, asm) for s in samples for asm in [_get_assembly_path(str(s.id))] if asm]
    return _run_skani_triangle(sample_info, threads)


def compute_ani_for_samples(sample_ids: List[str], db, threads: int = 4) -> Dict:
    """Compute all-vs-all ANI for a list of sample IDs."""
    sample_info = []
    for sid in sample_ids:
        s = db.query(Sample).filter(Sample.id == sid).first()
        if s:
            asm = _get_assembly_path(str(s.id))
            if asm:
                sample_info.append((s, asm))
    return _run_skani_triangle(sample_info, threads)
