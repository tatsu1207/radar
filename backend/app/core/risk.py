import logging
from typing import Optional

from app.models.models import (
    ARGResult,
    VirulenceResult,
    MobilityResult,
    PlasmidResult,
    RiskScore,
    RiskCategory,
)
from app.schemas.schemas import RiskWeights

logger = logging.getLogger(__name__)

# WHO Critically Important Antimicrobial resistance genes
WHO_CIA_ARGS = {
    "mcr-1", "mcr-2", "mcr-3", "mcr-4", "mcr-5",
    "blaNDM-1", "blaNDM-5", "blaNDM",
    "blaKPC-2", "blaKPC-3", "blaKPC",
    "blaOXA-48",
    "vanA",
    "cfr",
}

# High-concern virulence categories
HIGH_CONCERN_VF_CATEGORIES = {
    "toxin", "immune evasion", "serum resistance", "invasion",
}


def calculate_arg_risk(sample_id: str, db) -> float:
    """Calculate ARG-based risk score (0-10).

    Scoring criteria:
    - Base score from number of unique ARGs (0-4 points)
    - Drug class diversity bonus (0-3 points)
    - WHO CIA gene presence bonus (0-3 points)

    Args:
        sample_id: UUID of the sample
        db: SQLAlchemy session

    Returns:
        Risk score between 0.0 and 10.0
    """
    arg_results = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()

    if not arg_results:
        return 0.0

    # Unique genes (deduplicate across databases)
    unique_genes = set(arg.gene for arg in arg_results)
    gene_count = len(unique_genes)

    # Number of ARGs score: 0-4 points
    # 1-3 genes = 1pt, 4-6 = 2pt, 7-10 = 3pt, >10 = 4pt
    if gene_count >= 10:
        arg_count_score = 4.0
    elif gene_count >= 7:
        arg_count_score = 3.0
    elif gene_count >= 4:
        arg_count_score = 2.0
    elif gene_count >= 1:
        arg_count_score = 1.0
    else:
        arg_count_score = 0.0

    # Drug class diversity: 0-3 points
    drug_classes = set()
    for arg in arg_results:
        if arg.drug_class:
            for dc in arg.drug_class.split(";"):
                drug_classes.add(dc.strip().lower())

    class_count = len(drug_classes)
    if class_count >= 5:
        diversity_score = 3.0
    elif class_count >= 3:
        diversity_score = 2.0
    elif class_count >= 1:
        diversity_score = 1.0
    else:
        diversity_score = 0.0

    # WHO CIA presence: 0-3 points
    cia_found = 0
    for gene in unique_genes:
        for cia in WHO_CIA_ARGS:
            if cia.lower() in gene.lower():
                cia_found += 1
                break

    if cia_found >= 3:
        cia_score = 3.0
    elif cia_found >= 2:
        cia_score = 2.5
    elif cia_found >= 1:
        cia_score = 2.0
    else:
        cia_score = 0.0

    total = min(arg_count_score + diversity_score + cia_score, 10.0)
    logger.info(
        f"ARG risk for {sample_id}: {total:.1f} "
        f"(genes={gene_count}, classes={class_count}, CIA={cia_found})"
    )
    return round(total, 2)


def calculate_vf_risk(sample_id: str, db) -> float:
    """Calculate virulence factor risk score (0-10).

    Scoring criteria:
    - Base score from VF count (0-5 points)
    - High-concern category bonus (0-5 points)

    Args:
        sample_id: UUID of the sample
        db: SQLAlchemy session

    Returns:
        Risk score between 0.0 and 10.0
    """
    vf_results = db.query(VirulenceResult).filter(VirulenceResult.sample_id == sample_id).all()

    if not vf_results:
        return 0.0

    unique_vfs = set(vf.gene for vf in vf_results)
    vf_count = len(unique_vfs)

    # VF count score: 0-5 points
    if vf_count >= 10:
        count_score = 5.0
    elif vf_count >= 7:
        count_score = 4.0
    elif vf_count >= 5:
        count_score = 3.0
    elif vf_count >= 3:
        count_score = 2.0
    elif vf_count >= 1:
        count_score = 1.0
    else:
        count_score = 0.0

    # High-concern categories: 0-5 points
    categories = set()
    for vf in vf_results:
        if vf.category:
            categories.add(vf.category.lower())

    high_concern_count = len(categories & HIGH_CONCERN_VF_CATEGORIES)
    if high_concern_count >= 3:
        category_score = 5.0
    elif high_concern_count >= 2:
        category_score = 3.5
    elif high_concern_count >= 1:
        category_score = 2.0
    else:
        category_score = 0.0

    total = min(count_score + category_score, 10.0)
    logger.info(
        f"VF risk for {sample_id}: {total:.1f} "
        f"(vfs={vf_count}, high_concern_categories={high_concern_count})"
    )
    return round(total, 2)


def calculate_mobility_risk(sample_id: str, db) -> float:
    """Calculate mobility risk score (0-10).

    Scoring criteria:
    - Transferable plasmid count (0-3 points)
    - IS element / integron count (0-3 points)
    - ARGs on mobile elements or near IS/integrons (0-4 points)

    Args:
        sample_id: UUID of the sample
        db: SQLAlchemy session

    Returns:
        Risk score between 0.0 and 10.0
    """
    plasmids = db.query(PlasmidResult).filter(PlasmidResult.sample_id == sample_id).all()
    mobility_elements = db.query(MobilityResult).filter(MobilityResult.sample_id == sample_id).all()
    arg_results = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()

    # Transferable plasmid score: 0-3 points
    transferable_count = sum(1 for p in plasmids if p.predicted_transferability)
    if transferable_count >= 3:
        plasmid_score = 3.0
    elif transferable_count >= 2:
        plasmid_score = 2.0
    elif transferable_count >= 1:
        plasmid_score = 1.5
    else:
        plasmid_score = 0.0

    # IS/integron count score: 0-3 points
    element_count = len(mobility_elements)
    if element_count >= 8:
        element_score = 3.0
    elif element_count >= 5:
        element_score = 2.0
    elif element_count >= 2:
        element_score = 1.5
    elif element_count >= 1:
        element_score = 1.0
    else:
        element_score = 0.0

    # ARGs associated with mobile elements: 0-4 points
    plasmid_args = sum(1 for arg in arg_results if arg.on_plasmid)
    nearby_arg_count = 0
    for me in mobility_elements:
        if me.nearby_args:
            nearby_arg_count += len(me.nearby_args)

    mobile_arg_total = plasmid_args + nearby_arg_count
    if mobile_arg_total >= 8:
        proximity_score = 4.0
    elif mobile_arg_total >= 5:
        proximity_score = 3.0
    elif mobile_arg_total >= 3:
        proximity_score = 2.0
    elif mobile_arg_total >= 1:
        proximity_score = 1.0
    else:
        proximity_score = 0.0

    total = min(plasmid_score + element_score + proximity_score, 10.0)
    logger.info(
        f"Mobility risk for {sample_id}: {total:.1f} "
        f"(transferable_plasmids={transferable_count}, "
        f"elements={element_count}, mobile_args={mobile_arg_total})"
    )
    return round(total, 2)


def _determine_category(score: float) -> RiskCategory:
    """Map a composite score to a risk category."""
    if score < 2.5:
        return RiskCategory.low
    elif score < 5.0:
        return RiskCategory.medium
    elif score < 7.5:
        return RiskCategory.high
    else:
        return RiskCategory.critical


def calculate_composite_risk(
    sample_id: str,
    weights: Optional[RiskWeights] = None,
    db=None,
) -> RiskScore:
    """Calculate composite risk score from all sub-scores.

    Args:
        sample_id: UUID of the sample
        weights: Optional weighting for sub-scores (default: equal)
        db: SQLAlchemy session

    Returns:
        RiskScore ORM instance
    """
    if weights is None:
        weights = RiskWeights()

    arg_score = calculate_arg_risk(sample_id, db)
    vf_score = calculate_vf_risk(sample_id, db)
    mobility_score = calculate_mobility_risk(sample_id, db)

    # Weighted combination
    total_weight = weights.arg_weight + weights.vf_weight + weights.mobility_weight
    if total_weight == 0:
        total_weight = 1.0

    composite = (
        (arg_score * weights.arg_weight)
        + (vf_score * weights.vf_weight)
        + (mobility_score * weights.mobility_weight)
    ) / total_weight

    composite = round(min(composite, 10.0), 2)
    category = _determine_category(composite)

    # Upsert risk score
    existing = db.query(RiskScore).filter(RiskScore.sample_id == sample_id).first()
    if existing:
        existing.arg_score = arg_score
        existing.vf_score = vf_score
        existing.mobility_score = mobility_score
        existing.composite_score = composite
        existing.risk_category = category
        risk = existing
    else:
        risk = RiskScore(
            sample_id=sample_id,
            arg_score=arg_score,
            vf_score=vf_score,
            mobility_score=mobility_score,
            composite_score=composite,
            risk_category=category,
        )
        db.add(risk)

    db.commit()
    db.refresh(risk)

    logger.info(
        f"Composite risk for {sample_id}: {composite:.2f} ({category.value}) "
        f"[ARG={arg_score}, VF={vf_score}, Mobility={mobility_score}]"
    )
    return risk
