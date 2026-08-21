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
    SpeciesResult,
    MLSTResult,
    Metadata,
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
    "arsenic", "arsenate", "copper", "copper/silver", "silver",
    "mercury", "organomercury", "zinc", "cadmium", "chromium", "lead",
    "tellurium", "nickel", "cobalt", "quaternary ammonium", "hydrogen peroxide",
    "triclosan", "benzalkonium", "chlorhexidine", "na",
}

# Classes excluded from MDR counting but NOT from hazard ranking.
# Efflux is a resistance mechanism, not an antibiotic class — it should not
# count toward MDR (≥3 distinct classes), but efflux pump genes that
# AMRFinderPlus labels Type=AMR should still participate in worst-case
# selection (they map to no AWaRe tier, so they won't drive the rank).
_MDR_EXCLUDED_CLASSES = _NON_AMR_CLASSES | {"efflux"}

# AMRFinderPlus mechanism values that indicate non-antimicrobial resistance
_NON_AMR_MECHANISMS = {"BIOCIDE", "METAL", "ACID", "STRESS"}

# ---------------------------------------------------------------------------
# Intrinsic/species-core gene filtering
#
# Species-core determinants are near-universal chromosomal genes that inflate
# the rank without representing actionable resistance. They are excluded from
# worst-case selection UNLESS activated by:
#   - An IS element within ~500 bp upstream (e.g., ISAba1 → blaOXA-51-like)
#   - A resistance-conferring point mutation in the gene
#
# Gene → species mapping. A gene is considered intrinsic only when:
#   1. It matches a prefix in this table AND
#   2. The isolate species matches the listed species AND
#   3. The gene is chromosomal (not on a plasmid)
# ---------------------------------------------------------------------------

_INTRINSIC_GENES = {
    # A. baumannii intrinsic beta-lactamases
    "blaoxa-51": "acinetobacter baumannii",
    "blaoxa-64": "acinetobacter baumannii",
    "blaoxa-65": "acinetobacter baumannii",
    "blaoxa-66": "acinetobacter baumannii",
    "blaoxa-67": "acinetobacter baumannii",
    "blaoxa-68": "acinetobacter baumannii",
    "blaoxa-69": "acinetobacter baumannii",
    "blaoxa-70": "acinetobacter baumannii",
    "blaoxa-71": "acinetobacter baumannii",
    "blaoxa-78": "acinetobacter baumannii",
    "blaoxa-82": "acinetobacter baumannii",
    "blaoxa-83": "acinetobacter baumannii",
    "blaoxa-84": "acinetobacter baumannii",
    "blaoxa-86": "acinetobacter baumannii",
    "blaoxa-87": "acinetobacter baumannii",
    "blaoxa-88": "acinetobacter baumannii",
    "blaoxa-89": "acinetobacter baumannii",
    "blaoxa-90": "acinetobacter baumannii",
    "blaoxa-91": "acinetobacter baumannii",
    "blaoxa-92": "acinetobacter baumannii",
    "blaoxa-94": "acinetobacter baumannii",
    "blaoxa-95": "acinetobacter baumannii",
    "blaoxa-98": "acinetobacter baumannii",
    "blaoxa-99": "acinetobacter baumannii",
    "blaoxa-104": "acinetobacter baumannii",
    "blaoxa-106": "acinetobacter baumannii",
    "blaoxa-107": "acinetobacter baumannii",
    "blaadc": "acinetobacter baumannii",
    # A. baumannii intrinsic efflux/resistance
    "adeb": "acinetobacter baumannii",
    "adea": "acinetobacter baumannii",
    "ader": "acinetobacter baumannii",
    "ades": "acinetobacter baumannii",
    # E. coli intrinsic chromosomal beta-lactamase
    "blaec": "escherichia coli",
    "ampc": "escherichia coli",
    # Salmonella intrinsic efflux
    "mdsab": "salmonella enterica",
    "mdsa": "salmonella enterica",
    "mdsb": "salmonella enterica",
    "mdsc": "salmonella enterica",
    "acrb": "salmonella enterica",
    # K. pneumoniae intrinsic beta-lactamases
    "blashv-1": "klebsiella pneumoniae",
    "blashv-11": "klebsiella pneumoniae",
    "blashv-26": "klebsiella pneumoniae",
    "blashv-28": "klebsiella pneumoniae",
    "blashv-33": "klebsiella pneumoniae",
    "blashv-36": "klebsiella pneumoniae",
    "blashv-38": "klebsiella pneumoniae",
    "blashv-41": "klebsiella pneumoniae",
    "blashv-56": "klebsiella pneumoniae",
    "blashv-60": "klebsiella pneumoniae",
    "blashv-61": "klebsiella pneumoniae",
    "blashv-62": "klebsiella pneumoniae",
    "blashv-75": "klebsiella pneumoniae",
    "blashv-76": "klebsiella pneumoniae",
    "blashv-100": "klebsiella pneumoniae",
    "blashv-110": "klebsiella pneumoniae",
    "blashv-187": "klebsiella pneumoniae",
    "oxyr": "klebsiella pneumoniae",
    # K. pneumoniae intrinsic fosfomycin resistance
    "fosA": "klebsiella pneumoniae",
    "fosa": "klebsiella pneumoniae",
    # S. aureus intrinsic
    "meca": "staphylococcus aureus",  # NOT intrinsic, but mecA is acquired — keep it
    "nora": "staphylococcus aureus",
    "mgrA": "staphylococcus aureus",
    "mgra": "staphylococcus aureus",
    "arlr": "staphylococcus aureus",
    "arls": "staphylococcus aureus",
    # Common intrinsic efflux pumps across Enterobacterales
    "acra": "enterobacterales",
    "acrb": "enterobacterales",
    "tolc": "enterobacterales",
    "mara": "enterobacterales",
    "marr": "enterobacterales",
    "soxs": "enterobacterales",
    "soxr": "enterobacterales",
    "rob": "enterobacterales",
    "emrd": "enterobacterales",
    "mdtk": "enterobacterales",
    "mdtm": "enterobacterales",
}

# IS elements known to activate intrinsic genes when inserted upstream
_ACTIVATING_IS = {
    "isaba1", "isaba125", "isaba2", "isaba3", "isaba4",  # A. baumannii
    "isecp1", "is26", "is1",  # Enterobacterales
}

# Maximum distance (bp) for an IS element to be considered activating
_IS_ACTIVATION_DISTANCE = 500


def _is_amr_entry(arg: ARGResult) -> bool:
    """Check if an ARGResult is an antimicrobial resistance entry.

    Excludes STRESS/METAL/BIOCIDE/ACID mechanism types and their drug classes.
    Efflux pump genes with AMRFinderPlus Type=AMR are INCLUDED — they participate
    in hazard ranking (though they map to no AWaRe tier). They are excluded from
    MDR counting separately via _MDR_EXCLUDED_CLASSES.
    """
    mechanism = (arg.mechanism or "").upper()
    if mechanism in _NON_AMR_MECHANISMS:
        return False
    # Check drug class — exclude non-AMR classes but keep efflux
    if arg.drug_class:
        main_class = arg.drug_class.split(";")[0].strip().lower()
        if main_class in _NON_AMR_CLASSES:
            return False
    return True


def _get_species_name(sample_id: str, db) -> Optional[str]:
    """Get species name for a sample from available sources."""
    # Try SpeciesResult first
    sr = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    if sr and sr.species:
        species = sr.species.lower()
        # If it looks like a species name (has space), use it
        if " " in species:
            return species

    # Try MLST scheme → species mapping
    mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
    if mlst and mlst.scheme:
        scheme_map = {
            "ecoli": "escherichia coli",
            "ecoli_achtman_4": "escherichia coli",
            "senterica": "salmonella enterica",
            "klebsiella": "klebsiella pneumoniae",
            "kpneumoniae": "klebsiella pneumoniae",
            "saureus": "staphylococcus aureus",
            "abaumannii": "acinetobacter baumannii",
            "abaumannii_2": "acinetobacter baumannii",
            "efaecium": "enterococcus faecium",
            "efaecalis": "enterococcus faecalis",
        }
        species = scheme_map.get(mlst.scheme.lower())
        if species:
            return species

    # Try Metadata
    meta = db.query(Metadata).filter(Metadata.sample_id == sample_id).first()
    if meta and meta.species:
        return meta.species.lower()

    return None


def _is_intrinsic(gene: str, species: Optional[str]) -> bool:
    """Check if a gene is intrinsic to the given species.

    Returns True if the gene matches the intrinsic gene table AND the species
    matches (or species is in the Enterobacterales order for order-level entries).

    Uses exact matching (after normalization) to avoid prefix collisions like
    blaSHV-1 (intrinsic) matching blaSHV-12 (acquired ESBL).
    """
    if not species:
        return False

    gene_lower = gene.lower().replace("-", "").replace("_", "")
    species_lower = species.lower()

    # Enterobacterales member species
    enterobacterales = {
        "escherichia coli", "salmonella enterica", "klebsiella pneumoniae",
        "enterobacter cloacae", "citrobacter freundii", "serratia marcescens",
        "proteus mirabilis", "morganella morganii",
    }

    for entry, intrinsic_species in _INTRINSIC_GENES.items():
        entry_norm = entry.lower().replace("-", "").replace("_", "")
        # Exact match after normalization
        if gene_lower != entry_norm:
            continue
        if intrinsic_species == "enterobacterales":
            return species_lower in enterobacterales
        if intrinsic_species in species_lower or species_lower in intrinsic_species:
            return True

    return False


def _has_activating_context(
    arg: ARGResult,
    mobility_results: list,
) -> bool:
    """Check if an intrinsic gene has activating context that restores its hazard.

    Activating context:
    1. A known activating IS element within _IS_ACTIVATION_DISTANCE bp upstream
    2. The gene is annotated with a point mutation (mechanism contains POINT)
    """
    # Point mutation activation
    mechanism = (arg.mechanism or "").upper()
    if "POINT" in mechanism:
        return True
    if arg.point_mutations:
        return True

    # IS element upstream activation
    if arg.contig and arg.start and arg.end:
        for mob in mobility_results:
            if mob.contig and mob.contig == arg.contig and mob.start and mob.end:
                # Check if IS element name is a known activator
                is_name = (mob.element_type or "").lower().replace(" ", "").replace("-", "").replace("_", "")
                is_family = (mob.family or "").lower().replace(" ", "").replace("-", "").replace("_", "")

                is_activating = False
                for act_is in _ACTIVATING_IS:
                    act_norm = act_is.lower().replace("-", "").replace("_", "")
                    if act_norm in is_name or act_norm in is_family:
                        is_activating = True
                        break

                if not is_activating:
                    continue

                # Check distance: IS must be within _IS_ACTIVATION_DISTANCE
                # upstream of the ARG
                # "Upstream" depends on strand; since we don't track strand,
                # check proximity in either direction
                is_end = mob.end
                is_start = mob.start
                arg_start = arg.start
                arg_end = arg.end

                # Distance from IS to ARG (either direction)
                if is_end <= arg_start:
                    dist = arg_start - is_end
                elif is_start >= arg_end:
                    dist = is_start - arg_end
                else:
                    dist = 0  # Overlapping

                if dist <= _IS_ACTIVATION_DISTANCE:
                    return True

    return False


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


def _extract_genus(species_name: Optional[str]) -> Optional[str]:
    """Extract genus from a species string like 'Escherichia coli' → 'escherichia'."""
    if not species_name:
        return None
    parts = species_name.strip().split()
    return parts[0].lower() if parts else None


def _is_broad_host_range(plasmid, isolate_species: Optional[str]) -> bool:
    """Determine if a conjugative plasmid has broad host range.

    Per the paper: broad = predicted host-range rank >= family.
    We compare the genus of the plasmid's nearest mash neighbor against the
    isolate's genus. Different genus → broad (level 5), same genus → narrow (4).
    Unknown neighbor → broad (conservative default).
    """
    neighbor = plasmid.mash_neighbor_identification if hasattr(plasmid, 'mash_neighbor_identification') else None
    if not neighbor or not isolate_species:
        return True  # Unknown → default to broad (conservative)

    isolate_genus = _extract_genus(isolate_species)
    neighbor_genus = _extract_genus(neighbor)

    if not isolate_genus or not neighbor_genus:
        return True  # Can't determine → broad

    # Different genus = broad host range
    return isolate_genus != neighbor_genus


def _get_transmissibility_level(
    arg: ARGResult,
    plasmids: list,
    ice_results: list,
    plasmid_contigs: dict,
    isolate_species: Optional[str] = None,
) -> Tuple[int, str]:
    """Determine transmissibility level (1-5) for an ARG.

    Returns (level, location_description).

    Levels:
      5 = conjugative plasmid (broad host range: neighbor genus != isolate genus)
      4 = conjugative plasmid (narrow host range: same genus) or ICE-borne chromosomal
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
                if _is_broad_host_range(plasmid, isolate_species):
                    return 5, f"plasmid (conjugative-broad, {cluster_id})"
                else:
                    return 4, f"plasmid (conjugative-narrow, {cluster_id})"

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
    mobility_results = db.query(MobilityResult).filter(
        MobilityResult.sample_id == sample_id
    ).all()

    # Get species for intrinsic gene filtering
    species = _get_species_name(sample_id, db)

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
    intrinsic_skipped = []

    # Collect antimicrobial drug classes for MDR (AMR entries only)
    drug_classes = set()

    for arg in amr_args:
        # Collect drug classes for MDR counting
        # Handle multi-class format ("AMINOGLYCOSIDE/QUINOLONE; ...")
        # Uses _MDR_EXCLUDED_CLASSES which includes efflux (a mechanism, not a class)
        if arg.drug_class:
            main_part = arg.drug_class.split(";")[0].strip()
            for mc in main_part.split("/"):
                mc = mc.strip().lower()
                if mc and mc not in _MDR_EXCLUDED_CLASSES:
                    drug_classes.add(mc)

        tier = _get_aware_tier(arg.gene, arg.drug_class, arg.mechanism)
        level, location = _get_transmissibility_level(
            arg, plasmids, ice_results, plasmid_contigs, isolate_species=species
        )

        # Filter intrinsic/species-core chromosomal genes from worst-case
        # selection. Intrinsic genes are still counted for MDR but cannot
        # drive the hazard rank, UNLESS they have activating context
        # (IS element upstream or point mutation).
        if tier is not None and not arg.on_plasmid \
                and _is_intrinsic(arg.gene, species) \
                and not _has_activating_context(arg, mobility_results):
            intrinsic_skipped.append(arg.gene)
            continue

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

    intrinsic_msg = f", intrinsic_skipped={intrinsic_skipped}" if intrinsic_skipped else ""
    logger.info(
        f"Hazard rank for {sample_id}: {hazard_rank.value} "
        f"(tier={aware_tier}, level={trans_level}, "
        f"worst_arg={wc_gene}, MDR={mdr}, species={species}, "
        f"classes={len(drug_classes)}, VF_cats={vf_cat_count}{intrinsic_msg})"
    )
    return risk
