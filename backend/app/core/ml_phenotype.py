"""ML-based phenotype prediction using pre-trained Random Forest models.

Extracts features from RADAR's existing annotation results (ARGResult,
PromoterResult, RBSResult, MLSTResult, SpeciesResult) and predicts
per-antibiotic resistance phenotype using models trained in the AMR project.

Supported species: Salmonella enterica, Escherichia coli,
Klebsiella pneumoniae, Staphylococcus aureus, Acinetobacter baumannii.
"""
import json
import logging
import os
from collections import defaultdict
from typing import Dict, List, Optional

import joblib
import numpy as np

from app.config import settings
from app.models.models import (
    ARGResult, MLPhenotypePrediction, MLSTResult, PromoterResult,
    RBSResult, SpeciesResult,
)

logger = logging.getLogger(__name__)

# Path to pre-trained models
# Probe order: env var > repo/models > ../AMR/models (dev) > /opt/ml_models (Docker)
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
_repo_models = os.path.join(_repo_root, "models")
_dev_fallback = os.path.join(_repo_root, "..", "AMR", "models")
_default_models = (
    _repo_models if os.path.isdir(_repo_models)
    else _dev_fallback if os.path.isdir(_dev_fallback)
    else "/opt/ml_models"
)
MODELS_DIR = os.environ.get("RADAR_ML_MODELS_DIR", _default_models)

MLST_SCHEME_TO_SPECIES = {
    "senterica": "Salmonella_enterica",
    "ecoli": "Escherichia_coli",
    "ecoli_achtman_4": "Escherichia_coli",
    "klebsiella": "Klebsiella_pneumoniae",
    "kpneumoniae": "Klebsiella_pneumoniae",
    "saureus": "Staphylococcus_aureus",
    "abaumannii": "Acinetobacter_baumannii",
    "abaumannii_2": "Acinetobacter_baumannii",
}

SPECIES_NAME_TO_DIR = {
    "salmonella enterica": "Salmonella_enterica",
    "salmonella": "Salmonella_enterica",
    "escherichia coli": "Escherichia_coli",
    "e. coli": "Escherichia_coli",
    "klebsiella pneumoniae": "Klebsiella_pneumoniae",
    "klebsiella": "Klebsiella_pneumoniae",
    "staphylococcus aureus": "Staphylococcus_aureus",
    "acinetobacter baumannii": "Acinetobacter_baumannii",
}

SPECIES_DISPLAY = {
    "Salmonella_enterica": "Salmonella enterica",
    "Escherichia_coli": "Escherichia coli",
    "Klebsiella_pneumoniae": "Klebsiella pneumoniae",
    "Staphylococcus_aureus": "Staphylococcus aureus",
    "Acinetobacter_baumannii": "Acinetobacter baumannii",
}

# Global model cache
_models: Dict[str, Dict] = {}


def _load_models():
    """Load all pre-trained models from disk (called once)."""
    global _models
    if _models:
        return

    if not os.path.isdir(MODELS_DIR):
        logger.warning(f"ML models directory not found: {MODELS_DIR}")
        return

    for species_dir in os.listdir(MODELS_DIR):
        sp_path = os.path.join(MODELS_DIR, species_dir)
        if not os.path.isdir(sp_path) or species_dir.startswith("_"):
            continue

        _models[species_dir] = {}
        for fname in os.listdir(sp_path):
            if not fname.endswith("_rf.joblib"):
                continue
            abx = fname.replace("_rf.joblib", "")
            meta_path = os.path.join(sp_path, f"{abx}_meta.json")
            try:
                model = joblib.load(os.path.join(sp_path, fname))
                meta = {}
                if os.path.exists(meta_path):
                    with open(meta_path) as f:
                        meta = json.load(f)
                _models[species_dir][abx] = {"model": model, "meta": meta}
            except Exception as e:
                logger.warning(f"Failed to load model {species_dir}/{abx}: {e}")

    total = sum(len(v) for v in _models.values())
    logger.info(f"Loaded {total} ML phenotype models across {len(_models)} species")


def _resolve_species(sample_id: str, db) -> Optional[str]:
    """Determine species directory name from MLST scheme or species ID."""
    # Try MLST scheme first (most reliable for model matching)
    mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
    if mlst and mlst.scheme:
        species = MLST_SCHEME_TO_SPECIES.get(mlst.scheme.lower())
        if species:
            return species

    # Fall back to species identification
    sp = db.query(SpeciesResult).filter(SpeciesResult.sample_id == sample_id).first()
    if sp and sp.species:
        sp_lower = sp.species.lower()
        for pattern, species_dir in SPECIES_NAME_TO_DIR.items():
            if pattern in sp_lower:
                return species_dir

    return None


def _extract_features_for_antibiotic(sample_id: str, antibiotic: str, drug_class: str, all_args, db) -> dict:
    """Extract ML features for a specific antibiotic.

    Target features (target_*) are computed only from ARGs that confer resistance
    to this specific antibiotic (using substrate mapping for beta-lactams, etc.).
    Genome features (genome_*, n_amr_genes, point mutations) are global.
    """
    from app.core.substrate_mapping import gene_confers_resistance

    features = {}

    # Filter target ARGs: must match antibiotic's drug class AND pass substrate check
    # Exclude intrinsic/housekeeping: EFFLUX, STRESS, NA, ACID, ARSENIC, METAL
    INTRINSIC_CLASSES = {"EFFLUX", "STRESS", "NA", "ACID", "ARSENIC", "ARSENATE", "METAL"}
    target_args = []
    for a in all_args:
        if not a.drug_class:
            continue
        gene_classes = {c.strip().upper() for c in (a.drug_class or "").split(";")}
        # Skip intrinsic/housekeeping genes
        if gene_classes.issubset(INTRINSIC_CLASSES):
            continue
        # Gene's drug class must match the antibiotic's drug class
        if drug_class.upper() not in gene_classes:
            continue
        # For beta-lactams/aminoglycosides, use substrate-specific mapping
        if not gene_confers_resistance(a.gene or "", antibiotic, drug_class):
            continue
        target_args.append(a)

    features["n_amr_genes"] = len(all_args)
    features["has_target_arg"] = 1 if target_args else 0
    features["n_target_args"] = len(target_args)

    # Helper for aggregate stats
    def _agg(vals, prefix):
        if not vals:
            return
        features[f"{prefix}_max"] = max(vals)
        features[f"{prefix}_mean"] = sum(vals) / len(vals)
        features[f"{prefix}_min"] = min(vals)

    # Target-level features: only from drug-class-matching ARGs
    if target_args:
        _agg([a.identity for a in target_args if a.identity is not None], "target_identity")
        _agg([a.coverage for a in target_args if a.coverage is not None], "target_coverage")
        _agg([a.cai for a in target_args if a.cai is not None], "target_cai")
        _agg([a.rare_codon_pct for a in target_args if a.rare_codon_pct is not None], "target_rare_codon_pct")
        _agg([float(a.rare_codon_clusters) for a in target_args if a.rare_codon_clusters is not None], "target_rare_codon_clusters")
        _agg([a.gene_gc for a in target_args if a.gene_gc is not None], "target_gene_gc")

        gc_dev_vals = [a.gc_deviation for a in target_args if a.gc_deviation is not None]
        if gc_dev_vals:
            features["target_gc_deviation_max"] = max(gc_dev_vals, key=abs)
            features["target_gc_deviation_mean"] = sum(gc_dev_vals) / len(gc_dev_vals)

        copies_vals = [a.gene_copies for a in target_args if a.gene_copies is not None]
        if copies_vals:
            features["target_gene_copies_max"] = max(copies_vals)
            features["target_gene_copies_mean"] = sum(copies_vals) / len(copies_vals)

        # Promoter features from target ARGs only
        ldf_vals, tf_vals, dist_vals, at_vals = [], [], [], []
        for a in target_args:
            pr = db.query(PromoterResult).filter(PromoterResult.arg_result_id == a.id).first()
            if not pr:
                continue
            if pr.ldf_score is not None: ldf_vals.append(pr.ldf_score)
            if pr.tf_binding_sites is not None: tf_vals.append(float(pr.tf_binding_sites))
            if pr.promoter_distance is not None: dist_vals.append(float(pr.promoter_distance))
            if pr.up_element_at_ratio is not None: at_vals.append(pr.up_element_at_ratio)
        _agg(ldf_vals, "target_promoter_ldf")
        _agg(tf_vals, "target_promoter_tf_sites")
        _agg(dist_vals, "target_promoter_distance")
        _agg(at_vals, "target_promoter_up_at_ratio")

        # RBS features from target ARGs only
        rbs_expr, rbs_dg, rbs_mrna = [], [], []
        for a in target_args:
            rbs = db.query(RBSResult).filter(RBSResult.arg_result_id == a.id).first()
            if not rbs:
                continue
            if rbs.expression is not None: rbs_expr.append(rbs.expression)
            if rbs.dg_total is not None: rbs_dg.append(rbs.dg_total)
            if rbs.dg_mrna is not None: rbs_mrna.append(rbs.dg_mrna)
        _agg(rbs_expr, "target_rbs_expression")
        _agg(rbs_dg, "target_rbs_dg_total")
        _agg(rbs_mrna, "target_rbs_dg_mrna")

        # Functionality flags — target ARGs only
        features["arg_low_rbs"] = 1 if rbs_expr and any(v < 1.0 for v in rbs_expr) else 0
        features["arg_low_promoter"] = 1 if not ldf_vals else 0
        features["arg_truncated"] = 1 if any(a.coverage is not None and a.coverage < 80.0 for a in target_args) else 0
        features["arg_poor_adaptation"] = 1 if any(a.cai is not None and a.cai < 0.2 for a in target_args) else 0

        # Functional score — target ARGs only
        scores = []
        for a in target_args:
            s = 0.25
            pr = db.query(PromoterResult).filter(PromoterResult.arg_result_id == a.id).first()
            rbs = db.query(RBSResult).filter(RBSResult.arg_result_id == a.id).first()
            if pr and pr.ldf_score is not None and pr.ldf_score > 2.0: s += 0.25
            if rbs and rbs.expression is not None and rbs.expression > 1.0: s += 0.25
            if a.cai is not None and a.cai > 0.3: s += 0.15
            if a.coverage is not None and a.coverage >= 95.0: s += 0.10
            scores.append(s)
        features["arg_functional_score"] = max(scores) if scores else 0.0

        # Plasmid features — target ARGs
        n_plasmid = sum(1 for a in target_args if a.on_plasmid)
        features["target_any_on_plasmid"] = 1 if n_plasmid > 0 else 0
        features["target_n_plasmid"] = n_plasmid
    else:
        # No target ARGs — set zero/absent flags
        features["arg_low_rbs"] = 0
        features["arg_low_promoter"] = 0
        features["arg_truncated"] = 0
        features["arg_poor_adaptation"] = 0
        features["arg_functional_score"] = 0.0
        features["target_any_on_plasmid"] = 0
        features["target_n_plasmid"] = 0

    # Genome-level features (always global)
    all_copies = [a.gene_copies for a in all_args if a.gene_copies is not None]
    if all_copies:
        features["genome_gene_copies_sum"] = sum(all_copies)
        features["genome_gene_copies_max"] = max(all_copies)

    for a in all_args:
        if a.genome_gc is not None:
            features["genome_gc"] = a.genome_gc
            break

    # Point mutation features (global)
    all_mutations = []
    for a in all_args:
        if a.point_mutations:
            all_mutations.extend(a.point_mutations.split("; "))

    features["target_has_point_mutation"] = 1 if all_mutations else 0
    features["genome_has_point_mutation"] = 1 if all_mutations else 0
    features["pf_n_mutations"] = len(all_mutations)
    features["pf_has_gyrA"] = 1 if any("gyra" in m.lower() for m in all_mutations) else 0
    features["pf_has_parC"] = 1 if any("parc" in m.lower() for m in all_mutations) else 0
    features["pf_has_parE"] = 1 if any("pare" in m.lower() for m in all_mutations) else 0
    features["pf_has_gyrB"] = 1 if any("gyrb" in m.lower() for m in all_mutations) else 0
    features["pf_has_ampC_promoter"] = 1 if any("ampc" in m.lower() for m in all_mutations) else 0

    quinolone_muts = [m for m in all_mutations if "gyr" in m.lower() or "par" in m.lower()]
    features["pf_has_quinolone_mutation"] = 1 if quinolone_muts else 0
    features["pf_n_quinolone_mutations"] = len(quinolone_muts)
    features["pf_has_gyrA_Ser83Leu"] = 1 if any("s83l" in m.lower() for m in all_mutations) else 0

    # MLST
    mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
    features["mlst_st"] = mlst.sequence_type if mlst and mlst.sequence_type else "unknown"

    return features


def _build_amr_results(args: List[ARGResult]) -> dict:
    """Build AMR results dict for key gene/mutation identification."""
    results = {"all_genes": [], "genes_by_class": defaultdict(list), "mutations": []}
    for a in args:
        results["all_genes"].append({
            "gene": a.gene,
            "drug_class": a.drug_class or "",
            "identity": a.identity or 0,
            "coverage": a.coverage or 0,
            "on_plasmid": a.on_plasmid or False,
        })
        dc = a.drug_class or ""
        if a.gene not in results["genes_by_class"][dc]:
            results["genes_by_class"][dc].append(a.gene)
        if a.point_mutations:
            results["mutations"].extend(a.point_mutations.split("; "))
    return results


def run_ml_phenotype(sample_id: str, db) -> List[MLPhenotypePrediction]:
    """Run ML phenotype prediction for a sample.

    Returns list of MLPhenotypePrediction records created.
    """
    _load_models()

    if not _models:
        logger.warning("No ML models loaded, skipping phenotype prediction")
        return []

    # Resolve species
    species = _resolve_species(sample_id, db)
    if not species or species not in _models:
        logger.info(f"No ML models for species of sample {sample_id} (species={species})")
        return []

    logger.info(f"Running ML phenotype prediction for sample {sample_id} (species={species})")

    # Load all ARGs once (reused per antibiotic)
    args = db.query(ARGResult).filter(ARGResult.sample_id == sample_id).all()
    amr_results = _build_amr_results(args)

    mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == sample_id).first()
    mlst_st = mlst.sequence_type if mlst and mlst.sequence_type else "unknown"

    # Run all predictions first, then persist atomically
    species_models = _models[species]
    predictions = []

    for abx, model_data in sorted(species_models.items()):
        model = model_data["model"]
        meta = model_data["meta"]
        feature_cols = meta.get("feature_columns", [])
        medians = meta.get("median_values", {})
        drug_class = meta.get("drug_class", "Unknown")

        # Extract features specific to this antibiotic
        feature_data = _extract_features_for_antibiotic(sample_id, abx, drug_class, args, db)

        # Build feature vector
        X = np.array([feature_data.get(col, medians.get(col, 0.0)) for col in feature_cols])
        X = np.nan_to_num(X, nan=0.0).reshape(1, -1)

        # Predict
        pred_proba = model.predict_proba(X)[0]
        resistant_idx = list(model.classes_).index(1) if 1 in model.classes_ else -1
        prob_resistant = pred_proba[resistant_idx] if resistant_idx >= 0 else pred_proba[-1]
        is_resistant = prob_resistant >= 0.5

        # Confidence
        pred_confidence = prob_resistant if is_resistant else (1.0 - prob_resistant)
        if pred_confidence > 0.85:
            confidence = "High"
        elif pred_confidence > 0.7:
            confidence = "Moderate"
        else:
            confidence = "Low"

        # Key determinants
        key_genes = []
        key_mutations = []
        importances = dict(zip(feature_cols, model.feature_importances_))
        class_genes = amr_results["genes_by_class"].get(drug_class, [])

        for gene in class_genes:
            gene_lower = gene.lower()
            relevant = any(
                gene_lower in col.lower() and importances.get(col, 0) > 0.01
                for col in feature_cols
            )
            if relevant:
                key_genes.append(gene)
            if len(key_genes) >= 3:
                break

        if not key_genes and is_resistant:
            key_genes = class_genes[:3]

        if "QUINOLONE" in drug_class.upper():
            key_mutations = [m for m in amr_results["mutations"]
                            if "gyr" in m.lower() or "par" in m.lower()]
        else:
            key_mutations = []

        predictions.append({
            "antibiotic": abx,
            "drug_class": drug_class,
            "prediction": "Resistant" if is_resistant else "Susceptible",
            "probability": round(float(prob_resistant), 3),
            "confidence": confidence,
            "key_genes": key_genes,
            "key_mutations": key_mutations,
        })

    # Persist atomically: delete old + insert new in one commit
    db.query(MLPhenotypePrediction).filter(
        MLPhenotypePrediction.sample_id == sample_id
    ).delete()
    db_preds = []
    for p in predictions:
        pred = MLPhenotypePrediction(sample_id=sample_id, **p)
        db.add(pred)
        db_preds.append(pred)
    db.commit()

    n_r = sum(1 for p in predictions if p["prediction"] == "Resistant")
    logger.info(
        f"ML phenotype prediction for {sample_id}: "
        f"{len(predictions)} antibiotics, {n_r} resistant"
    )
    return db_preds
