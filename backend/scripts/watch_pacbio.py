#!/usr/bin/env python
"""Watch the 'PacBio isolates' batch; exit when all samples are terminal or stalled.

Polls every 180s. Exits 0 with a final report when every sample is complete/failed.
Exits with a STALL report if no sample has reached a terminal state for ~60 min
AND nothing is running (worker died / queue drained) — so the parent can step in
rather than wait forever (the batch already stalled once overnight).
"""
import time
from datetime import datetime

from app.db import SessionLocal
from app.models.models import (
    Project, Sample, SampleStatus, AnalysisJob, JobStatus, RiskScore, SpeciesResult,
)

PROJECT = "PacBio isolates"
INTERVAL = 180
STALL_CHECKS = 20  # 20 * 180s = 60 min with no terminal progress & nothing running

TERMINAL = {SampleStatus.complete, SampleStatus.failed}


def snapshot(db, sids):
    counts = {}
    for s in db.query(Sample).filter(Sample.id.in_(sids)):
        counts[s.status] = counts.get(s.status, 0) + 1
    term = sum(counts.get(t, 0) for t in TERMINAL)
    running = db.query(AnalysisJob).filter(
        AnalysisJob.sample_id.in_(sids), AnalysisJob.tool == "pipeline",
        AnalysisJob.status == JobStatus.running).count()
    return counts, term, running


def final_report(db, sids, header):
    print("\n" + "=" * 60)
    print(header)
    print("=" * 60)
    samples = db.query(Sample).filter(Sample.id.in_(sids)).order_by(Sample.name).all()
    comp = [s for s in samples if s.status == SampleStatus.complete]
    fail = [s for s in samples if s.status == SampleStatus.failed]
    other = [s for s in samples if s.status not in TERMINAL]
    print(f"complete={len(comp)} failed={len(fail)} unfinished={len(other)} / {len(samples)}")
    print("\n--- COMPLETE (species / hazard rank) ---")
    for s in comp:
        rs = db.query(RiskScore).filter(RiskScore.sample_id == s.id).first()
        sp = db.query(SpeciesResult).filter(SpeciesResult.sample_id == s.id).first()
        rank = getattr(rs, "hazard_rank", None) if rs else None
        spn = getattr(sp, "species", None) if sp else None
        print(f"  {s.name:<14} {spn or '?':<28} {rank or '-'}")
    if fail:
        print("\n--- FAILED ---")
        for s in fail:
            j = db.query(AnalysisJob).filter(
                AnalysisJob.sample_id == s.id, AnalysisJob.tool == "pipeline"
            ).order_by(AnalysisJob.started_at.desc().nullslast()).first()
            tail = (j.log or "").strip().splitlines() if j else []
            msg = next((l for l in reversed(tail) if "FAIL" in l or "ERROR" in l), tail[-1] if tail else "")
            print(f"  {s.name:<14} {msg[:80]}")
    if other:
        print("\n--- UNFINISHED ---")
        for s in other:
            print(f"  {s.name:<14} {str(s.status).split('.')[-1]}")


def main():
    db = SessionLocal()
    p = db.query(Project).filter(Project.name == PROJECT).order_by(
        Project.created_at.desc()).first()
    sids = [s.id for s in db.query(Sample).filter(Sample.project_id == p.id)]
    total = len(sids)
    db.close()

    last_term = -1
    stale = 0
    while True:
        db = SessionLocal()
        counts, term, running = snapshot(db, sids)
        ts = datetime.utcnow().strftime("%H:%M")
        cs = " ".join(f"{str(k).split('.')[-1]}={v}" for k, v in counts.items())
        print(f"[{ts}Z] {cs} | running={running} | terminal={term}/{total}", flush=True)

        if term >= total:
            final_report(db, sids, "PacBio batch FINISHED")
            db.close()
            return 0

        if term == last_term and running == 0:
            stale += 1
        else:
            stale = 0
        last_term = term

        if stale >= STALL_CHECKS:
            final_report(db, sids, f"PacBio batch STALLED (no progress ~{STALL_CHECKS*INTERVAL//60} min, nothing running)")
            db.close()
            return 2

        db.close()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    import sys
    sys.exit(main())
