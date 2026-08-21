"""Hazard rank framework for isolate-level AMR risk assessment.

Based on: Cheon & Unno (2026) — "A framework for isolate-level antimicrobial
resistance hazard ranking based on clinical importance and transmissibility
in bacterial pathogens."

Each isolate gets a rank (R1-R12 or NG) based on two axes:
  1. AWaRe tier (Reserve > Watch > Access) of its worst-case ARG
  2. Transmissibility level (1-5) of that ARG's genetic context

The old weighted-average scoring (ARG/VF/mobility 0-10) is preserved for
backwards compatibility but the primary output is now the hazard rank.
"""

import logging
from typing import Optional, Tuple

from app.models.models import (
    ARGResult,
    VirulenceResult,
    MobilityResult,
    PlasmidResult,
    ICEResult,
    RiskScore,
    RiskCategory,
    HazardRank,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WHO AWaRe tier mapping
# Maps AMRFinderPlus Class (and Subclass where needed) to AWaRe tiers.
# Uses the worst-case (highest) tier when a class spans multiple agents.
# ---------------------------------------------------------------------------

# Agent-level AWaRe tiers (from WHO AWaRe Classification 2023)
# Reserve antibiotics
_RESERVE_AGENTS = {
    "colistin", "polymyxin", "polymyxin b",
    "carbapenem", "imipenem", "meropenem", "ertapenem", "doripenem",
    "tigecycline",
    "linezolid", "tedizolid",
    "daptomycin",
    "fosfomycin",
    "ceftazidime-avibactam", "ceftolozane-tazobactam",
    "aztreonam",
    "plazomicin",
    "vancomycin", "teicoplanin",
}

# Watch antibiotics
_WATCH_AGENTS = {
    "cephalosporin", "cefotaxime", "ceftriaxone", "ceftazidime", "cefepime",
    "cefixime", "cefpodoxime",
    "fluoroquinolone", "ciprofloxacin", "levofloxacin", "moxifloxacin",
    "norfloxacin", "ofloxacin",
    "macrolide", "azithromycin", "clarithromycin", "erythromycin",
    "piperacillin-tazobactam",
    "ampicillin-sulbactam", "amoxicillin-clavulanate",
    "aminoglycoside", "gentamicin", "amikacin", "tobramycin",
    "glycopeptide",
}

# Class-level AWaRe fallback (mode tier per antibiotic class)
_CLASS_TIER_MAP = {
    # Reserve-tier classes
    "glycopeptide": "Reserve",
    "lipopeptide": "Reserve",
    "oxazolidinone": "Reserve",
    "polymyxin": "Reserve",
    "carbapenem": "Reserve",
    "glycylcycline": "Reserve",
    # Watch-tier classes
    "beta-lactam": "Watch",
    "cephalosporin": "Watch",
    "fluoroquinolone": "Watch",
    "quinolone": "Watch",
    "macrolide": "Watch",
    "aminoglycoside": "Watch",
    "monobactam": "Watch",
    # Access-tier classes
    "tetracycline": "Access",
    "phenicol": "Access",
    "sulfonamide": "Access",
    "trimethoprim": "Access",
    "fosfomycin": "Reserve",
    "rifamycin": "Watch",
    "lincosamide": "Access",
    "streptogramin": "Watch",
    "nitroimidazole": "Access",
    "nitrofuran": "Access",
    "fusidane": "Access",
    "mupirocin": "Access",
    "penicillin": "Access",
    "aminocoumarin": "Access",
    "diaminopyrimidine": "Access",
    "nucleoside": "Access",
    "pleuromutilin": "Access",
    "elfamycin": "Access",
    "tunicamycin": "Access",
    "bicyclomycin": "Access",
    "thiostrepton": "Access",
}

# Gene-family-level overrides for known important ARGs
_GENE_TIER_OVERRIDES = {
    # Carbapenemases → Reserve
    "blandm": "Reserve", "blakpc": "Reserve", "blaoxa-48": "Reserve",
    "blavim": "Reserve", "blaimp": "Reserve", "blages": "Reserve",
    "blaoxa-23": "Reserve", "blaoxa-24": "Reserve", "blaoxa-58": "Reserve",
    # Colistin resistance → Reserve
    "mcr": "Reserve",
    # Vancomycin resistance → Reserve
    "vana": "Reserve", "vanb": "Reserve", "vanc": "Reserve",
    "vand": "Reserve", "vane": "Reserve", "vang": "Reserve",
    # Linezolid resistance → Reserve
    "cfr": "Reserve", "optra": "Reserve",
    # ESBL → Watch (cephalosporin resistance)
    "blactx-m": "Watch", "blashv": "Watch", "blatem": "Watch",
    "blacmy": "Watch", "bladha": "Watch",
    # Glycylcycline-specific → Reserve (tet(X) family)
    "tetx": "Reserve",
    "tmexcd": "Reserve",
}


def _normalize_class(raw_class: str) -> str:
    """Normalize AMRFinderPlus class string for matching."""
    return raw_class.strip().lower().replace(" ", "").replace("-", "").replace("/", "")


def _get_aware_tier(gene: str, drug_class: str, mechanism: str) -> Optional[str]:
    """Determine AWaRe tier for an ARG.

    Cascade:
    1. Gene-family override (known carbapenemases, mcr, van, etc.)
    2. Subclass agent-level matching
    3. Class-level fallback (mode tier)
    4. None (intrinsic/undetermined)
    """
    gene_lower = gene.lower().replace("-", "").replace("_", "")

    # Step 1: gene family overrides
    for prefix, tier in _GENE_TIER_OVERRIDES.items():
        if gene_lower.startswith(prefix):
            return tier

    if not drug_class:
        return None

    # Parse "Class; Subclass" format from AMRFinderPlus
    parts = [p.strip().lower() for p in drug_class.split(";")]
    main_class = parts[0] if parts else ""
    subclasses = parts[1:] if len(parts) > 1 else []

    # Step 2: agent-level from subclass
    best_tier = None
    for sub in subclasses:
        # Check each word in the subclass against agent lists
        sub_words = sub.replace("/", " ").replace("-", " ").split()
        for word in sub_words:
            word = word.strip()
            if word in _RESERVE_AGENTS:
                return "Reserve"  # Can't get higher
            if word in _WATCH_AGENTS:
                best_tier = "Watch"

    # Also check the main class against agent lists
    if main_class in _RESERVE_AGENTS:
        return "Reserve"
    if main_class in _WATCH_AGENTS and best_tier != "Reserve":
        best_tier = "Watch"

    if best_tier:
        return best_tier

    # Step 3: class-level fallback
    normalized = _normalize_class(main_class)
    for key, tier in _CLASS_TIER_MAP.items():
        if _normalize_class(key) in normalized or normalized in _normalize_class(key):
            return tier

    # Step 4: no tier
    return None


# ---------------------------------------------------------------------------
# Transmissibility scoring
# ---------------------------------------------------------------------------

_TIER_ORDER = {"Reserve": 3, "Watch": 2, "Access": 1}


def _get_transmissibility_level(
    arg: ARGResult,
    plasmids: list,
    ice_results: list,
    plasmid_contigs: dict,
) -> Tuple[int, str]:
    """Determine transmissibility level (1-5) for an ARG.

    Returns (level, location_description).

    Levels:
      5 = conjugative plasmid (broad host range or unknown)
      4 = conjugative plasmid (narrow host range) or ICE-borne chromosomal
      3 = mobilizable plasmid with co-occurring conjugative plasmid
      2 = mobilizable plasmid without helper
      1 = non-mobilizable / chromosome / unknown
    """
    contig = arg.contig or ""

    # Check if ARG is on a plasmid
    cluster_id = plasmid_contigs.get(contig)
    if cluster_id:
        # Find the plasmid record
        plasmid = None
        for p in plasmids:
            if p.plasmid_id == cluster_id:
                plasmid = p
                break

        if plasmid:
            mobility = (plasmid.predicted_mobility or "").lower()

            if mobility == "conjugative":
                # Conjugative: check host range
                # If mash_neighbor is from a different genus/family → broad
                # For simplicity: if mash_neighbor exists and differs from
                # isolate species, treat as broad (level 5). Otherwise narrow (4).
                # Default to broad (5) when no host range info available,
                # as conjugative plasmids are high concern regardless.
                return 5, f"plasmid (conjugative, {cluster_id})"

            elif mobility == "mobilizable":
                # Check if a conjugative helper exists in same isolate
                has_conjugative = any(
                    (p2.predicted_mobility or "").lower() == "conjugative"
                    for p2 in plasmids
                )
                if has_conjugative:
                    return 3, f"plasmid (mobilizable+helper, {cluster_id})"
                else:
                    return 2, f"plasmid (mobilizable, {cluster_id})"

            else:
                # Non-mobilizable plasmid
                return 1, f"plasmid (non-mobilizable, {cluster_id})"

        # Plasmid contig but no matching record
        return 1, f"plasmid ({cluster_id})"

    # Check if chromosomal ARG is within an ICE region
    # Only for acquired ARGs (not point mutations)
    mechanism = (arg.mechanism or "").upper()
    is_point_mutation = "POINT" in mechanism

    if not is_point_mutation and arg.start and arg.end and ice_results:
        for ice in ice_results:
            if ice.contig == contig and ice.start and ice.end:
                # Check overlap: ARG within ICE region
                if arg.start >= ice.start and arg.end <= ice.end:
                    # ICE-borne → assign narrow conjugative level (4)
                    return 4, f"ICE ({ice.ice_id or 'unknown'})"

    # Chromosomal / non-mobile
    return 1, "chromosome"


def _assign_rank(tier: Optional[str], level: int) -> HazardRank:
    """Assign hazard rank from AWaRe tier and transmissibility level.

    Reserve + 5→R1, 4→R2, 3→R3, 2→R4, 1→R5
    Watch   + 5→R6, 4→R7, 3→R8, 2→R9, 1→R10
    Access  → R11
    No ARG  → R12
    """
    if tier == "Reserve":
        return {5: HazardRank.R1, 4: HazardRank.R2, 3: HazardRank.R3,
                2: HazardRank.R4, 1: HazardRank.R5}[level]
    elif tier == "Watch":
        return {5: HazardRank.R6, 4: HazardRank.R7, 3: HazardRank.R8,
                2: HazardRank.R9, 1: HazardRank.R10}[level]
    elif tier == "Access":
        return HazardRank.R11
    else:
        return HazardRank.R12


def _rank_to_category(rank: HazardRank) -> RiskCategory:
    """Map hazard rank to legacy risk category for backwards compat."""
    if rank in (HazardRank.R1, HazardRank.R2, HazardRank.R3):
        return RiskCategory.critical
    elif rank in (HazardRank.R4, HazardRank.R5):
        return RiskCategory.high
    elif rank in (HazardRank.R6, HazardRank.R7, HazardRank.R8, HazardRank.R9, HazardRank.R10):
        return RiskCategory.medium
    elif rank == HazardRank.R11:
        return RiskCategory.low
    elif rank == HazardRank.R12:
        return RiskCategory.low
    else:  # NG
        return RiskCategory.low


def _rank_to_score(rank: HazardRank) -> float:
    """Map hazard rank to a 0-10 composite score for backwards compat."""
    score_map = {
        HazardRank.R1: 10.0,
        HazardRank.R2: 9.5,
        HazardRank.R3: 9.0,
        HazardRank.R4: 8.0,
        HazardRank.R5: 7.0,
        HazardRank.R6: 6.0,
        HazardRank.R7: 5.5,
        HazardRank.R8: 5.0,
        HazardRank.R9: 4.5,
        HazardRank.R10: 4.0,
        HazardRank.R11: 2.0,
        HazardRank.R12: 0.0,
        HazardRank.NG: 1.0,
    }
    return score_map.get(rank, 0.0)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def calculate_composite_risk(sample_id: str, db=None, **kwargs) -> RiskScore:
    """Calculate hazard rank for a sample.

    Steps:
    1. For each ARG, determine AWaRe tier and transmissibility level
    2. Find worst-case ARG (highest tier, then highest transmissibility)
    3. Assign rank R1-R12 or NG
    4. Flag MDR (≥3 distinct antibiotic classes)
    5. Count VF categories as annotation
    """
    arg_results = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    plasmids = db.query(PlasmidResult).filter(PlasmidResult.sample_id == sample_id).all()
    ice_results = db.query(ICEResult).filter(ICEResult.sample_id == sample_id).all()
    vf_results = db.query(VirulenceResult).filter(VirulenceResult.sample_id == sample_id).all()

    # Build plasmid contig mapping
    plasmid_contigs = {}
    for arg in arg_results:
        if arg.on_plasmid and arg.contig_type:
            # contig_type is like "plasmid (AA738)"
            ct = arg.contig_type
            if ct.startswith("plasmid"):
                cluster = ct.replace("plasmid (", "").rstrip(")")
                if cluster and cluster != "plasmid":
                    plasmid_contigs[arg.contig] = cluster

    # Also build from PlasmidResult data (more reliable)
    # We need to re-read the contig_report for contig→cluster mapping
    # But we already set this during plasmid.py. Use ARGResult.contig_type.
    # Ensure we have all plasmid contigs mapped
    for p in plasmids:
        # Find ARGs that reference this plasmid
        for arg in arg_results:
            if arg.on_plasmid and arg.contig_type and p.plasmid_id and p.plasmid_id in arg.contig_type:
                plasmid_contigs[arg.contig] = p.plasmid_id

    # Score each ARG
    worst_tier_order = 0
    worst_level = 0
    worst_arg = None
    worst_arg_tier = None
    worst_arg_level = None
    worst_arg_location = None
    worst_drug_class = None
    has_tiered_arg = False

    # Collect drug classes for MDR
    drug_classes = set()

    for arg in arg_results:
        # Collect drug classes
        if arg.drug_class:
            # Use the main class (before semicolon) for MDR counting
            main_class = arg.drug_class.split(";")[0].strip().lower()
            if main_class:
                drug_classes.add(main_class)

        tier = _get_aware_tier(arg.gene, arg.drug_class, arg.mechanism)
        level, location = _get_transmissibility_level(
            arg, plasmids, ice_results, plasmid_contigs
        )

        if tier is not None:
            has_tiered_arg = True
            tier_order = _TIER_ORDER.get(tier, 0)

            # Worst case: highest tier first, then highest transmissibility
            if (tier_order > worst_tier_order) or \
               (tier_order == worst_tier_order and level > worst_level):
                worst_tier_order = tier_order
                worst_level = level
                worst_arg = arg
                worst_arg_tier = tier
                worst_arg_level = level
                worst_arg_location = location
                worst_drug_class = arg.drug_class

    # Determine rank
    if not arg_results:
        hazard_rank = HazardRank.R12
        aware_tier = None
        trans_level = None
        wc_gene = None
        wc_class = None
        wc_location = None
    elif not has_tiered_arg:
        hazard_rank = HazardRank.NG
        aware_tier = None
        trans_level = None
        wc_gene = None
        wc_class = None
        wc_location = None
    else:
        hazard_rank = _assign_rank(worst_arg_tier, worst_arg_level)
        aware_tier = worst_arg_tier
        trans_level = worst_arg_level
        wc_gene = worst_arg.gene if worst_arg else None
        wc_class = worst_drug_class
        wc_location = worst_arg_location

    # MDR flag
    mdr = len(drug_classes) >= 3

    # VF category count
    vf_categories = set()
    for vf in vf_results:
        if vf.category:
            vf_categories.add(vf.category.lower())
    vf_cat_count = len(vf_categories)

    # Legacy scores
    composite = _rank_to_score(hazard_rank)
    category = _rank_to_category(hazard_rank)

    # Upsert
    existing = db.query(RiskScore).filter(RiskScore.sample_id == sample_id).first()
    if existing:
        existing.hazard_rank = hazard_rank
        existing.aware_tier = aware_tier
        existing.transmissibility_level = trans_level
        existing.worst_case_arg = wc_gene
        existing.worst_case_drug_class = wc_class
        existing.worst_case_location = wc_location
        existing.mdr_flag = mdr
        existing.drug_class_count = len(drug_classes)
        existing.vf_category_count = vf_cat_count
        existing.composite_score = composite
        existing.risk_category = category
        existing.arg_score = composite  # legacy
        existing.vf_score = 0.0
        existing.mobility_score = 0.0
        risk = existing
    else:
        risk = RiskScore(
            sample_id=sample_id,
            hazard_rank=hazard_rank,
            aware_tier=aware_tier,
            transmissibility_level=trans_level,
            worst_case_arg=wc_gene,
            worst_case_drug_class=wc_class,
            worst_case_location=wc_location,
            mdr_flag=mdr,
            drug_class_count=len(drug_classes),
            vf_category_count=vf_cat_count,
            composite_score=composite,
            risk_category=category,
            arg_score=composite,
            vf_score=0.0,
            mobility_score=0.0,
        )
        db.add(risk)

    db.commit()
    db.refresh(risk)

    logger.info(
        f"Hazard rank for {sample_id}: {hazard_rank.value} "
        f"(tier={aware_tier}, level={trans_level}, "
        f"worst_arg={wc_gene}, MDR={mdr}, "
        f"classes={len(drug_classes)}, VF_cats={vf_cat_count})"
    )
    return risk
