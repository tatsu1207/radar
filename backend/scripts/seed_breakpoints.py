#!/usr/bin/env python
"""Parse the APQA AST panel workbook into Breakpoint rows.

Dry-run (default): print parsed rows + a summary, insert nothing.
    python scripts/seed_breakpoints.py "/home/wgs/검역본부 항생제감수성검사 패널 .xlsx"
Commit to DB:
    python scripts/seed_breakpoints.py "<xlsx>" --commit [--replace]

The panel gives a single resistant cutoff (MIC >= X -> R); we seed resistant_min only.
Host-specific ("dog >=0.5 cat >=4") and species-specific ("C. jejuni >=8 C. coli >=16")
cells are split into multiple rows. ND / "-" cells are kept as notes with no cutoff.
"""
import re
import sys
import argparse

import openpyxl

SOURCE = "APQA panel"

# fix obvious typos in the source workbook so names match sample species
NAME_FIX = {
    "Bronchiseptica bronchiseptica": "Bordetella bronchiseptica",
    "Clstridioides difficile": "Clostridioides difficile",
    "Staphylococcus pseudintermeidus": "Staphylococcus pseudintermedius",
}
HOST_KW = ("개", "고양이", "소", "돼지", "닭", "오리")


def norm(s):
    if s is None:
        return ""
    return str(s).replace("\n", " ").replace("∼", "-").strip()


def parse_mic(text):
    """Return (resistant_min: float|None, note: str). Takes the first numeric token
    after a >= / > sign, stripping commas and any /combo second component."""
    t = norm(text)
    if not t:
        return None, ""
    low = t.lower()
    if "not determined" in low or low in ("nd", "-", "–", "—"):
        return None, t
    m = re.search(r"[≥>]\s*=?\s*([0-9][0-9,]*\.?[0-9]*)", t)
    if not m:
        # bare number, no operator
        m = re.search(r"([0-9][0-9,]*\.?[0-9]*)", t)
        if not m:
            return None, t
    val = float(m.group(1).replace(",", ""))
    return val, t


def parse_abbrev(name):
    """Pull '(ABC)' abbreviation out of an agent name."""
    m = re.search(r"\(([^)]+)\)", name)
    abbr = m.group(1).strip() if m else None
    clean = re.sub(r"\s*\([^)]*\)\s*", "", name).strip(" /")
    return clean, abbr


HOST_SPLIT = re.compile(r"(dog|cat|개|고양이)\s*[≥>]=?\s*([0-9.,]+)", re.I)
SPP_SPLIT = re.compile(r"(C\.?\s*jejuni|C\.?\s*coli)\s*[≥>]=?\s*([0-9.,]+)", re.I)


def _spp_norm(s):
    return re.sub(r"\s+", " ", s).replace("C.", "C. ").replace("  ", " ").strip()


def expand_cell(raw):
    """A breakpoint cell may encode host/species-specific cutoffs. Return a list of
    (qualifier|None, text). qualifier is a host ('dog'/'cat') or species ('C. jejuni')
    when the cell names one; None when it applies to the whole block."""
    t = norm(raw)
    hosts = HOST_SPLIT.findall(t)
    if len(hosts) >= 1 and re.match(r"^\s*(dog|cat|개|고양이)", t, re.I):
        return [(h.lower(), f">={v}") for h, v in hosts]
    spp = SPP_SPLIT.findall(t)
    if len(spp) >= 1 and re.match(r"^\s*C\.?\s*(jejuni|coli)", t, re.I):
        return [(_spp_norm(s), f">={v}") for s, v in spp]
    return [(None, t)]


def label_host_site(label, sheet_host):
    """A breakpoint-column label may encode a host and/or sample site,
    e.g. '고양이 설사' -> (cat, 설사), '개 뇨' -> (dog, 뇨), '피부/귀' -> (sheet_host, 피부/귀).
    Returns (host, site_note|None)."""
    t = norm(label)
    if not t or t.lower().startswith("breakpoint") or re.match(r"^\(?[㎍μug]", t.lower()):
        return sheet_host, None
    host = sheet_host
    if "개" in t or re.search(r"\bdog\b", t, re.I):
        host = "dog"
    elif "고양이" in t or re.search(r"\bcat\b", t, re.I):
        host = "cat"
    site = re.sub(r"(개|고양이|dog|cat)", "", t, flags=re.I).strip() or None
    return host, site


def host_of_sheet(title):
    if "가축" in title:
        return "livestock"
    if "반려" in title:
        return "companion"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--replace", action="store_true", help="delete existing APQA rows first")
    args = ap.parse_args()

    wb = openpyxl.load_workbook(args.xlsx, data_only=True)
    rows = []

    for ws in wb.worksheets:
        if "균주목록" in ws.title or "삭제" in ws.title:
            continue  # master list / deleted panel, skip
        host = host_of_sheet(ws.title)
        grid = [[norm(c) for c in r] for r in ws.iter_rows(values_only=True)]

        organisms = []   # organisms the current panel block applies to
        in_table = False
        cur_subclass = ""
        col_labels = []  # breakpoint-column labels for the current table
        last_clean = last_abbr = None  # previous antibiotic, for continuation rows
        pend_name = pend_bp = None   # carry a combo agent fragment to the next row

        for idx, r in enumerate(grid):
            cells = [c for c in r]
            joined = " ".join(cells)
            # new block: the "균주 | 축종 | 시료 | 분류" header resets organisms + closes any table
            if cells and cells[0].startswith("균주"):
                in_table = False
                organisms = []
                cur_subclass = ""
                continue
            # organism rows: "<Name> [(nnn)] | <host> | 시료 | 분류"
            # accept with a code, or without a code when col2 names a host
            if not in_table and cells and cells[0] and re.match(r"^[A-Z][A-Za-z.]", cells[0]):
                col1 = cells[1] if len(cells) > 1 else ""
                mo = re.match(r"^([A-Z][A-Za-z.\- ]+?)\s*\(\d+\)", cells[0])
                if mo:
                    name = mo.group(1).strip()
                elif any(k in col1 for k in HOST_KW):
                    name = cells[0].strip()
                else:
                    name = None
                if name:
                    organisms.append(NAME_FIX.get(name, name))
                    continue
            # table header (may span two rows: "Antimicrobial..." then "Breakpoints..." separately).
            # the column-label row is whichever of the next ~2 rows has the most cells past col 1.
            if "Antimicrobial" in joined and ("Agent" in joined or "subclass" in joined):
                in_table = True
                cur_subclass = ""
                best = []
                for look in grid[idx:idx + 3]:
                    labs = [c for c in look[2:] if norm(c)]
                    if len(labs) > len(best):
                        best = labs
                col_labels = best
                continue
            if not in_table:
                continue
            if not any(cells):
                continue
            # skip sub-header / unit rows
            if joined.strip().startswith("Breakpoint") or re.match(r"^\(?[㎍μ]", joined.strip()):
                continue
            # column layout: [subclass, agent(abbr), bp, bp2, ...]
            subclass, agent = cells[0], (cells[1] if len(cells) > 1 else "")
            bp_cols = [c for c in cells[2:] if c != ""]
            if subclass:
                cur_subclass = subclass
            if not agent and not bp_cols:
                continue
            # merge split combo agent (e.g. "Amoxicillin/" [≥32/16] + "clavulanic acid(AMC)" [])
            if pend_name is not None:
                agent = pend_name + agent
                if not bp_cols:
                    bp_cols = pend_bp
                pend_name = pend_bp = None
            if agent and "(" not in agent and agent.endswith("/"):
                pend_name, pend_bp = agent, bp_cols
                continue
            clean, abbr = parse_abbrev(agent) if agent else ("", None)
            # continuation row: no agent but a species/host-qualified breakpoint for the
            # previous antibiotic (e.g. "| C. coli >=16", "| cat >=4")
            if (not clean or not re.search(r"[A-Za-z]", clean)) and bp_cols and last_clean \
                    and expand_cell(bp_cols[0])[0][0] is not None:
                clean, abbr = last_clean, last_abbr
            if not clean or not re.search(r"[A-Za-z]", clean):
                continue
            last_clean, last_abbr = clean, abbr
            # organism x breakpoint-column mapping
            targets = organisms if organisms else [ws.title]
            if not bp_cols:
                rows.append(dict(organism=targets[0], host=host, antibiotic=clean, abbreviation=abbr,
                                 subclass=cur_subclass, resistant_min=None, note="(no breakpoint column)"))
                continue
            # Case A: multiple columns, one per organism (C. jejuni/coli, pathogenic 4-spp)
            if len(bp_cols) == len(targets) and len(targets) > 1:
                for org, cell in zip(targets, bp_cols):
                    rmin, note = parse_mic(cell)
                    rows.append(dict(organism=org, host=host, antibiotic=clean, abbreviation=abbr,
                                     subclass=cur_subclass, resistant_min=rmin, note=note))
            # Case B: multiple columns for a single organism = host/site variants (Proteus, companion pathogenic)
            elif len(bp_cols) > 1 and len(targets) == 1:
                for ci, cell in enumerate(bp_cols):
                    lab = col_labels[ci] if ci < len(col_labels) else ""
                    chost, site = label_host_site(lab, host)
                    rmin, note = parse_mic(cell)
                    note = (f"{site}: {note}" if site else note)
                    rows.append(dict(organism=targets[0], host=chost, antibiotic=clean, abbreviation=abbr,
                                     subclass=cur_subclass, resistant_min=rmin, note=note))
            # Case C: single column (may still name a host or species within the cell)
            else:
                for qual, piece in expand_cell(bp_cols[0]):
                    rmin, note = parse_mic(piece)
                    if qual in ("dog", "cat", "개", "고양이"):   # host-specific -> all targets, that host
                        h = {"개": "dog", "고양이": "cat"}.get(qual, qual)
                        for org in targets:
                            rows.append(dict(organism=org, host=h, antibiotic=clean, abbreviation=abbr,
                                             subclass=cur_subclass, resistant_min=rmin, note=note))
                    elif qual and qual.lower().startswith("c."):   # species-specific -> matching target only
                        key = qual.split()[-1].lower()  # 'jejuni' / 'coli'
                        match = [o for o in targets if key in o.lower()]
                        o = match[0] if match else qual
                        rows.append(dict(organism=o, host=host, antibiotic=clean, abbreviation=abbr,
                                         subclass=cur_subclass, resistant_min=rmin, note=note))
                    else:                                          # applies to the whole block
                        for org in targets:
                            rows.append(dict(organism=org, host=host, antibiotic=clean, abbreviation=abbr,
                                             subclass=cur_subclass, resistant_min=rmin, note=note))

    # ---- report ----
    orgs = {}
    for r in rows:
        orgs.setdefault(r["organism"], 0)
        orgs[r["organism"]] += 1
    print(f"Parsed {len(rows)} breakpoint rows across {len(orgs)} organisms:\n")
    for o, n in sorted(orgs.items()):
        print(f"  {n:3d}  {o}")
    import os as _os
    filt = _os.environ.get("FILTER", "").lower()
    shown = [r for r in rows if filt in (r["organism"] + " " + r["antibiotic"] + " " + (r["host"] or "")).lower()] if filt else rows[:40]
    print(f"\nSample rows ({'filter='+filt if filt else 'first 40'}):")
    for r in shown[:60]:
        print(f"  [{r['host'] or '-':9}] {r['organism'][:28]:28} {(r['abbreviation'] or ''):6} "
              f"{r['antibiotic'][:28]:28} R>={r['resistant_min']}   {r['note'][:20]}")

    if not args.commit:
        print("\n(dry-run; pass --commit to insert)")
        return

    sys.path.insert(0, ".")
    from app.db import SessionLocal, engine, Base
    from app.models.models import Breakpoint
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.replace:
            n = db.query(Breakpoint).filter(Breakpoint.source == SOURCE).delete()
            print(f"deleted {n} existing {SOURCE} rows")
        for r in rows:
            db.add(Breakpoint(organism=r["organism"], host=r["host"], antibiotic=r["antibiotic"],
                              abbreviation=r["abbreviation"], subclass=r["subclass"],
                              resistant_min=r["resistant_min"], source=SOURCE,
                              notes=(r["note"] or None), unit="µg/mL"))
        db.commit()
        print(f"inserted {len(rows)} rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
