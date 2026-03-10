import logging
import traceback
from datetime import datetime

from app.celery_app import celery_app
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

    For FASTQ input: QC (BBDuk) -> Assembly (Unicycler) -> QUAST/BUSCO -> Annotation
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
            # ── Step 1: QC with BBDuk ──
            sample.status = SampleStatus.qc
            db.commit()
            _append_master_log(db, master_job_id, "Step 1: Running BBDuk QC...")

            from app.core.qc import run_bbduk
            qc_job = _create_job(db, sample_id, "bbduk", threads)
            try:
                qc_result = run_bbduk(sample_id, file_paths, db, threads=threads)
                _complete_job(db, qc_job, f"BBDuk QC complete")
                _append_master_log(db, master_job_id, "  BBDuk QC complete")
            except Exception as e:
                _fail_job(db, qc_job, str(e))
                _append_master_log(db, master_job_id, f"  BBDuk QC FAILED: {e}")
                raise

            # ── Step 2: Assembly with Unicycler ──
            sample.status = SampleStatus.assembling
            db.commit()
            _append_master_log(db, master_job_id, "Step 2: Running Unicycler assembly...")

            from app.core.assembly import run_unicycler
            asm_job = _create_job(db, sample_id, "unicycler", threads)
            try:
                assembly_path = run_unicycler(sample_id, file_paths, db, threads=threads)
                _complete_job(db, asm_job, f"Assembly complete: {assembly_path}")
                _append_master_log(db, master_job_id, f"  Unicycler assembly complete")
            except Exception as e:
                _fail_job(db, asm_job, str(e))
                _append_master_log(db, master_job_id, f"  Unicycler assembly FAILED: {e}")
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

        if tool == "bbduk":
            from app.core.qc import run_bbduk
            run_bbduk(sample_id, file_paths, db, threads=threads)
            job.log += "BBDuk QC complete\n"

        elif tool == "unicycler":
            from app.core.assembly import run_unicycler
            assembly_path = run_unicycler(sample_id, file_paths, db, threads=threads)
            job.log += f"Assembly complete: {assembly_path}\n"

        elif tool == "quast":
            from app.core.assembly import run_quast
            assembly_path = _get_assembly_path(sample_id, db)
            if not assembly_path:
                raise ValueError("No assembly found. Run Unicycler first.")
            metrics = run_quast(sample_id, assembly_path, threads=threads)
            job.log += f"QUAST complete: {metrics}\n"

        elif tool == "busco":
            from app.core.assembly import run_busco
            assembly_path = _get_assembly_path(sample_id, db)
            if not assembly_path:
                raise ValueError("No assembly found. Run Unicycler first.")
            run_busco(sample_id, assembly_path, threads=threads)
            job.log += "BUSCO complete\n"

        elif tool == "amrfinderplus":
            from app.core.arg_detect import run_amrfinderplus
            assembly_path = _get_assembly_path(sample_id, db)
            if not assembly_path:
                raise ValueError("No assembly found. Run Unicycler first.")
            run_amrfinderplus(sample_id, assembly_path, db, threads=threads)
            job.log += "AMRFinderPlus complete\n"

        elif tool == "mob_recon":
            from app.core.plasmid import run_mob_recon
            assembly_path = _get_assembly_path(sample_id, db)
            if not assembly_path:
                raise ValueError("No assembly found. Run Unicycler first.")
            run_mob_recon(sample_id, assembly_path, db, threads=threads)
            job.log += "MOB-recon complete\n"

        elif tool == "mefinder":
            from app.core.mobility import run_mefinder
            assembly_path = _get_assembly_path(sample_id, db)
            if not assembly_path:
                raise ValueError("No assembly found. Run Unicycler first.")
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
