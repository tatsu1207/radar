"""Reset a sample so the pipeline runs again from scratch ("force re-run").

The pipeline skips every step whose output already exists (QC files, assembly,
result rows), so re-running a finished sample normally does nothing. A force
re-run first removes the sample's results directory and all result rows; the
inputs and user-entered data are kept:

  kept:    sample_files (reads; BAM->FASTQ conversions live in the uploads dir),
           metadata, ast_results, sra_downloads, bvbrc_fetches, analysis_jobs (history)
  removed: data/results/<sample_id>/ and every other table keyed to the sample,
           including promoter/RBS rows that hang off its ARG results
"""
import logging
import os
import shutil

from sqlalchemy import select

from app.config import settings
from app.db import Base
from app.models.models import SampleStatus

logger = logging.getLogger(__name__)

KEEP_TABLES = {"samples", "sample_files", "metadata", "ast_results",
               "sra_downloads", "bvbrc_fetches", "analysis_jobs"}


def reset_sample_results(db, sample) -> dict:
    """Delete the sample's result rows and results directory, set status to pending.
    Commits. Returns {table: rows deleted} (non-zero only)."""
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    arg_ids = select(tables["arg_results"].c.id).where(tables["arg_results"].c.sample_id == sample.id)
    deleted = {}
    # children first (reverse dependency order), so FK constraints never block a delete
    for t in reversed(Base.metadata.sorted_tables):
        if t.name in KEEP_TABLES:
            continue
        if "sample_id" in t.c:
            stmt = t.delete().where(t.c.sample_id == sample.id)
        elif "arg_result_id" in t.c:
            stmt = t.delete().where(t.c.arg_result_id.in_(arg_ids))
        else:
            continue
        n = db.execute(stmt).rowcount
        if n:
            deleted[t.name] = n
    sample.status = SampleStatus.pending
    db.commit()

    res = os.path.join(settings.RESULTS_DIR, str(sample.id))
    if os.path.isdir(res):
        shutil.rmtree(res, ignore_errors=True)
    logger.info(f"Force re-run: reset sample {sample.id} ({sample.name}): {deleted}")
    return deleted
