"""MIC -> S/I/R interpretation against the editable Breakpoint table.

The APQA monitoring panel supplies only a resistant cutoff (MIC >= resistant_min -> R),
so by default a MIC below that cutoff is reported S. If a user fills in susceptible_max
and/or intermediate_min, full three-way S/I/R is produced.
"""
import re
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Breakpoint


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
                      host: Optional[str] = None) -> Optional[Breakpoint]:
    """Pick the best breakpoint for (organism, antibiotic[, host]).

    Organism matches case-insensitively, either exactly or as a prefix (so
    'Escherichia coli O157' still matches the 'Escherichia coli' panel). An exact
    host match is preferred; otherwise the most conservative row (lowest
    resistant_min) with a usable cutoff wins."""
    if not organism or not antibiotic:
        return None
    org = organism.strip().lower()
    abx = antibiotic.strip().lower()
    q = db.query(Breakpoint).filter(
        func.lower(Breakpoint.antibiotic) == abx,
    )
    cands = [b for b in q.all()
             if org == b.organism.lower() or org.startswith(b.organism.lower())
             or b.organism.lower().startswith(org)]
    if not cands:
        # try abbreviation
        cands = [b for b in db.query(Breakpoint).filter(func.lower(Breakpoint.abbreviation) == abx).all()
                 if org == b.organism.lower() or org.startswith(b.organism.lower())
                 or b.organism.lower().startswith(org)]
    # never interpret with the other specific animal's cutoff
    if host and host.lower() in ("dog", "cat"):
        other = "cat" if host.lower() == "dog" else "dog"
        cands = [b for b in cands if (b.host or "").lower() != other] or cands

    if not cands:
        return None

    def rank(b):
        host_match = 0 if (host and b.host and host.lower() == b.host.lower()) else 1
        has_cutoff = 0 if b.resistant_min is not None else 1
        rmin = b.resistant_min if b.resistant_min is not None else float("inf")
        return (host_match, has_cutoff, rmin)

    return sorted(cands, key=rank)[0]


def interpret(bp: Optional[Breakpoint], mic) -> Optional[str]:
    """Return 'S'/'I'/'R' (or None if undeterminable) for a MIC against a breakpoint."""
    val = parse_mic(mic)
    if bp is None or val is None:
        return None
    if bp.resistant_min is not None and val >= bp.resistant_min:
        return "R"
    if bp.susceptible_max is not None and val <= bp.susceptible_max:
        return "S"
    if bp.intermediate_min is not None and val >= bp.intermediate_min:
        return "I"
    if bp.resistant_min is not None:   # below the resistant cutoff, no S/I bands -> susceptible
        return "S"
    return None


def interpret_mic(db: Session, organism: str, antibiotic: str, mic,
                  host: Optional[str] = None):
    """Convenience: select + interpret. Returns (sir|None, Breakpoint|None)."""
    bp = select_breakpoint(db, organism, antibiotic, host)
    return interpret(bp, mic), bp
