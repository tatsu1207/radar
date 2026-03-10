import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.models import Sample, ARGResult, Metadata

logger = logging.getLogger(__name__)


def get_resistome_matrix(project_id: str, db: Session) -> Dict:
    """Build a samples x drug_classes presence/absence matrix.

    Args:
        project_id: UUID of the project
        db: SQLAlchemy session

    Returns:
        Dict with keys: sample_names, drug_classes, matrix (list of lists of 0/1)
    """
    samples = db.query(Sample).filter(Sample.project_id == project_id).all()

    all_drug_classes: set = set()
    sample_drug_map: Dict[str, set] = {}

    for sample in samples:
        args = db.query(ARGResult).filter(ARGResult.sample_id == sample.id).all()
        classes: set = set()
        for arg in args:
            if arg.drug_class:
                for dc in arg.drug_class.split(";"):
                    dc_clean = dc.strip().lower()
                    if dc_clean:
                        classes.add(dc_clean)
                        all_drug_classes.add(dc_clean)
        sample_drug_map[str(sample.id)] = classes

    drug_classes_sorted = sorted(all_drug_classes)
    sample_names = [s.name for s in samples]

    matrix = []
    for sample in samples:
        classes = sample_drug_map.get(str(sample.id), set())
        row = [1 if dc in classes else 0 for dc in drug_classes_sorted]
        matrix.append(row)

    return {
        "sample_names": sample_names,
        "drug_classes": drug_classes_sorted,
        "matrix": matrix,
    }


def get_temporal_data(project_id: str, db: Session) -> Dict:
    """Get time-series resistance data if collection dates are available.

    Groups samples by collection date and calculates per-drug-class
    resistance prevalence at each time point.

    Args:
        project_id: UUID of the project
        db: SQLAlchemy session

    Returns:
        Dict with time_points, drug_classes, and series data
    """
    samples = db.query(Sample).filter(Sample.project_id == project_id).all()

    # Get samples with collection dates
    dated_samples: List[Tuple] = []
    for sample in samples:
        meta = db.query(Metadata).filter(Metadata.sample_id == sample.id).first()
        if meta and meta.collection_date:
            dated_samples.append((sample, meta.collection_date))

    if not dated_samples:
        return {"time_points": [], "drug_classes": [], "series": {}}

    # Sort by date
    dated_samples.sort(key=lambda x: x[1])

    # Group by date (day granularity)
    date_groups: Dict[str, List] = defaultdict(list)
    for sample, date in dated_samples:
        date_key = date.strftime("%Y-%m-%d")
        date_groups[date_key].append(sample)

    # Get all drug classes across the project
    all_drug_classes: set = set()
    sample_classes: Dict[str, set] = {}

    for sample, _ in dated_samples:
        args = db.query(ARGResult).filter(ARGResult.sample_id == sample.id).all()
        classes: set = set()
        for arg in args:
            if arg.drug_class:
                for dc in arg.drug_class.split(";"):
                    dc_clean = dc.strip().lower()
                    if dc_clean:
                        classes.add(dc_clean)
                        all_drug_classes.add(dc_clean)
        sample_classes[str(sample.id)] = classes

    drug_classes_sorted = sorted(all_drug_classes)
    time_points = sorted(date_groups.keys())

    # Build series: for each drug class, prevalence at each time point
    series: Dict[str, List[float]] = {}
    for dc in drug_classes_sorted:
        prevalence = []
        for tp in time_points:
            samples_at_tp = date_groups[tp]
            if not samples_at_tp:
                prevalence.append(0.0)
                continue
            resistant_count = sum(
                1 for s in samples_at_tp
                if dc in sample_classes.get(str(s.id), set())
            )
            prevalence.append(round(resistant_count / len(samples_at_tp), 3))
        series[dc] = prevalence

    return {
        "time_points": time_points,
        "drug_classes": drug_classes_sorted,
        "series": series,
    }


def cluster_samples(project_id: str, db: Session) -> Dict:
    """Hierarchical clustering of samples by resistome similarity.

    Uses Jaccard distance on drug class presence/absence profiles
    and performs agglomerative hierarchical clustering.

    Args:
        project_id: UUID of the project
        db: SQLAlchemy session

    Returns:
        Dict with sample_names, dendrogram linkage matrix, and distance_matrix
    """
    resistome = get_resistome_matrix(project_id, db)
    sample_names = resistome["sample_names"]
    matrix = resistome["matrix"]

    if len(sample_names) < 2:
        return {
            "sample_names": sample_names,
            "linkage": [],
            "distance_matrix": [],
        }

    # Compute Jaccard distance matrix
    n = len(matrix)
    distance_matrix = [[0.0] * n for _ in range(n)]

    for i in range(n):
        for j in range(i + 1, n):
            # Jaccard distance = 1 - (intersection / union)
            set_i = set(k for k, v in enumerate(matrix[i]) if v > 0)
            set_j = set(k for k, v in enumerate(matrix[j]) if v > 0)

            union_size = len(set_i | set_j)
            if union_size == 0:
                dist = 0.0
            else:
                intersection_size = len(set_i & set_j)
                dist = 1.0 - (intersection_size / union_size)

            distance_matrix[i][j] = round(dist, 4)
            distance_matrix[j][i] = round(dist, 4)

    # Try to use scipy for proper hierarchical clustering
    try:
        from scipy.spatial.distance import squareform
        from scipy.cluster.hierarchy import linkage

        condensed = squareform(distance_matrix)
        linkage_matrix = linkage(condensed, method="average").tolist()
    except ImportError:
        # Fallback: simple single-linkage clustering without scipy
        logger.warning("scipy not available, using naive single-linkage clustering")
        linkage_matrix = _naive_single_linkage(distance_matrix, n)

    return {
        "sample_names": sample_names,
        "linkage": linkage_matrix,
        "distance_matrix": distance_matrix,
    }


def _naive_single_linkage(dist_matrix: List[List[float]], n: int) -> List[List[float]]:
    """Simple single-linkage clustering fallback when scipy is not available."""
    clusters = {i: [i] for i in range(n)}
    linkage_result = []
    next_id = n

    active = set(range(n))

    for step in range(n - 1):
        # Find minimum distance pair among active clusters
        min_dist = float("inf")
        merge_a, merge_b = -1, -1

        active_list = sorted(active)
        for i_idx in range(len(active_list)):
            for j_idx in range(i_idx + 1, len(active_list)):
                ci = active_list[i_idx]
                cj = active_list[j_idx]

                # Single linkage: minimum distance between any pair of points
                d = float("inf")
                for pi in clusters[ci]:
                    for pj in clusters[cj]:
                        if dist_matrix[pi][pj] < d:
                            d = dist_matrix[pi][pj]
                if d < min_dist:
                    min_dist = d
                    merge_a = ci
                    merge_b = cj

        # Merge
        new_cluster = clusters[merge_a] + clusters[merge_b]
        clusters[next_id] = new_cluster
        active.discard(merge_a)
        active.discard(merge_b)
        active.add(next_id)

        linkage_result.append([
            float(merge_a),
            float(merge_b),
            round(min_dist, 4),
            float(len(new_cluster)),
        ])
        next_id += 1

    return linkage_result
