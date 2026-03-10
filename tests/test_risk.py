"""
Risk scoring tests for RADAR.

Tests the ARG risk calculation logic including individual gene risk,
risk category classification, and composite scoring with configurable weights.
"""

import pytest


# ---------------------------------------------------------------------------
# Risk scoring functions (self-contained for testability)
# ---------------------------------------------------------------------------

# Drug classes considered critically important by WHO
CRITICAL_DRUG_CLASSES = {
    "carbapenem",
    "colistin",
    "third-generation cephalosporin",
    "fourth-generation cephalosporin",
    "glycopeptide",
    "polymyxin",
    "oxazolidinone",
}

# Mobility types ordered by transfer risk
MOBILITY_RISK = {
    "plasmid": 1.0,
    "integron": 0.85,
    "transposon": 0.7,
    "IS_element": 0.6,
    "genomic_island": 0.5,
    "chromosomal": 0.1,
    "unknown": 0.3,
}


def calculate_arg_risk(
    identity: float,
    coverage: float,
    drug_class: str,
    mobility: str,
) -> float:
    """
    Calculate the risk score for a single antibiotic resistance gene detection.

    Parameters
    ----------
    identity : float
        Percent identity of the gene match (0-100).
    coverage : float
        Percent coverage of the reference gene (0-100).
    drug_class : str
        Antibiotic drug class the gene confers resistance to.
    mobility : str
        Genomic context / mobility classification.

    Returns
    -------
    float
        Risk score between 0.0 and 1.0.
    """
    # Normalize identity and coverage to 0-1 range
    id_score = min(max(identity / 100.0, 0.0), 1.0)
    cov_score = min(max(coverage / 100.0, 0.0), 1.0)

    # Match quality component (40% weight)
    match_quality = (id_score * 0.6 + cov_score * 0.4)

    # Clinical importance component (30% weight)
    clinical_score = 1.0 if drug_class.lower() in CRITICAL_DRUG_CLASSES else 0.4

    # Mobility component (30% weight)
    mob_score = MOBILITY_RISK.get(mobility, 0.3)

    risk = (match_quality * 0.4) + (clinical_score * 0.3) + (mob_score * 0.3)

    return round(min(max(risk, 0.0), 1.0), 4)


def classify_risk(score: float) -> str:
    """
    Classify a risk score into a human-readable category.

    Parameters
    ----------
    score : float
        Risk score between 0.0 and 1.0.

    Returns
    -------
    str
        One of: "critical", "high", "medium", "low", "minimal".
    """
    if score >= 0.85:
        return "critical"
    elif score >= 0.65:
        return "high"
    elif score >= 0.45:
        return "medium"
    elif score >= 0.25:
        return "low"
    else:
        return "minimal"


def composite_risk_score(
    arg_scores: list[float],
    weights: dict[str, float] | None = None,
) -> float:
    """
    Calculate a composite risk score for a sample from multiple ARG detections.

    The composite score considers:
    - max_risk: The single highest ARG risk score.
    - mean_risk: The average of all ARG risk scores.
    - breadth: The fraction of ARGs relative to a reference maximum (capped at 1.0).

    Parameters
    ----------
    arg_scores : list[float]
        List of individual ARG risk scores.
    weights : dict[str, float], optional
        Weights for each component. Keys: "max_risk", "mean_risk", "breadth".
        Defaults to {"max_risk": 0.5, "mean_risk": 0.3, "breadth": 0.2}.

    Returns
    -------
    float
        Composite risk score between 0.0 and 1.0.
    """
    if not arg_scores:
        return 0.0

    if weights is None:
        weights = {"max_risk": 0.5, "mean_risk": 0.3, "breadth": 0.2}

    max_risk = max(arg_scores)
    mean_risk = sum(arg_scores) / len(arg_scores)
    # Breadth: number of detected ARGs normalized against a reference ceiling of 20
    breadth = min(len(arg_scores) / 20.0, 1.0)

    composite = (
        weights.get("max_risk", 0.5) * max_risk
        + weights.get("mean_risk", 0.3) * mean_risk
        + weights.get("breadth", 0.2) * breadth
    )

    return round(min(max(composite, 0.0), 1.0), 4)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCalculateArgRisk:
    """Tests for the calculate_arg_risk function."""

    def test_perfect_carbapenem_plasmid(self):
        """blaNDM-1 at 100% identity/coverage on a plasmid should score very high."""
        score = calculate_arg_risk(
            identity=100.0,
            coverage=100.0,
            drug_class="carbapenem",
            mobility="plasmid",
        )
        assert score >= 0.9
        assert score <= 1.0

    def test_perfect_colistin_plasmid(self):
        """mcr-1 at 100% identity/coverage on a plasmid should score very high."""
        score = calculate_arg_risk(
            identity=100.0,
            coverage=100.0,
            drug_class="colistin",
            mobility="plasmid",
        )
        assert score >= 0.9

    def test_chromosomal_tetracycline(self):
        """tet(A) on chromosome with non-critical drug class should score low."""
        score = calculate_arg_risk(
            identity=98.0,
            coverage=99.0,
            drug_class="tetracycline",
            mobility="chromosomal",
        )
        assert score < 0.55
        assert score > 0.2

    def test_low_identity_reduces_score(self):
        """Lower identity should reduce the risk score."""
        high_id_score = calculate_arg_risk(
            identity=100.0,
            coverage=100.0,
            drug_class="carbapenem",
            mobility="plasmid",
        )
        low_id_score = calculate_arg_risk(
            identity=70.0,
            coverage=100.0,
            drug_class="carbapenem",
            mobility="plasmid",
        )
        assert high_id_score > low_id_score

    def test_low_coverage_reduces_score(self):
        """Lower coverage should reduce the risk score."""
        full_cov = calculate_arg_risk(
            identity=100.0,
            coverage=100.0,
            drug_class="carbapenem",
            mobility="plasmid",
        )
        partial_cov = calculate_arg_risk(
            identity=100.0,
            coverage=50.0,
            drug_class="carbapenem",
            mobility="plasmid",
        )
        assert full_cov > partial_cov

    def test_mobility_ordering(self):
        """Plasmid mobility should score higher than chromosomal."""
        plasmid_score = calculate_arg_risk(
            identity=95.0,
            coverage=95.0,
            drug_class="carbapenem",
            mobility="plasmid",
        )
        chromosomal_score = calculate_arg_risk(
            identity=95.0,
            coverage=95.0,
            drug_class="carbapenem",
            mobility="chromosomal",
        )
        assert plasmid_score > chromosomal_score

    def test_integron_between_plasmid_and_chromosomal(self):
        """Integron mobility should score between plasmid and chromosomal."""
        plasmid = calculate_arg_risk(100.0, 100.0, "carbapenem", "plasmid")
        integron = calculate_arg_risk(100.0, 100.0, "carbapenem", "integron")
        chromosomal = calculate_arg_risk(100.0, 100.0, "carbapenem", "chromosomal")
        assert plasmid > integron > chromosomal

    def test_unknown_mobility_gets_default(self):
        """Unknown mobility type should use the default risk factor."""
        score = calculate_arg_risk(
            identity=100.0,
            coverage=100.0,
            drug_class="carbapenem",
            mobility="unknown",
        )
        assert 0.5 < score < 1.0

    def test_score_clamped_between_zero_and_one(self):
        """Risk score should always be between 0 and 1, even with extreme inputs."""
        score_low = calculate_arg_risk(0.0, 0.0, "tetracycline", "chromosomal")
        score_high = calculate_arg_risk(100.0, 100.0, "carbapenem", "plasmid")
        assert 0.0 <= score_low <= 1.0
        assert 0.0 <= score_high <= 1.0

    def test_non_critical_drug_class(self):
        """A non-critical drug class should score lower than a critical one, all else equal."""
        critical = calculate_arg_risk(100.0, 100.0, "carbapenem", "plasmid")
        non_critical = calculate_arg_risk(100.0, 100.0, "tetracycline", "plasmid")
        assert critical > non_critical


class TestRiskCategories:
    """Tests for the classify_risk function."""

    def test_critical_category(self):
        assert classify_risk(0.95) == "critical"
        assert classify_risk(0.85) == "critical"

    def test_high_category(self):
        assert classify_risk(0.84) == "high"
        assert classify_risk(0.65) == "high"

    def test_medium_category(self):
        assert classify_risk(0.64) == "medium"
        assert classify_risk(0.45) == "medium"

    def test_low_category(self):
        assert classify_risk(0.44) == "low"
        assert classify_risk(0.25) == "low"

    def test_minimal_category(self):
        assert classify_risk(0.24) == "minimal"
        assert classify_risk(0.0) == "minimal"

    def test_boundary_values(self):
        """Verify exact boundary values are classified correctly."""
        assert classify_risk(0.85) == "critical"
        assert classify_risk(0.65) == "high"
        assert classify_risk(0.45) == "medium"
        assert classify_risk(0.25) == "low"

    def test_perfect_score(self):
        assert classify_risk(1.0) == "critical"

    def test_zero_score(self):
        assert classify_risk(0.0) == "minimal"


class TestCompositeScoring:
    """Tests for the composite_risk_score function."""

    def test_empty_list_returns_zero(self):
        assert composite_risk_score([]) == 0.0

    def test_single_high_risk_arg(self):
        """A single high-risk ARG should produce a meaningful composite score."""
        score = composite_risk_score([0.95])
        assert score > 0.5
        assert score <= 1.0

    def test_multiple_high_risk_args(self):
        """Multiple high-risk ARGs should score higher than a single one."""
        single = composite_risk_score([0.95])
        multiple = composite_risk_score([0.95, 0.90, 0.88])
        assert multiple > single

    def test_many_low_risk_args(self):
        """Many low-risk ARGs should still produce a moderate composite score due to breadth."""
        scores = [0.3] * 15
        result = composite_risk_score(scores)
        assert result > 0.25  # Breadth component should elevate it

    def test_default_weights(self):
        """Verify the default weighting produces the expected value."""
        arg_scores = [0.9, 0.6, 0.3]
        result = composite_risk_score(arg_scores)

        max_risk = 0.9
        mean_risk = (0.9 + 0.6 + 0.3) / 3.0
        breadth = 3 / 20.0
        expected = 0.5 * max_risk + 0.3 * mean_risk + 0.2 * breadth
        expected = round(min(max(expected, 0.0), 1.0), 4)

        assert result == expected

    def test_custom_weights_max_only(self):
        """With all weight on max_risk, composite should equal the max ARG score."""
        weights = {"max_risk": 1.0, "mean_risk": 0.0, "breadth": 0.0}
        result = composite_risk_score([0.8, 0.5, 0.3], weights=weights)
        assert result == 0.8

    def test_custom_weights_mean_only(self):
        """With all weight on mean_risk, composite should equal the mean ARG score."""
        weights = {"max_risk": 0.0, "mean_risk": 1.0, "breadth": 0.0}
        arg_scores = [0.9, 0.6, 0.3]
        result = composite_risk_score(arg_scores, weights=weights)
        expected = round(sum(arg_scores) / len(arg_scores), 4)
        assert result == expected

    def test_custom_weights_breadth_only(self):
        """With all weight on breadth, composite depends on number of ARGs."""
        weights = {"max_risk": 0.0, "mean_risk": 0.0, "breadth": 1.0}
        result_few = composite_risk_score([0.5, 0.5], weights=weights)
        result_many = composite_risk_score([0.5] * 10, weights=weights)
        assert result_many > result_few

    def test_breadth_caps_at_one(self):
        """Breadth should not exceed 1.0 even with many ARGs."""
        weights = {"max_risk": 0.0, "mean_risk": 0.0, "breadth": 1.0}
        result_20 = composite_risk_score([0.5] * 20, weights=weights)
        result_40 = composite_risk_score([0.5] * 40, weights=weights)
        assert result_20 == result_40  # Both should be capped at 1.0

    def test_composite_clamped(self):
        """Composite score should always be between 0 and 1."""
        result = composite_risk_score([1.0] * 25, weights={"max_risk": 0.5, "mean_risk": 0.3, "breadth": 0.2})
        assert 0.0 <= result <= 1.0

    def test_mixed_risk_profile(self):
        """Realistic profile: one critical, one high, several low."""
        scores = [0.95, 0.70, 0.35, 0.30, 0.28]
        result = composite_risk_score(scores)
        category = classify_risk(result)
        assert category in ("high", "critical")
