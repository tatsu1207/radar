#!/usr/bin/env python
"""Seed EUCAST and CLSI clinical breakpoints into the Breakpoint table from the AMR
R package's open datasets (GNU GPL 2.0), covering both human and veterinary hosts.

The AMR `clinical_breakpoints` table combines EUCAST and CLSI (2011-present) in a
single machine-readable file; `microorganisms` and `antimicrobials` decode its coded
`mo` / `ab` columns. We keep only MIC rows from the latest year of each guideline,
drop ECOFF (epidemiological, not clinical S/I/R), and collapse the per-site / per-UTI
variants to one representative row per (standard, taxon, host, antibiotic).

  breakpoint_S -> susceptible_max   (MIC <= S -> Susceptible)
  breakpoint_R -> resistant_min     (EUCAST: MIC > R -> R; CLSI: MIC >= R -> R)

It also writes app/data/taxonomy_lineage.json (bacterial genus -> family/order) so the
interpreter can resolve a sample species up to the taxon a breakpoint is keyed on.

Dry-run (default): parse + summarise, insert nothing.
    python scripts/seed_amr_breakpoints.py
Commit:
    python scripts/seed_amr_breakpoints.py --commit [--replace]
Use already-downloaded files instead of fetching:
    python scripts/seed_amr_breakpoints.py --from-dir /tmp
"""
import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path

RAW = "https://github.com/msberends/AMR/raw/main/data-raw/datasets"
FILES = {
    "cb": "clinical_breakpoints.txt",
    "mo": "microorganisms.txt",
    "ab": "antimicrobials.txt",
}
VET_HOSTS = {"dogs", "cats", "cattle", "swine", "horse", "poultry", "aquatic"}
# most general -> most specific; we keep the most general site available per combo
SITE_RANK = {"": 0, "non-meningitis": 1, "intravenous": 2, "oral": 3, "meningitis": 4}

APP_DATA = Path(__file__).resolve().parent.parent / "app" / "data"


def _load(name: str, from_dir):
    if from_dir:
        path = Path(from_dir) / FILES[name]
        data = path.read_text()
    else:
        url = f"{RAW}/{FILES[name]}"
        print(f"  downloading {FILES[name]} …", flush=True)
        with urllib.request.urlopen(url) as resp:
            data = resp.read().decode("utf-8")
    return list(csv.DictReader(data.splitlines(), delimiter="\t"))


def build_lineage(mo_rows):
    """Bacterial genus (as stored) -> {'family':..., 'order':...}."""
    lineage = {}
    for m in mo_rows:
        if m.get("domain") != "Bacteria":
            continue
        g = m.get("genus")
        if g and g not in lineage:
            lineage[g] = {"family": m.get("family") or None, "order": m.get("order") or None}
    return lineage


def site_of(row):
    return (row.get("site") or "").strip().lower()


def num(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--replace", action="store_true",
                    help="delete existing EUCAST/CLSI rows first")
    ap.add_argument("--from-dir", help="read the three .txt files from here instead of downloading")
    args = ap.parse_args()

    print("Loading AMR datasets:")
    cb = _load("cb", args.from_dir)
    mo_rows = _load("mo", args.from_dir)
    ab_rows = _load("ab", args.from_dir)
    mo = {m["mo"]: m for m in mo_rows}
    ab = {a["ab"]: a for a in ab_rows}

    # latest available year per guideline family
    latest = {}
    for r in cb:
        fam, yr = r["guideline"].split()
        latest[fam] = max(latest.get(fam, 0), int(yr))
    print(f"  latest guideline years: {latest}")

    def keep(r):
        fam, yr = r["guideline"].split()
        if int(yr) != latest[fam]:
            return False
        if r["method"] != "MIC":
            return False
        if r["type"] == "ECOFF" or r["host"] == "ECOFF":
            return False
        if r["host"] not in ({"human"} | VET_HOSTS):
            return False
        return num(r["breakpoint_S"]) is not None or num(r["breakpoint_R"]) is not None

    # one representative row per (standard, mo, ab, host): prefer non-UTI + most general site
    best = {}
    for r in cb:
        if not keep(r):
            continue
        key = (r["guideline"].split()[0], r["mo"], r["ab"], r["host"])
        rankv = (1 if r["uti"] == "TRUE" else 0, SITE_RANK.get(site_of(r), 9))
        if key not in best or rankv < best[key][0]:
            best[key] = (rankv, r)

    rows = []
    skipped_codes = set()
    for (standard, mo_code, ab_code, host), (_, r) in best.items():
        m = mo.get(mo_code)
        a = ab.get(ab_code)
        if not m or not a:
            skipped_codes.add(mo_code if not m else ab_code)
            continue
        organism = m["fullname"]
        antibiotic = a["name"]
        abbr = ab_code  # the AMR code doubles as a compact abbreviation (MEM, CIP, …)
        subclass = a.get("group") or None
        note_bits = []
        if site_of(r):
            note_bits.append(r["site"].strip())
        if r["uti"] == "TRUE":
            note_bits.append("UTI")
        # EUCAST encodes "no Susceptible category" (I/R only) as breakpoint_S <= 0.001;
        # drop that sentinel so it isn't read as a real susceptible cutoff.
        s_max = num(r["breakpoint_S"])
        if s_max is not None and s_max <= 0.001:
            s_max = None
            note_bits.append("no S category")
        if (r.get("note") or "").strip():
            note_bits.append(r["note"].strip().replace("\n", " ")[:300])
        rows.append(dict(
            organism=organism, standard=standard, host=host,
            antibiotic=antibiotic, abbreviation=abbr, subclass=subclass,
            susceptible_max=s_max,
            resistant_min=num(r["breakpoint_R"]),
            source=f"AMR {r['guideline']} (MIC)",
            notes="; ".join(note_bits) or None,
        ))

    # ---- report ----
    from collections import Counter
    by_std = Counter(r["standard"] for r in rows)
    by_host = Counter(r["host"] for r in rows)
    taxa = {r["organism"] for r in rows}
    print(f"\nParsed {len(rows)} breakpoint rows: {dict(by_std)}")
    print(f"  hosts: {dict(by_host)}")
    print(f"  distinct taxa: {len(taxa)}")
    if skipped_codes:
        print(f"  skipped {len(skipped_codes)} rows with unresolvable mo/ab codes")
    print("\n  sample rows:")
    for r in rows[:12]:
        print(f"    [{r['standard']:6} {r['host']:7}] {r['organism'][:26]:26} "
              f"{(r['abbreviation'] or ''):5} {r['antibiotic'][:22]:22} "
              f"S<={r['susceptible_max']} R={r['resistant_min']}")

    lineage = build_lineage(mo_rows)
    print(f"\nTaxonomy lineage map: {len(lineage)} bacterial genera")

    if not args.commit:
        print("\n(dry-run; pass --commit to write the lineage file and insert rows)")
        return

    APP_DATA.mkdir(parents=True, exist_ok=True)
    out = APP_DATA / "taxonomy_lineage.json"
    out.write_text(json.dumps(lineage, sort_keys=True))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")

    sys.path.insert(0, ".")
    from app.db import SessionLocal, engine, Base
    from app.models.models import Breakpoint
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.replace:
            n = db.query(Breakpoint).filter(Breakpoint.standard.in_(["EUCAST", "CLSI"])).delete(
                synchronize_session=False)
            print(f"deleted {n} existing EUCAST/CLSI rows")
        for r in rows:
            db.add(Breakpoint(unit="µg/mL", intermediate_min=None, **r))
        db.commit()
        print(f"inserted {len(rows)} rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
