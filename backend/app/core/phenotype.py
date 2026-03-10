import logging
import re
from typing import Dict, List, Optional

from app.models.models import ARGResult, ASTResult

logger = logging.getLogger(__name__)

# Maps gene name patterns to predicted drug resistances
PHENOTYPE_RULES: Dict[str, List[str]] = {
    "blaTEM": ["ampicillin", "amoxicillin"],
    "blaSHV": ["ampicillin", "amoxicillin"],
    "blaCTX": ["cefotaxime", "ceftriaxone", "ceftazidime"],
    "blaNDM": ["carbapenems", "imipenem", "meropenem", "ertapenem"],
    "blaKPC": ["carbapenems", "imipenem", "meropenem", "ertapenem"],
    "blaOXA-48": ["carbapenems", "imipenem", "meropenem"],
    "blaOXA": ["ampicillin", "amoxicillin"],
    "mecA": ["methicillin", "oxacillin"],
    "mecC": ["methicillin", "oxacillin"],
    "vanA": ["vancomycin"],
    "vanB": ["vancomycin"],
    "mcr": ["colistin"],
    "tet": ["tetracycline", "doxycycline"],
    "ermB": ["erythromycin", "clindamycin"],
    "ermC": ["erythromycin", "clindamycin"],
    "ermA": ["erythromycin", "clindamycin"],
    "sul1": ["sulfamethoxazole"],
    "sul2": ["sulfamethoxazole"],
    "dfrA": ["trimethoprim"],
    "dfrB": ["trimethoprim"],
    "aac": ["aminoglycosides", "gentamicin", "tobramycin"],
    "aph": ["aminoglycosides", "kanamycin"],
    "ant": ["aminoglycosides", "streptomycin"],
    "qnr": ["fluoroquinolones", "ciprofloxacin"],
    "cfr": ["linezolid", "chloramphenicol"],
    "catA": ["chloramphenicol"],
    "catB": ["chloramphenicol"],
    "floR": ["florfenicol", "chloramphenicol"],
    "fosA": ["fosfomycin"],
    "mph": ["macrolides", "azithromycin"],
    "arr": ["rifampicin"],
}


def predict_phenotype(sample_id: str, db) -> Dict[str, str]:
    """Predict antibiotic resistance phenotype from detected ARGs.

    Uses gene name pattern matching against PHENOTYPE_RULES to predict
    which antibiotics the sample is likely resistant to.

    Args:
        sample_id: UUID of the sample
        db: SQLAlchemy session

    Returns:
        Dict mapping antibiotic name to predicted SIR value ("R" or "S")
    """
    logger.info(f"Predicting phenotype for sample {sample_id}")

    arg_results = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()

    # Collect all antibiotics that have a resistance gene
    resistant_antibiotics: set = set()

    for arg in arg_results:
        gene_name = arg.gene
        for pattern, drugs in PHENOTYPE_RULES.items():
            if re.search(re.escape(pattern), gene_name, re.IGNORECASE):
                resistant_antibiotics.update(drugs)

    # Build prediction dict
    # All antibiotics in the rules that were NOT matched are predicted susceptible
    all_antibiotics: set = set()
    for drugs in PHENOTYPE_RULES.values():
        all_antibiotics.update(drugs)

    predictions: Dict[str, str] = {}
    for ab in sorted(all_antibiotics):
        predictions[ab] = "R" if ab in resistant_antibiotics else "S"

    logger.info(
        f"Phenotype prediction for sample {sample_id}: "
        f"{sum(1 for v in predictions.values() if v == 'R')} resistant, "
        f"{sum(1 for v in predictions.values() if v == 'S')} susceptible"
    )

    return predictions


def compare_phenotype(sample_id: str, db) -> List[Dict]:
    """Compare predicted phenotype with observed AST results.

    Args:
        sample_id: UUID of the sample
        db: SQLAlchemy session

    Returns:
        List of dicts with antibiotic, predicted, observed, and concordance
    """
    logger.info(f"Comparing phenotype for sample {sample_id}")

    predictions = predict_phenotype(sample_id, db)
    ast_results = db.query(ASTResult).filter(ASTResult.sample_id == sample_id).all()

    # Build a map of observed results
    observed_map: Dict[str, str] = {}
    for ast in ast_results:
        observed_map[ast.antibiotic.lower()] = ast.sir.value if hasattr(ast.sir, "value") else ast.sir

    comparisons = []
    all_antibiotics = set(predictions.keys()) | set(observed_map.keys())

    for ab in sorted(all_antibiotics):
        predicted = predictions.get(ab)
        observed = observed_map.get(ab.lower())

        concordant = False
        if predicted and observed:
            # Consider S/I as "not resistant" for concordance
            pred_resistant = predicted == "R"
            obs_resistant = observed == "R"
            concordant = pred_resistant == obs_resistant

        comparisons.append({
            "antibiotic": ab,
            "predicted": predicted,
            "observed": observed,
            "concordant": concordant,
        })

    total = len([c for c in comparisons if c["predicted"] and c["observed"]])
    concordant_count = len([c for c in comparisons if c["concordant"] and c["predicted"] and c["observed"]])

    logger.info(
        f"Phenotype comparison for sample {sample_id}: "
        f"{concordant_count}/{total} concordant "
        f"({concordant_count/total*100:.1f}%)" if total > 0 else
        f"No overlapping antibiotics for comparison"
    )

    return comparisons
