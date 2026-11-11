"""MIC -> S/I/R interpretation against the editable Breakpoint table.

Breakpoints come from several guidelines, tagged on each row by `standard`:

- APQA monitoring panel: only a resistant cutoff (MIC >= resistant_min -> R), so a
  MIC below that is reported S.
- EUCAST / CLSI (seeded from the AMR R package): susceptible_max (= breakpoint_S)
  and resistant_min (= breakpoint_R), with the intermediate band being the gap
  between them. The resistant boundary follows the guideline convention — EUCAST is
  open (MIC > R -> R), CLSI/APQA closed (MIC >= R -> R).

EUCAST/CLSI key their breakpoints to a taxon that may be above species level (e.g.
"Enterobacterales"). select_breakpoint() therefore resolves a sample's species up its
lineage (genus -> family -> order) using a bundled taxonomy map, and prefers the most
specific matching row.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Breakpoint

_LINEAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "taxonomy_lineage.json"


@lru_cache(maxsize=1)
def _lineage() -> dict:
    """genus (lowercase) -> {"family": ..., "order": ...}. Empty if the file is absent."""
    try:
        raw = json.loads(_LINEAGE_PATH.read_text())
    except (OSError, ValueError):
        return {}
    return {k.lower(): v for k, v in raw.items()}


def _sample_taxa(organism: str) -> List[Tuple[int, str]]:
    """Higher-rank taxa for a sample species, each as (specificity, name_lower).
    specificity: 3 = genus, 2 = family, 1 = order. The species string itself is
    matched separately (specificity 4)."""
    genus = organism.strip().split()[0] if organism.strip() else ""
    if not genus:
        return []
    out: List[Tuple[int, str]] = [(3, genus.lower())]
    lin = _lineage().get(genus.lower(), {})
    if lin.get("family"):
        out.append((2, lin["family"].lower()))
    if lin.get("order"):
        out.append((1, lin["order"].lower()))
    return out


def parse_mic(mic) -> Optional[float]:
    """Extract the numeric MIC. Handles '<=0.25', '>256', '32/16' (first component),
    comma thousands, and bare numbers. Returns None if nothing numeric."""
    if mic is None:
        return None
    t = str(mic).strip()
    if not t:
        return None
    t = t.split("/")[0]  # combination drug: compare the first component
    m = re.search(r"([0-9][0-9,]*\.?[0-9]*)", t)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def select_breakpoint(db: Session, organism: str, antibiotic: str,
                      host: Optional[str] = None,
                      standard: Optional[str] = None) -> Optional[Breakpoint]:
    """Pick the best breakpoint for (organism, antibiotic[, host, standard]).

    Candidates match the antibiotic (by name, then abbreviation) and, if given, the
    standard. Each candidate is scored by how specifically its organism matches the
    sample: an exact/prefix species match beats genus, which beats family, which beats
    order. Among equally specific rows, an exact host match (human by default) wins,
    then the most conservative cutoff."""
    if not organism or not antibiotic:
        return None
    org = organism.strip().lower()
    abx = antibiotic.strip().lower()
    std = standard.strip().lower() if standard else None

    def fetch(col):
        q = db.query(Breakpoint).filter(func.lower(col) == abx)
        if std:
            q = q.filter(func.lower(Breakpoint.standard) == std)
        return q.all()

    cands = fetch(Breakpoint.antibiotic) or fetch(Breakpoint.abbreviation)
    if not cands:
        return None

    # never interpret with the other companion animal's cutoff
    h = (host or "").lower()
    if h in ("dog", "dogs", "cat", "cats"):
        other = {"dog": "cats", "dogs": "cats", "cat": "dogs", "cats": "dogs"}[h]
        cands = [b for b in cands if (b.host or "").lower() != other] or cands

    taxa = {name: spec for spec, name in _sample_taxa(organism)}

    def specificity(b: Breakpoint) -> int:
        bo = (b.organism or "").strip().lower()
        if not bo:
            return 0
        if org == bo or org.startswith(bo) or bo.startswith(org):
            return 4  # species-level (or an exact higher-taxon query)
        return taxa.get(bo, 0)

    scored = [(specificity(b), b) for b in cands]
    scored = [(s, b) for s, b in scored if s > 0]
    if not scored:
        return None
    best = max(s for s, _ in scored)
    top = [b for s, b in scored if s == best]

    want_host = h or "human"  # an unspecified host is treated as human

    def rank(b: Breakpoint):
        host_match = 0 if (b.host or "").lower() == want_host else 1
        has_cutoff = 0 if b.resistant_min is not None else 1
        rmin = b.resistant_min if b.resistant_min is not None else float("inf")
        return (host_match, has_cutoff, rmin)

    return sorted(top, key=rank)[0]


def interpret(bp: Optional[Breakpoint], mic) -> Optional[str]:
    """Return 'S'/'I'/'R' (or None if undeterminable) for a MIC against a breakpoint.

    MIC <= susceptible_max -> S. Resistant boundary depends on the guideline: EUCAST
    uses the open interval (MIC > resistant_min -> R), CLSI/APQA the closed interval
    (MIC >= resistant_min -> R). A value that is neither S nor R is Intermediate for a
    full S/I/R guideline (EUCAST/CLSI). APQA rows carry only a resistant cutoff, so a
    value below it is reported Susceptible."""
    val = parse_mic(mic)
    if bp is None or val is None:
        return None
    s_max = bp.susceptible_max
    r_min = bp.resistant_min
    i_min = bp.intermediate_min
    std = (bp.standard or "").upper()
    eucast = std.startswith("EUCAST")
    full_sir = eucast or std.startswith("CLSI")  # three-way guideline with an I band

    if s_max is not None and val <= s_max:
        return "S"
    if r_min is not None and ((val > r_min) if eucast else (val >= r_min)):
        return "R"
    if i_min is not None and val >= i_min:
        return "I"
    if full_sir and r_min is not None:
        return "I"  # EUCAST/CLSI: not S and not R -> intermediate (incl. "no S category")
    if s_max is not None and r_min is not None:
        return "I"  # a manually-filled three-way APQA row, between the cutoffs
    if r_min is not None and s_max is None:
        return "S"  # single-cutoff (APQA) row, below the resistant cutoff
    return None


def interpret_mic(db: Session, organism: str, antibiotic: str, mic,
                  host: Optional[str] = None, standard: Optional[str] = None):
    """Convenience: select + interpret. Returns (sir|None, Breakpoint|None)."""
    bp = select_breakpoint(db, organism, antibiotic, host, standard)
    return interpret(bp, mic), bp
