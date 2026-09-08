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

        # Parse ANI file (phylip lower-triangular format):
        # Line 1: count
        # Line 2: path1
        # Line 3: path2 \t ani_to_1
        # Line 4: path3 \t ani_to_1 \t ani_to_2
        # ...
        if os.path.exists(output_file):
            file_paths = []  # ordered paths as they appear in the file
            with open(output_file) as fh:
                lines = [l.strip() for l in fh if l.strip()]
            if lines:
                # First line is count, skip it
                for line in lines[1:]:
                    parts = line.split("\t")
                    path = parts[0]
                    file_paths.append(path)
                    row_idx = len(file_paths) - 1
                    for col_idx, val_str in enumerate(parts[1:]):
                        try:
                            val = float(val_str)
                        except ValueError:
                            continue
                        i = path_to_idx.get(file_paths[row_idx])
                        j = path_to_idx.get(file_paths[col_idx])
                        if i is not None and j is not None:
                            ani_matrix[i][j] = round(val, 4)
                            ani_matrix[j][i] = round(val, 4)

        # Parse AF file (full square matrix with path + values per row)
        af_file = output_file + ".af"
        if os.path.exists(af_file):
            with open(af_file) as fh:
                af_lines = [l.strip() for l in fh if l.strip()]
            if af_lines:
                af_paths = []
                for line in af_lines[1:]:  # skip count line
                    parts = line.split("\t")
                    path = parts[0]
                    af_paths.append(path)
                    row_idx = path_to_idx.get(path)
                    if row_idx is None:
                        continue
                    for col_idx, val_str in enumerate(parts[1:]):
                        if col_idx >= len(af_paths):
                            break
                        col_path = af_paths[col_idx] if col_idx < len(af_paths) else None
                        j = path_to_idx.get(col_path) if col_path else None
                        if j is not None:
                            try:
                                af_matrix[row_idx][j] = round(float(val_str) / 100.0, 4)
                            except ValueError:
                                pass

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
