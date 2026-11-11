#!/usr/bin/env python
"""Fill ARGResult.element_type (AMR / STRESS) for samples analysed before the
column was stored, from each sample's results/<id>/amr/amrfinderplus.tsv.

Rows are matched on (gene, contig, start, end), as the pipeline parser stores
them. Rows with no match (TSV missing, or re-run since) stay NULL; the results
API treats NULL as AMR, so nothing disappears.

Dry-run (default): report what would change.
    cd backend && python scripts/backfill_element_type.py
Write to the DB:
    cd backend && python scripts/backfill_element_type.py --commit

Run from start.sh's environment, or set RADAR_DATABASE_URL / RADAR_RESULTS_DIR.
"""
import argparse
import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def load_types(tsv_path):
    """(gene, contig, start, end) -> element type, using arg_detect's column choices."""
    types = {}
    with open(tsv_path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            etype = row.get("Element type", row.get("Type", ""))
            if etype not in ("AMR", "STRESS"):
                continue
            gene = row.get("Gene symbol", row.get("Element symbol", row.get("Sequence name", "unknown")))
            key = (gene, row.get("Contig id", ""), _int(row.get("Start")), _int(row.get("Stop")))
            types.setdefault(key, etype)
    return types


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    from app.config import settings
    from app.db import SessionLocal
    from app.models.models import ARGResult, Sample

    db = SessionLocal()
    try:
        sample_ids = [sid for (sid,) in db.query(ARGResult.sample_id)
                      .filter(ARGResult.element_type.is_(None)).distinct()]
        totals = Counter()
        for sid in sample_ids:
            sample = db.query(Sample).filter(Sample.id == sid).first()
            name = sample.name if sample else str(sid)
            rows = db.query(ARGResult).filter(ARGResult.sample_id == sid,
                                              ARGResult.element_type.is_(None)).all()
            tsv = os.path.join(settings.RESULTS_DIR, str(sid), "amr", "amrfinderplus.tsv")
            if not os.path.exists(tsv):
                print(f"{name}: {len(rows)} rows, no amrfinderplus.tsv - left NULL")
                totals["no_tsv"] += len(rows)
                continue
            types = load_types(tsv)
            counts = Counter()
            for r in rows:
                etype = types.get((r.gene, r.contig or "", r.start, r.end))
                counts[etype or "unmatched"] += 1
                if etype:
                    r.element_type = etype
            totals.update(counts)
            print(f"{name}: AMR {counts['AMR']}, STRESS {counts['STRESS']}, unmatched {counts['unmatched']}")
        print(f"\nTotal: AMR {totals['AMR']}, STRESS {totals['STRESS']}, "
              f"unmatched {totals['unmatched']}, no TSV {totals['no_tsv']}")
        if args.commit:
            db.commit()
            print("Committed.")
        else:
            db.rollback()
            print("Dry run - nothing written (use --commit).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
