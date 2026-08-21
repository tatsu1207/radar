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
#
# Tier assignment follows a four-step cascade (per the paper):
#   1. Per-agent tiers from the AMRFinderPlus Subclass (worst-case rule)
#   2. Mode tier of the corresponding antibiotic Class (representative value)
#   3. Worst-case tier of the gene family
#   4. No tier (intrinsic/undetermined)
# ---------------------------------------------------------------------------

# Step 1: Individual antibiotic agent → AWaRe tier (WHO AWaRe 2023)
# These must be actual agent names, NOT class names.
_AGENT_TIER = {
    # Reserve agents
    "colistin": "Reserve",
    "polymyxin": "Reserve",
    "polymyxin b": "Reserve",
    "imipenem": "Reserve",
    "meropenem": "Reserve",
    "ertapenem": "Reserve",
    "doripenem": "Reserve",
    "tigecycline": "Reserve",
    "linezolid": "Reserve",
    "tedizolid": "Reserve",
    "daptomycin": "Reserve",
    "fosfomycin": "Reserve",
    "ceftazidime-avibactam": "Reserve",
    "ceftolozane-tazobactam": "Reserve",
    "plazomicin": "Reserve",
    "vancomycin": "Reserve",
    "teicoplanin": "Reserve",
    "aztreonam": "Reserve",
    # Watch agents
    "cefotaxime": "Watch",
    "ceftriaxone": "Watch",
    "ceftazidime": "Watch",
    "cefepime": "Watch",
    "cefixime": "Watch",
    "cefpodoxime": "Watch",
    "ciprofloxacin": "Watch",
    "levofloxacin": "Watch",
    "moxifloxacin": "Watch",
    "norfloxacin": "Watch",
    "ofloxacin": "Watch",
    "azithromycin": "Watch",
    "clarithromycin": "Watch",
    "erythromycin": "Watch",
    "gentamicin": "Watch",
    "amikacin": "Watch",
    "tobramycin": "Watch",
    "piperacillin-tazobactam": "Watch",
    "ampicillin-sulbactam": "Watch",
    "amoxicillin-clavulanate": "Watch",
    # Access agents
    "amoxicillin": "Access",
    "ampicillin": "Access",
    "penicillin": "Access",
    "doxycycline": "Access",
    "tetracycline": "Access",
    "chloramphenicol": "Access",
    "trimethoprim": "Access",
    "sulfamethoxazole": "Access",
    "nitrofurantoin": "Access",
    "metronidazole": "Access",
    "clindamycin": "Access",
    "streptomycin": "Access",
    "kanamycin": "Access",
    "spectinomycin": "Access",
    "nalidixic acid": "Access",
    "florfenicol": "Access",
    "mupirocin": "Access",
}

# Step 2: Antibiotic class → mode AWaRe tier (representative value)
# Mode = most frequent tier among the class's agents; ties → higher tier.
# This is the FALLBACK when no specific agent matches in step 1.
_CLASS_MODE_TIER = {
    # Reserve-mode classes (majority of agents are Reserve)
    "glycopeptide": "Reserve",
    "lipopeptide": "Reserve",
    "oxazolidinone": "Reserve",
    "polymyxin": "Reserve",
    "carbapenem": "Reserve",
    "glycylcycline": "Reserve",
    # Watch-mode classes (majority of agents are Watch)
    "cephalosporin": "Watch",
    "fluoroquinolone": "Watch",
    "quinolone": "Watch",
    "macrolide": "Watch",
    "aminoglycoside": "Watch",
    "monobactam": "Watch",
    "rifamycin": "Watch",
    "streptogramin": "Watch",
    # Access-mode classes (majority of agents are Access)
    "beta-lactam": "Access",
    "penicillin": "Access",
    "tetracycline": "Access",
    "phenicol": "Access",
    "sulfonamide": "Access",
    "trimethoprim": "Access",
    "fosfomycin": "Reserve",
    "lincosamide": "Access",
    "nitroimidazole": "Access",
    "nitrofuran": "Access",
    "fusidane": "Access",
    "mupirocin": "Access",
    "aminocoumarin": "Access",
    "diaminopyrimidine": "Access",
    "nucleoside": "Access",
    "pleuromutilin": "Access",
    "elfamycin": "Access",
    "tunicamycin": "Access",
    "bicyclomycin": "Access",
    "thiostrepton": "Access",
}

# Step 3: Gene-family worst-case tier (fallback when class/agent unknown)
# Only used when neither step 1 nor step 2 produces a tier.
_GENE_FAMILY_TIER = {
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
    "blactx-m": "Watch", "blacmy": "Watch", "bladha": "Watch",
    # Glycylcycline-specific → Reserve (tet(X) family)
    "tetx": "Reserve",
    "tmexcd": "Reserve",
}

# Non-antimicrobial drug classes (STRESS/BIOCIDE/METAL) — excluded from
# AWaRe tier assignment and MDR counting per the paper ("only Type=AMR").
_NON_AMR_CLASSES = {
    "efflux", "arsenic", "arsenate", "copper", "copper/silver", "silver",
    "mercury", "organomercury", "zinc", "cadmium", "chromium", "lead",
    "tellurium", "nickel", "cobalt", "quaternary ammonium", "hydrogen peroxide",
    "triclosan", "benzalkonium", "chlorhexidine", "na",
}

# AMRFinderPlus mechanism values that indicate non-antimicrobial resistance
_NON_AMR_MECHANISMS = {"BIOCIDE", "METAL", "ACID", "STRESS"}


def _is_amr_entry(arg: ARGResult) -> bool:
    """Check if an ARGResult is an antimicrobial resistance entry (not STRESS/METAL/BIOCIDE)."""
    mechanism = (arg.mechanism or "").upper()
    if mechanism in _NON_AMR_MECHANISMS:
        return False
    # Also check drug class
    if arg.drug_class:
        main_class = arg.drug_class.split(";")[0].strip().lower()
        if main_class in _NON_AMR_CLASSES:
            return False
    return True


def _normalize_class(raw_class: str) -> str:
    """Normalize antibiotic class string for matching."""
    return raw_class.strip().lower().replace(" ", "").replace("-", "").replace("/", "")


def _get_aware_tier(gene: str, drug_class: str, mechanism: str) -> Optional[str]:
    """Determine AWaRe tier for an ARG using the four-step cascade.

    Step 1: Per-agent tiers from the Subclass (worst-case across agents)
    Step 2: Mode tier of the antibiotic Class (representative, avoids over-estimation)
    Step 3: Worst-case tier of the gene family (last resort)
    Step 4: No tier (intrinsic/undetermined)
    """
    if not drug_class:
        # No drug class → skip to step 3 (gene family)
        return _gene_family_fallback(gene)

    # Parse "Class; Subclass" format from AMRFinderPlus
    # Main class may contain "/" for multi-class genes (e.g., "AMINOGLYCOSIDE/QUINOLONE")
    parts = [p.strip() for p in drug_class.split(";")]
    main_class = parts[0] if parts else ""
    subclass = ";".join(parts[1:]) if len(parts) > 1 else ""

    # ── Step 1: Per-agent tiers from Subclass (worst-case rule) ──
    # AMRFinderPlus subclass may contain individual agents ("STREPTOMYCIN")
    # or class-level terms ("CEPHALOSPORIN"). Both are checked.
    if subclass:
        best_tier = None
        best_order = 0
        agents = [a.strip().lower() for a in subclass.replace("/", ";").split(";") if a.strip()]
        for agent in agents:
            # Try exact match in agent tier table
            tier = _AGENT_TIER.get(agent)
            if not tier:
                # Try fuzzy match against known agents
                for known_agent, t in _AGENT_TIER.items():
                    if known_agent in agent or agent in known_agent:
                        tier = t
                        break
            if not tier:
                # Subclass term might be a class name (e.g., "CEPHALOSPORIN")
                tier = _CLASS_MODE_TIER.get(agent)
            if tier:
                order = _TIER_ORDER.get(tier, 0)
                if order > best_order:
                    best_order = order
                    best_tier = tier
                    if tier == "Reserve":
                        return "Reserve"  # Can't get higher

        if best_tier:
            return best_tier

    # ── Step 2: Class-level mode tier ──
    # Main class may be multi-class ("AMINOGLYCOSIDE/QUINOLONE") — use worst-case
    main_classes = [c.strip().lower() for c in main_class.split("/") if c.strip()]
    best_tier = None
    best_order = 0
    for mc in main_classes:
        tier = _CLASS_MODE_TIER.get(mc)
        if not tier:
            normalized = _normalize_class(mc)
            for key, t in _CLASS_MODE_TIER.items():
                if _normalize_class(key) == normalized:
                    tier = t
                    break
        if tier:
            order = _TIER_ORDER.get(tier, 0)
            if order > best_order:
                best_order = order
                best_tier = tier
    if best_tier:
        return best_tier

    # ── Step 3: Gene-family fallback (worst-case rule) ──
    return _gene_family_fallback(gene)


def _gene_family_fallback(gene: str) -> Optional[str]:
    """Step 3: Map gene name to AWaRe tier by gene family prefix."""
    gene_lower = gene.lower().replace("-", "").replace("_", "")
    for prefix, tier in _GENE_FAMILY_TIER.items():
        if gene_lower.startswith(prefix):
            return tier
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
    # Per paper: point mutations are NEVER re-scored for ICE location
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
    elif rank in (HazardRank.R6, HazardRank.R7, HazardRank.R8,
                  HazardRank.R9, HazardRank.R10):
        return RiskCategory.medium
    elif rank in (HazardRank.R11, HazardRank.R12):
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
    1. Filter to AMR-type entries only (exclude STRESS/BIOCIDE/METAL)
    2. For each AMR ARG, determine AWaRe tier and transmissibility level
    3. Find worst-case ARG (highest tier, then highest transmissibility)
    4. Assign rank R1-R12 or NG
    5. Flag MDR (≥3 distinct antimicrobial classes)
    6. Count VF categories as annotation
    """
    all_arg_results = db.query(ARGResult).filter(
        ARGResult.sample_id == sample_id
    ).all()
    plasmids = db.query(PlasmidResult).filter(
        PlasmidResult.sample_id == sample_id
    ).all()
    ice_results = db.query(ICEResult).filter(
        ICEResult.sample_id == sample_id
    ).all()
    vf_results = db.query(VirulenceResult).filter(
        VirulenceResult.sample_id == sample_id
    ).all()

    # Filter to AMR-type entries only (per paper: "only Type=AMR")
    amr_args = [a for a in all_arg_results if _is_amr_entry(a)]

    # Build plasmid contig mapping from ARGResult.contig_type
    plasmid_contigs = {}
    for arg in all_arg_results:
        if arg.on_plasmid and arg.contig_type:
            ct = arg.contig_type
            if ct.startswith("plasmid"):
                cluster = ct.replace("plasmid (", "").rstrip(")")
                if cluster and cluster != "plasmid":
                    plasmid_contigs[arg.contig] = cluster

    # Also ensure plasmid contigs are mapped via PlasmidResult
    for p in plasmids:
        for arg in all_arg_results:
            if arg.on_plasmid and arg.contig_type and p.plasmid_id \
                    and p.plasmid_id in arg.contig_type:
                plasmid_contigs[arg.contig] = p.plasmid_id

    # Score each AMR ARG
    worst_tier_order = 0
    worst_level = 0
    worst_arg = None
    worst_arg_tier = None
    worst_arg_level = None
    worst_arg_location = None
    worst_drug_class = None
    has_tiered_arg = False

    # Collect antimicrobial drug classes for MDR (AMR entries only)
    drug_classes = set()

    for arg in amr_args:
        # Collect drug classes for MDR counting
        # Handle multi-class format ("AMINOGLYCOSIDE/QUINOLONE; ...")
        if arg.drug_class:
            main_part = arg.drug_class.split(";")[0].strip()
            for mc in main_part.split("/"):
                mc = mc.strip().lower()
                if mc and mc not in _NON_AMR_CLASSES:
                    drug_classes.add(mc)

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
    if not amr_args:
        # No AMR-type ARGs at all
        hazard_rank = HazardRank.R12
        aware_tier = None
        trans_level = None
        wc_gene = None
        wc_class = None
        wc_location = None
    elif not has_tiered_arg:
        # Has AMR ARGs but none map to an AWaRe tier → NG
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

    # MDR flag (≥3 distinct antimicrobial classes)
    mdr = len(drug_classes) >= 3

    # VF category count (annotation only, orthogonal to rank)
    vf_categories = set()
    for vf in vf_results:
        if vf.category:
            vf_categories.add(vf.category.lower())
    vf_cat_count = len(vf_categories)

    # Legacy scores for backwards compat
    composite = _rank_to_score(hazard_rank)
    category = _rank_to_category(hazard_rank)

    # Upsert
    existing = db.query(RiskScore).filter(
        RiskScore.sample_id == sample_id
    ).first()
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
        existing.arg_score = composite
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
