import logging
import re
from typing import Dict, List, Optional

from app.models.models import ARGResult, ASTResult, MLPhenotypePrediction

logger = logging.getLogger(__name__)

# Maps gene name patterns to (drug_class, [antibiotics])
# Patterns are matched with re.search, so "bla" matches "blaEC", "blaTEM", etc.
# More specific patterns (e.g. "blaOXA-48") must come before generic ones ("blaOXA")
PHENOTYPE_RULES: Dict[str, tuple] = {
    # Beta-lactamases — specific first
    "blaCTX": ("CEPHALOSPORIN", ["cefotaxime", "ceftriaxone", "ceftazidime"]),
    "blaCMY": ("CEPHALOSPORIN", ["cefoxitin", "ceftriaxone", "ceftazidime"]),
    "blaDHA": ("CEPHALOSPORIN", ["cefoxitin", "ceftriaxone"]),
    "blaNDM": ("CARBAPENEM", ["imipenem", "meropenem", "ertapenem"]),
    "blaKPC": ("CARBAPENEM", ["imipenem", "meropenem", "ertapenem"]),
    "blaVIM": ("CARBAPENEM", ["imipenem", "meropenem", "ertapenem"]),
    "blaIMP": ("CARBAPENEM", ["imipenem", "meropenem", "ertapenem"]),
    "blaOXA-48": ("CARBAPENEM", ["imipenem", "meropenem"]),
    "blaOXA-23": ("CARBAPENEM", ["imipenem", "meropenem"]),
    "blaOXA": ("BETA-LACTAM", ["ampicillin", "amoxicillin"]),
    "blaTEM": ("BETA-LACTAM", ["ampicillin", "amoxicillin"]),
    "blaSHV": ("BETA-LACTAM", ["ampicillin", "amoxicillin"]),
    "blaEC": ("BETA-LACTAM", ["ampicillin"]),
    "ampC": ("CEPHALOSPORIN", ["cefoxitin", "ceftriaxone"]),
    "bla": ("BETA-LACTAM", ["ampicillin"]),
    # Methicillin resistance
    "mecA": ("BETA-LACTAM", ["methicillin", "oxacillin"]),
    "mecC": ("BETA-LACTAM", ["methicillin", "oxacillin"]),
    # Glycopeptides
    "vanA": ("GLYCOPEPTIDE", ["vancomycin"]),
    "vanB": ("GLYCOPEPTIDE", ["vancomycin"]),
    # Polymyxins
    "mcr": ("POLYMYXIN", ["colistin"]),
    # Tetracyclines
    "tet": ("TETRACYCLINE", ["tetracycline", "doxycycline"]),
    # Macrolides/Lincosamides
    "ermB": ("MACROLIDE", ["erythromycin", "clindamycin"]),
    "ermC": ("MACROLIDE", ["erythromycin", "clindamycin"]),
    "ermA": ("MACROLIDE", ["erythromycin", "clindamycin"]),
    "mef": ("MACROLIDE", ["erythromycin", "azithromycin"]),
    "mph": ("MACROLIDE", ["azithromycin"]),
    "lnu": ("LINCOSAMIDE", ["clindamycin"]),
    # Sulfonamides
    "sul1": ("SULFONAMIDE", ["sulfamethoxazole"]),
    "sul2": ("SULFONAMIDE", ["sulfamethoxazole"]),
    "sul3": ("SULFONAMIDE", ["sulfamethoxazole"]),
    # Trimethoprim
    "dfrA": ("DIAMINOPYRIMIDINE", ["trimethoprim"]),
    "dfrB": ("DIAMINOPYRIMIDINE", ["trimethoprim"]),
    # Aminoglycosides
    "aac": ("AMINOGLYCOSIDE", ["gentamicin", "tobramycin"]),
    "aph": ("AMINOGLYCOSIDE", ["kanamycin"]),
    "ant": ("AMINOGLYCOSIDE", ["streptomycin"]),
    "armA": ("AMINOGLYCOSIDE", ["gentamicin", "tobramycin", "amikacin"]),
    "rmtB": ("AMINOGLYCOSIDE", ["gentamicin", "tobramycin", "amikacin"]),
    # Quinolones
    "qnr": ("QUINOLONE", ["ciprofloxacin"]),
    "oqxA": ("QUINOLONE", ["ciprofloxacin"]),
    "oqxB": ("QUINOLONE", ["ciprofloxacin"]),
    # Phenicols
    "cfr": ("PHENICOL", ["linezolid", "chloramphenicol"]),
    "catA": ("PHENICOL", ["chloramphenicol"]),
    "catB": ("PHENICOL", ["chloramphenicol"]),
    "floR": ("PHENICOL", ["florfenicol", "chloramphenicol"]),
    "cmlA": ("PHENICOL", ["chloramphenicol"]),
    # Fosfomycin
    "fosA": ("FOSFOMYCIN", ["fosfomycin"]),
    "fosB": ("FOSFOMYCIN", ["fosfomycin"]),
    # Rifamycin
    "arr": ("RIFAMYCIN", ["rifampicin"]),
    # Efflux pumps (broad-spectrum, low confidence)
    "emrD": ("EFFLUX", ["nalidixic_acid"]),
    "emrE": ("EFFLUX", ["erythromycin"]),
    "emrB": ("EFFLUX", ["nalidixic_acid"]),
    "mdtK": ("EFFLUX", ["ciprofloxacin"]),
    "acrB": ("EFFLUX", ["ciprofloxacin", "tetracycline", "chloramphenicol"]),
    "mdfA": ("EFFLUX", ["chloramphenicol", "erythromycin"]),
}

# Drug class lookup for each antibiotic (derived from rules)
ANTIBIOTIC_TO_CLASS: Dict[str, str] = {}
for _pattern, (_dc, _drugs) in PHENOTYPE_RULES.items():
    for _drug in _drugs:
        if _drug not in ANTIBIOTIC_TO_CLASS:
            ANTIBIOTIC_TO_CLASS[_drug] = _dc


def predict_phenotype(sample_id: str, db) -> Dict[str, str]:
    """Predict antibiotic resistance phenotype from detected ARGs.

    Uses gene name pattern matching against PHENOTYPE_RULES to predict
    which antibiotics the sample is likely resistant to.

    If ML models have not produced predictions for this sample, saves
    rule-based results to MLPhenotypePrediction table as fallback.

    Args:
        sample_id: UUID of the sample
        db: SQLAlchemy session

    Returns:
        Dict mapping antibiotic name to predicted SIR value ("R" or "S")
    """
    logger.info(f"Predicting phenotype for sample {sample_id}")

    arg_results = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()

    # Collect resistant antibiotics and their matching genes
    resistant_antibiotics: set = set()
    antibiotic_genes: Dict[str, List[str]] = {}

    for arg in arg_results:
        gene_name = arg.gene
        for pattern, (drug_class, drugs) in PHENOTYPE_RULES.items():
            if re.search(re.escape(pattern), gene_name, re.IGNORECASE):
                resistant_antibiotics.update(drugs)
                for drug in drugs:
                    antibiotic_genes.setdefault(drug, [])
                    if gene_name not in antibiotic_genes[drug]:
                        antibiotic_genes[drug].append(gene_name)

    # Build prediction dict
    all_antibiotics: set = set()
    for _dc, drugs in PHENOTYPE_RULES.values():
        all_antibiotics.update(drugs)

    predictions: Dict[str, str] = {}
    for ab in sorted(all_antibiotics):
        predictions[ab] = "R" if ab in resistant_antibiotics else "S"

    logger.info(
        f"Phenotype prediction for sample {sample_id}: "
        f"{sum(1 for v in predictions.values() if v == 'R')} resistant, "
        f"{sum(1 for v in predictions.values() if v == 'S')} susceptible"
    )

    # Save to MLPhenotypePrediction as fallback if ML models didn't run
    existing_ml = db.query(MLPhenotypePrediction).filter(
        MLPhenotypePrediction.sample_id == sample_id
    ).first()
    if not existing_ml:
        logger.info(f"No ML predictions found, saving rule-based predictions to DB")
        for ab, sir in predictions.items():
            is_resistant = sir == "R"
            pred = MLPhenotypePrediction(
                sample_id=sample_id,
                antibiotic=ab,
                drug_class=ANTIBIOTIC_TO_CLASS.get(ab, "Unknown"),
                prediction="Resistant" if is_resistant else "Susceptible",
                probability=1.0 if is_resistant else 0.0,
                confidence="High" if is_resistant else "Moderate",
                key_genes=antibiotic_genes.get(ab, []),
                key_mutations=[],
            )
            db.add(pred)
        db.commit()

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
