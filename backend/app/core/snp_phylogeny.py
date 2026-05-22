import logging
import os
import subprocess
from datetime import datetime
from typing import List, Optional

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models.models import (
    ComparativeAnalysisJob,
    JobStatus,
    SNPPhylogenyResult,
    Sample,
    SampleFile,
    PairType,
)

logger = logging.getLogger(__name__)

CONDA_SNIPPY = "radar-snippy"


@celery_app.task(name="run_snp_phylogeny", bind=True)
def run_snp_phylogeny(
    self,
    project_id: str,
    job_id: str,
    sample_ids: List[str],
    reference_sample_id: Optional[str] = None,
    run_gubbins: bool = True,
    threads: int = 4,
):
    """Run Snippy core-genome SNP analysis + optional Gubbins recombination filtering.

    Maps reads from each sample against a reference to call SNPs,
    then builds a core-SNP alignment and phylogenetic tree.
    """
    db = SessionLocal()
    try:
        job = db.query(ComparativeAnalysisJob).filter(
            ComparativeAnalysisJob.id == job_id
        ).first()
        if not job:
            return
        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        job.log = "Starting core-genome SNP analysis...\n"
        db.commit()

        results_dir = os.path.join(
            settings.RESULTS_DIR, "projects", str(project_id), "snp_phylogeny"
        )
        os.makedirs(results_dir, exist_ok=True)

        # Determine reference
        ref_path = _get_assembly_path(reference_sample_id or sample_ids[0], db)
        if not ref_path:
            raise RuntimeError("No assembly found for reference sample")

        ref_sample = db.query(Sample).filter(
            Sample.id == (reference_sample_id or sample_ids[0])
        ).first()
        job.log += f"Reference: {ref_sample.name if ref_sample else 'unknown'}\n"
        db.commit()

        # Run Snippy for each sample
        snippy_dirs = []
        for sid in sample_ids:
            if sid == reference_sample_id:
                continue

            sample = db.query(Sample).filter(Sample.id == sid).first()
            if not sample:
                continue

            sample_snippy_dir = os.path.join(results_dir, str(sid))
            snippy_dirs.append(sample_snippy_dir)

            if os.path.exists(os.path.join(sample_snippy_dir, "snps.vcf")):
                job.log += f"  {sample.name}: Snippy output exists, skipping\n"
                db.commit()
                continue

            job.log += f"  Running Snippy for {sample.name}...\n"
            db.commit()

            # Get reads or assembly
            assembly_path = _get_assembly_path(sid, db)
            cmd = [
                "conda", "run", "-n", CONDA_SNIPPY,
                "snippy",
                "--outdir", sample_snippy_dir,
                "--ref", ref_path,
                "--cpus", str(threads),
                "--force",
            ]

            # Prefer reads over assembly for Snippy
            files = db.query(SampleFile).filter(SampleFile.sample_id == sid).all()
            r1 = next((f for f in files if f.pair == PairType.R1), None)
            r2 = next((f for f in files if f.pair == PairType.R2), None)

            if r1 and r2:
                cmd.extend(["--R1", r1.file_path, "--R2", r2.file_path])
            elif assembly_path:
                cmd.extend(["--ctgs", assembly_path])
            else:
                job.log += f"  WARNING: No reads or assembly for {sample.name}\n"
                db.commit()
                continue

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                job.log += f"  WARNING: Snippy failed for {sample.name}: {result.stderr[-200:]}\n"
                db.commit()
                continue

        # Run snippy-core
        job.log += "Running snippy-core...\n"
        db.commit()

        core_prefix = os.path.join(results_dir, "core")
        cmd_core = [
            "conda", "run", "-n", CONDA_SNIPPY,
            "snippy-core",
            "--ref", ref_path,
            "--prefix", core_prefix,
            *snippy_dirs,
        ]

        result = subprocess.run(cmd_core, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            raise RuntimeError(f"snippy-core failed: {result.stderr[-500:]}")

        core_aln = f"{core_prefix}.full.aln"
        core_snp_count = _count_snps(f"{core_prefix}.txt")

        # Build tree with FastTree
        newick_path = os.path.join(results_dir, "core_snp.nwk")
        cmd_tree = [
            "conda", "run", "-n", CONDA_SNIPPY,
            "FastTree", "-gtr", "-nt", core_aln,
        ]
        result = subprocess.run(cmd_tree, capture_output=True, text=True, timeout=1800)
        if result.returncode == 0:
            with open(newick_path, "w") as f:
                f.write(result.stdout)
        else:
            job.log += f"  WARNING: FastTree failed: {result.stderr[-200:]}\n"
            newick_path = None

        # Optional: Gubbins recombination filtering
        newick_recomb = None
        if run_gubbins and os.path.exists(core_aln):
            job.log += "Running Gubbins (recombination filtering)...\n"
            db.commit()
            newick_recomb = _run_gubbins(results_dir, core_aln, threads)
            if newick_recomb:
                job.log += "  Gubbins complete\n"
            else:
                job.log += "  Gubbins failed or skipped (non-critical)\n"
            db.commit()

        # Save result
        snp_result = SNPPhylogenyResult(
            project_id=project_id,
            job_id=job_id,
            reference_sample_id=reference_sample_id or sample_ids[0],
            core_snp_count=core_snp_count,
            newick_path=newick_path,
            newick_recomb_filtered_path=newick_recomb,
            snp_alignment_path=core_aln if os.path.exists(core_aln) else None,
        )
        db.add(snp_result)

        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        job.result_dir = results_dir
        job.log += f"SNP phylogeny complete: {core_snp_count} core SNPs\n"
        db.commit()

        logger.info(f"SNP phylogeny complete for project {project_id}")

    except Exception as e:
        logger.error(f"SNP phylogeny failed: {e}")
        try:
            job = db.query(ComparativeAnalysisJob).filter(
                ComparativeAnalysisJob.id == job_id
            ).first()
            if job:
                job.status = JobStatus.failed
                job.finished_at = datetime.utcnow()
                job.log = (job.log or "") + f"FAILED: {str(e)}\n"
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


def _run_gubbins(results_dir: str, alignment: str, threads: int) -> Optional[str]:
    """Run Gubbins to filter recombination from core alignment."""
    gubbins_dir = os.path.join(results_dir, "gubbins")
    os.makedirs(gubbins_dir, exist_ok=True)
    prefix = os.path.join(gubbins_dir, "gubbins")

    cmd = [
        "conda", "run", "-n", CONDA_SNIPPY,
        "run_gubbins.py",
        "--threads", str(threads),
        "--prefix", prefix,
        alignment,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            return None

        tree_file = f"{prefix}.final_tree.tre"
        if os.path.exists(tree_file):
            return tree_file
    except Exception:
        pass

    return None


def _get_assembly_path(sample_id: str, db) -> Optional[str]:
    """Find assembly FASTA for a sample."""
    assembly = os.path.join(
        settings.RESULTS_DIR, str(sample_id), "assembly", "assembly.fasta"
    )
    if os.path.exists(assembly):
        return assembly

    files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
    fasta_exts = (".fasta", ".fa", ".fna")
    for f in files:
        if any(f.file_path.endswith(ext) for ext in fasta_exts):
            return f.file_path
    return None


def _count_snps(txt_file: str) -> int:
    """Count core SNPs from snippy-core stats file."""
    if not os.path.exists(txt_file):
        return 0
    try:
        with open(txt_file) as f:
            for line in f:
                if line.startswith("CoreSNP"):
                    return int(line.strip().split("\t")[-1])
    except Exception:
        pass
    return 0
