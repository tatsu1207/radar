import logging
import traceback
from datetime import datetime

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.models.models import Sample, SampleFile, AnalysisJob, SampleStatus, InputType, JobStatus, PairType

logger = logging.getLogger(__name__)


def _create_job(db, sample_id: str, tool: str, threads: int = 4) -> AnalysisJob:
    job = AnalysisJob(
        sample_id=sample_id,
        tool=tool,
        status=JobStatus.running,
        started_at=datetime.utcnow(),
        threads=threads,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _complete_job(db, job: AnalysisJob, log: str = ""):
    job.status = JobStatus.complete
    job.finished_at = datetime.utcnow()
    job.log = log
    db.commit()


def _fail_job(db, job: AnalysisJob, error: str):
    job.status = JobStatus.failed
    job.finished_at = datetime.utcnow()
    job.log = error
    db.commit()


def _append_master_log(db, master_job_id: str, message: str):
    """Append a progress message to the master job log."""
    if not master_job_id:
        return
    master_job = db.query(AnalysisJob).filter(AnalysisJob.id == master_job_id).first()
    if master_job:
        existing = master_job.log or ""
        master_job.log = existing + message + "\n"
        db.commit()


@celery_app.task(name="run_pipeline", bind=True)
def run_pipeline(self, sample_id: str, master_job_id: str = None, threads: int = 4):
    """Main pipeline orchestration task.

    For FASTQ input: QC (fastp/Filtlong) -> Assembly (SPAdes/Flye+Medaka+Polypolish) -> QUAST/BUSCO -> Annotation
    For FASTA input: Annotation directly
    """
    db = SessionLocal()
    try:
        sample = db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            logger.error(f"Sample {sample_id} not found")
            return

        # Update master job status
        if master_job_id:
            master_job = db.query(AnalysisJob).filter(AnalysisJob.id == master_job_id).first()
            if master_job:
                master_job.status = JobStatus.running
                master_job.started_at = datetime.utcnow()
                master_job.log = "Pipeline started\n"
                db.commit()

        input_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
        file_paths = [f.file_path for f in input_files]

        assembly_path = None

        if sample.input_type == InputType.fastq:
            # ── Step 1: QC with fastp ──
            sample.status = SampleStatus.qc
            db.commit()
            _append_master_log(db, master_job_id, "Step 1: Running fastp QC...")

            from app.core.qc import run_fastp
            qc_job = _create_job(db, sample_id, "fastp", threads)
            try:
                qc_result = run_fastp(sample_id, file_paths, db, threads=threads)
                _complete_job(db, qc_job, f"fastp QC complete")
                _append_master_log(db, master_job_id, "  fastp QC complete")
            except Exception as e:
                _fail_job(db, qc_job, str(e))
                _append_master_log(db, master_job_id, f"  fastp QC FAILED: {e}")
                raise

            # ── Step 2: Genome assembly ──
            sample.status = SampleStatus.assembling
            db.commit()
            _append_master_log(db, master_job_id, "Step 2: Running Genome assembly...")

            from app.core.assembly import run_assembly
            asm_job = _create_job(db, sample_id, "assembly", threads)
            try:
                assembly_path = run_assembly(sample_id, file_paths, db, threads=threads)
                _complete_job(db, asm_job, f"Assembly complete: {assembly_path}")
                _append_master_log(db, master_job_id, f"  Genome assembly complete")
            except Exception as e:
                _fail_job(db, asm_job, str(e))
                _append_master_log(db, master_job_id, f"  Genome assembly FAILED: {e}")
                raise

            # ── Step 2b: Assembly QC (QUAST + BUSCO) ──
            _append_master_log(db, master_job_id, "Step 2b: Running assembly QC (QUAST, BUSCO)...")

            from app.core.assembly import run_quast, run_busco

            quast_job = _create_job(db, sample_id, "quast", threads)
            try:
                quast_metrics = run_quast(sample_id, assembly_path, threads=threads)
                _complete_job(db, quast_job, f"QUAST complete: {quast_metrics}")
                _append_master_log(db, master_job_id, "  QUAST complete")
            except Exception as e:
                _fail_job(db, quast_job, str(e))
                _append_master_log(db, master_job_id, f"  QUAST failed (non-critical): {e}")

            busco_job = _create_job(db, sample_id, "busco", threads)
            try:
                busco_result = run_busco(sample_id, assembly_path, threads=threads)
                _complete_job(db, busco_job, f"BUSCO complete")
                _append_master_log(db, master_job_id, "  BUSCO complete")
            except Exception as e:
                _fail_job(db, busco_job, str(e))
                _append_master_log(db, master_job_id, f"  BUSCO failed (non-critical): {e}")

        elif sample.input_type == InputType.fasta:
            # Use the FASTA file directly as the assembly
            fasta_exts = (".fasta", ".fa", ".fna")
            fasta_files = [f for f in file_paths if any(f.endswith(ext) for ext in fasta_exts)]
            assembly_path = fasta_files[0] if fasta_files else (file_paths[0] if file_paths else None)

        if not assembly_path:
            raise ValueError("No assembly available for annotation")

        # ── Step 3: AMR detection with AMRFinderPlus ──
        sample.status = SampleStatus.annotating
        db.commit()
        _append_master_log(db, master_job_id, "Step 3: Running AMRFinderPlus...")

        from app.core.arg_detect import run_amrfinderplus
        amr_job = _create_job(db, sample_id, "amrfinderplus", threads)
        try:
            run_amrfinderplus(sample_id, assembly_path, db, threads=threads)
            _complete_job(db, amr_job, "AMRFinderPlus analysis complete")
            _append_master_log(db, master_job_id, "  AMRFinderPlus complete")
        except Exception as e:
            _fail_job(db, amr_job, str(e))
            _append_master_log(db, master_job_id, f"  AMRFinderPlus FAILED: {e}")
            raise

        # ── Step 4: Plasmid analysis with MOB-suite ──
        _append_master_log(db, master_job_id, "Step 4: Running MOB-recon...")

        from app.core.plasmid import run_mob_recon
        plasmid_job = _create_job(db, sample_id, "mob_recon", threads)
        try:
            run_mob_recon(sample_id, assembly_path, db, threads=threads)
            _complete_job(db, plasmid_job, "MOB-recon analysis complete")
            _append_master_log(db, master_job_id, "  MOB-recon complete")
        except Exception as e:
            _fail_job(db, plasmid_job, str(e))
            _append_master_log(db, master_job_id, f"  MOB-recon failed (non-critical): {e}")

        # ── Step 5: Mobile elements with MobileElementFinder ──
        _append_master_log(db, master_job_id, "Step 5: Running MobileElementFinder...")

        from app.core.mobility import run_mefinder
        mef_job = _create_job(db, sample_id, "mefinder", threads)
        try:
            run_mefinder(sample_id, assembly_path, db)
            _complete_job(db, mef_job, "MobileElementFinder analysis complete")
            _append_master_log(db, master_job_id, "  MobileElementFinder complete")
        except Exception as e:
            _fail_job(db, mef_job, str(e))
            _append_master_log(db, master_job_id, f"  MobileElementFinder failed (non-critical): {e}")

        # ── Step 6: Phenotype prediction ──
        _append_master_log(db, master_job_id, "Step 6: Phenotype prediction & risk scoring...")

        from app.core.phenotype import predict_phenotype
        pheno_job = _create_job(db, sample_id, "phenotype_prediction", threads)
        try:
            predict_phenotype(sample_id, db)
            _complete_job(db, pheno_job, "Phenotype prediction complete")
            _append_master_log(db, master_job_id, "  Phenotype prediction complete")
        except Exception as e:
            _fail_job(db, pheno_job, str(e))
            _append_master_log(db, master_job_id, f"  Phenotype prediction failed: {e}")

        # ── Step 7: Risk scoring ──
        from app.core.risk import calculate_composite_risk
        risk_job = _create_job(db, sample_id, "risk_scoring", threads)
        try:
            calculate_composite_risk(sample_id, db=db)
            _complete_job(db, risk_job, "Risk scoring complete")
            _append_master_log(db, master_job_id, "  Risk scoring complete")
        except Exception as e:
            _fail_job(db, risk_job, str(e))
            _append_master_log(db, master_job_id, f"  Risk scoring failed: {e}")

        # ── Done ──
        sample.status = SampleStatus.complete
        db.commit()

        if master_job_id:
            master_job = db.query(AnalysisJob).filter(AnalysisJob.id == master_job_id).first()
            if master_job:
                master_job.status = JobStatus.complete
                master_job.finished_at = datetime.utcnow()
                existing_log = master_job.log or ""
                master_job.log = existing_log + "Pipeline completed successfully\n"
                db.commit()

        logger.info(f"Pipeline completed for sample {sample_id}")

    except Exception as e:
        logger.error(f"Pipeline failed for sample {sample_id}: {traceback.format_exc()}")
        try:
            sample = db.query(Sample).filter(Sample.id == sample_id).first()
            if sample:
                sample.status = SampleStatus.failed
                db.commit()

            if master_job_id:
                master_job = db.query(AnalysisJob).filter(AnalysisJob.id == master_job_id).first()
                if master_job:
                    master_job.status = JobStatus.failed
                    master_job.finished_at = datetime.utcnow()
                    existing_log = master_job.log or ""
                    master_job.log = existing_log + f"Pipeline failed: {str(e)}\n"
                    db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()


def _get_assembly_path(sample_id: str, db) -> str:
    """Find the assembly FASTA for a sample."""
    from app.config import settings
    import os

    # Check standard assembly output location
    assembly = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly", "assembly.fasta")
    if os.path.exists(assembly):
        return assembly

    # Check if FASTA input files exist
    input_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
    fasta_exts = (".fasta", ".fa", ".fna")
    for f in input_files:
        if any(f.file_path.endswith(ext) for ext in fasta_exts):
            return f.file_path

    return None


@celery_app.task(name="run_preprocessing", bind=True)
def run_preprocessing(self, sample_id: str, job_id: str, threads: int = 4):
    """Full per-sample pipeline: Assembly (if FASTQ) -> Annotation.

    For FASTQ input: runs QC + assembly, then annotation.
    For FASTA input: skips directly to annotation.
    """
    db = SessionLocal()
    try:
        sample = db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            logger.error(f"Sample {sample_id} not found")
            return

        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        job.log = "Pipeline started\n"
        db.commit()

        # Step 1: Assembly (only for FASTQ input)
        assembly_path = _run_assembly_phase(sample_id, job, db, threads)

        # Step 2: Annotation (runs on assembly FASTA)
        _run_annotation_phase(sample_id, assembly_path, job, db, threads)

        # Done
        sample.status = SampleStatus.complete
        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        job.log += "Pipeline completed successfully\n"
        db.commit()

        logger.info(f"Pipeline complete for sample {sample_id}")

    except Exception as e:
        logger.error(f"Pipeline failed for sample {sample_id}: {traceback.format_exc()}")
        try:
            sample = db.query(Sample).filter(Sample.id == sample_id).first()
            if sample:
                sample.status = SampleStatus.failed
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
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


@celery_app.task(name="run_annotation_only", bind=True)
def run_annotation_only(self, sample_id: str, job_id: str, threads: int = 4):
    """Run annotation pipeline only (for pre-assembled FASTA input).

    Skips QC and assembly steps. Expects an assembly to already exist
    (either from a previous assembly run or from uploaded FASTA).
    """
    db = SessionLocal()
    try:
        sample = db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            logger.error(f"Sample {sample_id} not found")
            return

        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        job.log = "Annotation pipeline started (assembly provided)\n"
        db.commit()

        assembly_path = _get_assembly_path(sample_id, db)
        if not assembly_path:
            raise ValueError("No assembly found. Upload a FASTA file or run assembly first.")

        job.log += f"Using assembly: {assembly_path}\n"
        db.commit()

        _run_annotation_phase(sample_id, assembly_path, job, db, threads)

        sample.status = SampleStatus.complete
        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        job.log += "Annotation pipeline completed successfully\n"
        db.commit()

        logger.info(f"Annotation complete for sample {sample_id}")

    except Exception as e:
        logger.error(f"Annotation failed for sample {sample_id}: {traceback.format_exc()}")
        try:
            sample = db.query(Sample).filter(Sample.id == sample_id).first()
            if sample:
                sample.status = SampleStatus.failed
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
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


def _run_assembly_phase(sample_id: str, job, db, threads: int) -> str:
    """Phase 1: QC + Assembly. Returns assembly path.

    For FASTA input, returns the FASTA path directly (no QC/assembly).
    """
    import os

    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    input_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
    file_paths = [f.file_path for f in input_files]

    # Check if FASTA input — skip QC/assembly entirely
    fasta_exts = (".fasta", ".fa", ".fna")
    fasta_files = [f for f in input_files if any(f.file_path.endswith(ext) for ext in fasta_exts)]
    if fasta_files:
        assembly_path = fasta_files[0].file_path
        job.log += f"── Phase 1: Assembly — skipped (FASTA input: {os.path.basename(assembly_path)})\n"
        db.commit()
        return assembly_path

    has_illumina = any(f.pair in (PairType.R1, PairType.R2) for f in input_files)
    has_long_read = any(f.pair == PairType.long_read for f in input_files)

    # Detect long-read platform
    from app.models.models import SequencingPlatform
    long_read_platform = "ont"
    for f in input_files:
        if f.pair == PairType.long_read and f.platform == SequencingPlatform.pacbio:
            long_read_platform = "pacbio"
            break

    qc_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "qc")
    asm_dir = os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly")
    existing_assembly = os.path.join(asm_dir, "assembly.fasta")

    job.log += "── Phase 1: QC & Assembly ──\n"
    db.commit()

    # fastp for Illumina reads (trimming) or PacBio-only (report only)
    trimmed_r1 = os.path.join(qc_dir, "trimmed_R1.fastq.gz")
    trimmed_r2 = os.path.join(qc_dir, "trimmed_R2.fastq.gz")
    fastp_report = os.path.join(qc_dir, "fastp_report.html")
    if has_illumina and not (os.path.exists(trimmed_r1) and os.path.exists(trimmed_r2)):
        sample.status = SampleStatus.qc
        db.commit()
        job.log += "  Running fastp (Illumina trimming)...\n"
        db.commit()

        from app.core.qc import run_fastp
        try:
            run_fastp(sample_id, file_paths, db, threads=threads)
            job.log += "    fastp complete\n"
            db.commit()
        except Exception as e:
            job.log += f"    fastp FAILED: {e}\n"
            db.commit()
            raise
    elif has_illumina:
        job.log += "  fastp — skipped (trimmed files exist)\n"
        db.commit()
    elif has_long_read and long_read_platform == "pacbio" and not os.path.exists(fastp_report):
        # PacBio-only: fastp report without trimming (matches pipeline.sh)
        sample.status = SampleStatus.qc
        db.commit()
        job.log += "  Running fastp (PacBio QC report)...\n"
        db.commit()

        from app.core.qc import run_fastp
        try:
            run_fastp(sample_id, file_paths, db, threads=threads)
            job.log += "    fastp report complete\n"
            db.commit()
        except Exception as e:
            job.log += f"    fastp report failed (non-critical): {e}\n"
            db.commit()

    # Filtlong for ONT reads only (not PacBio — HiFi reads don't need filtering)
    filtered_long = os.path.join(qc_dir, "filtered_long.fastq.gz")
    if has_long_read and long_read_platform == "ont" and not os.path.exists(filtered_long):
        sample.status = SampleStatus.qc
        db.commit()
        job.log += "  Running Filtlong (ONT filtering)...\n"
        db.commit()

        from app.core.filtlong import run_filtlong
        try:
            run_filtlong(sample_id, file_paths, db, threads=threads)
            job.log += "    Filtlong complete\n"
            db.commit()
        except Exception as e:
            job.log += f"    Filtlong FAILED: {e}\n"
            db.commit()
            raise
    elif has_long_read and long_read_platform == "ont":
        job.log += "  Filtlong — skipped (filtered file exists)\n"
        db.commit()
    elif has_long_read and long_read_platform == "pacbio":
        job.log += "  Filtlong — skipped (PacBio HiFi reads)\n"
        db.commit()

    # Genome assembly
    if os.path.exists(existing_assembly):
        assembly_path = existing_assembly
        job.log += "  Assembly — skipped (assembly exists)\n"
        db.commit()
    else:
        sample.status = SampleStatus.assembling
        db.commit()
        job.log += "  Running Genome assembly...\n"
        db.commit()

        from app.core.assembly import run_assembly
        try:
            assembly_path = run_assembly(sample_id, file_paths, db, threads=threads)
            job.log += "    Assembly complete\n"
            db.commit()
        except Exception as e:
            job.log += f"    Assembly FAILED: {e}\n"
            db.commit()
            raise

    # Assembly QC (QUAST + BUSCO) — skip if reports exist
    import os as _os
    quast_report = _os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly", "quast", "report.tsv")
    busco_dir = _os.path.join(settings.RESULTS_DIR, str(sample_id), "assembly", "busco", "busco_result")
    if not _os.path.exists(quast_report) or not _os.path.isdir(busco_dir):
        job.log += "  Running assembly QC (QUAST + BUSCO)...\n"
        db.commit()
        from app.core.assembly import run_quast, run_busco
        if not _os.path.exists(quast_report):
            _run_noncritical(db, job, "QUAST", lambda: run_quast(sample_id, assembly_path, threads=threads))
        else:
            job.log += "  QUAST — skipped (report exists)\n"
            db.commit()
        if not _os.path.isdir(busco_dir):
            _run_noncritical(db, job, "BUSCO", lambda: run_busco(sample_id, assembly_path, threads=threads))
        else:
            job.log += "  BUSCO — skipped (results exist)\n"
            db.commit()
    else:
        job.log += "  QUAST + BUSCO — skipped (reports exist)\n"
        db.commit()

    return assembly_path


MLST_SCHEME_TO_SPECIES = {
    "ecoli": "Escherichia coli",
    "ecoli_achtman_4": "Escherichia coli",
    "senterica": "Salmonella enterica",
    "klebsiella": "Klebsiella pneumoniae",
    "kpneumoniae": "Klebsiella pneumoniae",
    "saureus": "Staphylococcus aureus",
    "abaumannii": "Acinetobacter baumannii",
    "abaumannii_2": "Acinetobacter baumannii",
    "efaecium": "Enterococcus faecium",
    "efaecalis": "Enterococcus faecalis",
}


def _reconcile_species_with_mlst(sample_id: str, job, db):
    """Update species result if MLST scheme gives a more reliable identification.

    MLST is more reliable than 16S BLAST for closely related species
    (e.g. E. coli vs Shigella, which are genomically identical by 16S).
    """
    from app.models.models import MLSTResult, SpeciesResult

    mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
    if not mlst or not mlst.scheme:
        return

    mlst_species = MLST_SCHEME_TO_SPECIES.get(mlst.scheme.lower())
    if not mlst_species:
        return

    sr = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    if not sr:
        # No species result yet — create one from MLST
        sr = SpeciesResult(
            sample_id=sample_id,
            species=mlst_species,
            method="mlst",
        )
        db.add(sr)
        db.commit()
        job.log += f"  Species updated from MLST: {mlst_species}\n"
        db.commit()
        return

    # Check if current species disagrees with MLST
    current = sr.species.lower() if sr.species else ""
    mlst_lower = mlst_species.lower()
    # If they already agree (e.g. both say E. coli), do nothing
    if mlst_lower.split()[0] in current:
        return

    # MLST disagrees with 16S/skani — MLST is more reliable for these cases
    old_species = sr.species
    sr.species = mlst_species
    sr.method = f"{sr.method}+mlst" if sr.method else "mlst"
    db.commit()
    job.log += f"  Species corrected: {old_species} → {mlst_species} (based on MLST scheme {mlst.scheme})\n"
    db.commit()


def _has_results(db, model_class, sample_id) -> bool:
    """Check if a sample already has results for a given model."""
    return db.query(model_class).filter(model_class.sample_id == sample_id).first() is not None


def _ensure_databases(job, db):
    """Download reference databases if missing (first run)."""
    import subprocess, os
    # backend/ is 3 dirs up from app/core/pipeline.py
    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "download_databases.sh",
    )
    if not os.path.exists(script):
        logger.warning(f"download_databases.sh not found at {script}")
        return
    # Resolve database dir (same as core modules: 4 dirs up from app/core/X.py → /databases)
    db_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "databases",
    )
    # Ensure AMRFinderPlus symlink exists (lost on container recreate)
    amrfinder_db = os.path.join(db_dir, "amrfinderplus")
    amrfinder_link = os.path.join(
        subprocess.run(["conda", "run", "-n", "radar", "bash", "-c", "echo $CONDA_PREFIX"],
                       capture_output=True, text=True, timeout=30).stdout.strip(),
        "bin", "data", "latest",
    ) if os.path.isdir(amrfinder_db) else None
    if amrfinder_link and not os.path.exists(amrfinder_link):
        os.makedirs(os.path.dirname(amrfinder_link), exist_ok=True)
        os.symlink(amrfinder_db, amrfinder_link)
        logger.info(f"Restored AMRFinderPlus symlink: {amrfinder_link} -> {amrfinder_db}")

    # Quick check: skip if key databases already exist
    if os.path.isdir(os.path.join(db_dir, "genomad_db")) and os.path.isfile(os.path.join(db_dir, "16S", "16S_ribosomal_RNA.ndb")):
        return
    job.log += "Downloading reference databases (first run)...\n"
    db.commit()
    logger.info(f"Downloading databases to {db_dir}")
    result = subprocess.run(
        ["bash", script, db_dir],
        capture_output=True, text=True, timeout=7200,
    )
    if result.returncode != 0:
        logger.warning(f"Database download had errors: {result.stderr[-500:]}")
        job.log += f"  Database download warnings: {result.stderr[-200:]}\n"
    else:
        job.log += "  Databases ready.\n"
    db.commit()


def _run_annotation_phase(sample_id: str, assembly_path: str, job, db, threads: int):
    """Phase 2: All annotation steps on the assembly. Skips steps with existing results."""
    from app.models.models import (
        SpeciesResult, MLSTResult, SerotypeResult, ARGResult,
        PlasmidResult, MobilityResult, IntegronResult, ProphageResult,
        CgMLSTResult, CRISPRResult, DefenseFinderResult, ICEResult,
        BacMetResult, RiskScore, MLPhenotypePrediction,
    )

    _ensure_databases(job, db)

    sample = db.query(Sample).filter(Sample.id == sample_id).first()
    sample.status = SampleStatus.annotating
    db.commit()

    job.log += "── Phase 2: Annotation ──\n"
    db.commit()

    # Species identification
    if not _has_results(db, SpeciesResult, sample_id):
        from app.core.species import run_species_id
        try:
            sr = run_species_id(sample_id, assembly_path, db, threads=threads)
            if sr:
                job.log += f"  Species: {sr.species} ({sr.identity}% identity)\n"
            else:
                job.log += "  No species ID hits found\n"
            db.commit()
        except Exception as e:
            job.log += f"  Species ID failed (non-critical): {e}\n"
            db.commit()
    else:
        sr = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
        job.log += f"  Species — skipped ({sr.species})\n"
        db.commit()

    # MLST
    if not _has_results(db, MLSTResult, sample_id):
        from app.core.context_annotations import run_mlst
        _run_noncritical(db, job, "MLST", lambda: run_mlst(sample_id, assembly_path, db))
    else:
        mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
        job.log += f"  MLST — skipped ({mlst.scheme} ST{mlst.sequence_type})\n"
        db.commit()

    # Reconcile species with MLST (MLST scheme is more reliable than 16S for Enterobacteriaceae)
    _reconcile_species_with_mlst(sample_id, job, db)

    # Serotyping
    if not _has_results(db, SerotypeResult, sample_id):
        from app.core.serotype import run_serotyping
        _run_noncritical(db, job, "Serotyping", lambda: run_serotyping(sample_id, assembly_path, db, threads=threads))
    else:
        job.log += "  Serotyping — skipped\n"
        db.commit()

    # ARG detection (AMRFinderPlus) — critical
    if not _has_results(db, ARGResult, sample_id):
        from app.core.arg_detect import run_amrfinderplus
        try:
            run_amrfinderplus(sample_id, assembly_path, db, threads=threads)
            job.log += "  AMRFinderPlus complete\n"
            db.commit()
        except Exception as e:
            job.log += f"  AMRFinderPlus FAILED: {e}\n"
            db.commit()
            raise
    else:
        n_args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).count()
        job.log += f"  AMRFinderPlus — skipped ({n_args} ARGs)\n"
        db.commit()

    # Plasmid analysis (MOB-recon)
    if not _has_results(db, PlasmidResult, sample_id):
        from app.core.plasmid import run_mob_recon
        _run_noncritical(db, job, "MOB-recon", lambda: run_mob_recon(sample_id, assembly_path, db, threads=threads))
    else:
        job.log += "  MOB-recon — skipped\n"
        db.commit()

    # IS element detection (MobileElementFinder)
    if not _has_results(db, MobilityResult, sample_id):
        from app.core.mobility import run_mefinder
        _run_noncritical(db, job, "MobileElementFinder", lambda: run_mefinder(sample_id, assembly_path, db))
    else:
        job.log += "  MobileElementFinder — skipped\n"
        db.commit()

    # Integron detection (IntegronFinder)
    if not _has_results(db, IntegronResult, sample_id):
        from app.core.context_annotations import run_integron_finder
        _run_noncritical(db, job, "IntegronFinder", lambda: run_integron_finder(sample_id, assembly_path, db=db, threads=threads))
    else:
        job.log += "  IntegronFinder — skipped\n"
        db.commit()

    # Prophage detection (geNomad)
    if not _has_results(db, ProphageResult, sample_id):
        from app.core.genomad import run_genomad
        _run_noncritical(db, job, "geNomad", lambda: run_genomad(sample_id, assembly_path, db, threads=threads))
    else:
        job.log += "  geNomad — skipped\n"
        db.commit()

    # Point mutation screening (PointFinder)
    from app.core.context_annotations import run_pointfinder
    _run_noncritical(db, job, "PointFinder", lambda: run_pointfinder(sample_id, assembly_path, threads=threads))

    # cgMLST (chewBBACA)
    if not _has_results(db, CgMLSTResult, sample_id):
        from app.core.cgmlst import run_cgmlst
        _run_noncritical(db, job, "cgMLST", lambda: run_cgmlst(sample_id, assembly_path, db, threads=threads))
    else:
        job.log += "  cgMLST — skipped\n"
        db.commit()

    # CRISPR detection
    if not _has_results(db, CRISPRResult, sample_id):
        from app.core.crispr import run_crisprcasfinder
        _run_noncritical(db, job, "CRISPRCasFinder", lambda: run_crisprcasfinder(sample_id, assembly_path, db, threads=threads))
    else:
        job.log += "  CRISPRCasFinder — skipped\n"
        db.commit()

    # Defense systems (DefenseFinder)
    if not _has_results(db, DefenseFinderResult, sample_id):
        from app.core.defensefinder import run_defensefinder
        _run_noncritical(db, job, "DefenseFinder", lambda: run_defensefinder(sample_id, assembly_path, db, threads=threads))
    else:
        job.log += "  DefenseFinder — skipped\n"
        db.commit()

    # ICE detection (ICEfinder)
    if not _has_results(db, ICEResult, sample_id):
        from app.core.icefinder import run_icefinder
        _run_noncritical(db, job, "ICEfinder", lambda: run_icefinder(sample_id, assembly_path, db, threads=threads))
    else:
        job.log += "  ICEfinder — skipped\n"
        db.commit()

    # Context annotations (Prodigal, sRNA, operon, dosage, CAI, GC deviation)
    # Check if CAI is populated on any ARG — if so, context annotations already ran
    args_with_cai = db.query(ARGResult).filter(
        ARGResult.sample_id == sample_id, ARGResult.cai.isnot(None)
    ).first()
    if not args_with_cai:
        from app.core.context_annotations import annotate_arg_context
        _run_noncritical(db, job, "Context annotations", lambda: annotate_arg_context(sample_id, assembly_path, db, threads=threads))
    else:
        job.log += "  Context annotations — skipped\n"
        db.commit()

    # BacMet2 (biocide/metal resistance — needs Prodigal proteins)
    if not _has_results(db, BacMetResult, sample_id):
        from app.core.bacmet import run_bacmet
        _run_noncritical(db, job, "BacMet2", lambda: run_bacmet(sample_id, assembly_path, db, threads=threads))
    else:
        job.log += "  BacMet2 — skipped\n"
        db.commit()

    # ML phenotype prediction
    if not _has_results(db, MLPhenotypePrediction, sample_id):
        from app.core.ml_phenotype import run_ml_phenotype
        _run_noncritical(db, job, "ML phenotype prediction", lambda: run_ml_phenotype(sample_id, db))
    else:
        job.log += "  ML phenotype prediction — skipped\n"
        db.commit()

    # Phenotype prediction (rule-based) — always re-run (fast, depends on ARGs)
    from app.core.phenotype import predict_phenotype
    _run_noncritical(db, job, "Phenotype prediction", lambda: predict_phenotype(sample_id, db))

    # Risk scoring — always re-run (fast, depends on ARGs/VFs/mobility)
    from app.core.risk import calculate_composite_risk
    _run_noncritical(db, job, "Risk scoring", lambda: calculate_composite_risk(sample_id, db=db))


def _run_noncritical(db, job, name, func):
    """Run a non-critical pipeline step, logging success or failure."""
    try:
        func()
        job.log += f"  {name} complete\n"
        db.commit()
    except Exception as e:
        job.log += f"  {name} failed (non-critical): {e}\n"
        db.commit()


@celery_app.task(name="run_single_step", bind=True)
def run_single_step(self, sample_id: str, job_id: str, tool: str, threads: int = 4):
    """Run a single pipeline step."""
    db = SessionLocal()
    try:
        sample = db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            logger.error(f"Sample {sample_id} not found")
            return

        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        job.log = f"Running {tool}...\n"
        db.commit()

        input_files = db.query(SampleFile).filter(SampleFile.sample_id == sample_id).all()
        file_paths = [f.file_path for f in input_files]

        if tool == "fastp":
            from app.core.qc import run_fastp
            run_fastp(sample_id, file_paths, db, threads=threads)
            job.log += "fastp QC complete\n"

        elif tool == "assembly":
            from app.core.assembly import run_assembly
            assembly_path = run_assembly(sample_id, file_paths, db, threads=threads)
            job.log += f"Assembly complete: {assembly_path}\n"

        elif tool == "quast":
            from app.core.assembly import run_quast
            assembly_path = _get_assembly_path(sample_id, db)
            if not assembly_path:
                raise ValueError("No assembly found. Run assembly first.")
            metrics = run_quast(sample_id, assembly_path, threads=threads)
            job.log += f"QUAST complete: {metrics}\n"

        elif tool == "busco":
            from app.core.assembly import run_busco
            assembly_path = _get_assembly_path(sample_id, db)
            if not assembly_path:
                raise ValueError("No assembly found. Run assembly first.")
            run_busco(sample_id, assembly_path, threads=threads)
            job.log += "BUSCO complete\n"

        elif tool == "amrfinderplus":
            from app.core.arg_detect import run_amrfinderplus
            assembly_path = _get_assembly_path(sample_id, db)
            if not assembly_path:
                raise ValueError("No assembly found. Run assembly first.")
            run_amrfinderplus(sample_id, assembly_path, db, threads=threads)
            job.log += "AMRFinderPlus complete\n"

        elif tool == "mob_recon":
            from app.core.plasmid import run_mob_recon
            assembly_path = _get_assembly_path(sample_id, db)
            if not assembly_path:
                raise ValueError("No assembly found. Run assembly first.")
            run_mob_recon(sample_id, assembly_path, db, threads=threads)
            job.log += "MOB-recon complete\n"

        elif tool == "mefinder":
            from app.core.mobility import run_mefinder
            assembly_path = _get_assembly_path(sample_id, db)
            if not assembly_path:
                raise ValueError("No assembly found. Run assembly first.")
            run_mefinder(sample_id, assembly_path, db)
            job.log += "MobileElementFinder complete\n"

        elif tool == "phenotype_prediction":
            from app.core.phenotype import predict_phenotype
            predict_phenotype(sample_id, db)
            job.log += "Phenotype prediction complete\n"

        elif tool == "risk_scoring":
            from app.core.risk import calculate_composite_risk
            calculate_composite_risk(sample_id, db=db)
            job.log += "Risk scoring complete\n"

        else:
            raise ValueError(f"Unknown tool: {tool}")

        job.status = JobStatus.complete
        job.finished_at = datetime.utcnow()
        db.commit()

        logger.info(f"Step {tool} completed for sample {sample_id}")

    except Exception as e:
        logger.error(f"Step {tool} failed for sample {sample_id}: {traceback.format_exc()}")
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
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
