"""Outbreak cluster detection from cgMLST distances and ANI.

Identifies probable transmission clusters using species-specific
thresholds on cgMLST allelic distances and/or ANI values.
Uses single-linkage clustering: if any member of cluster A is within
threshold of any member of cluster B, the two clusters merge.
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from app.models.models import (
    Sample, SampleStatus, CgMLSTResult, ARGResult, PlasmidResult,
    Metadata, SpeciesResult, MLSTResult,
)

logger = logging.getLogger(__name__)

# Species-specific cgMLST allelic distance thresholds for cluster membership.
# Based on published epidemiological cutoffs.
_CGMLST_THRESHOLDS = {
    "escherichia coli": 10,
    "klebsiella pneumoniae": 10,
    "salmonella enterica": 7,
    "staphylococcus aureus": 24,
    "listeria monocytogenes": 7,
    "enterococcus faecium": 20,
    "acinetobacter baumannii": 10,
}
_DEFAULT_CGMLST_THRESHOLD = 10

# ANI threshold: pairs above this are considered clonal regardless of cgMLST
_ANI_CLONAL_THRESHOLD = 99.98


def _allelic_distance(profile_a: dict, profile_b: dict) -> Tuple[int, int]:
    """Compute allelic distance between two cgMLST profiles.

    Returns (distance, shared_loci).
    """
    shared = 0
    diff = 0
    for locus in profile_a:
        if locus not in profile_b:
            continue
        a_val = profile_a[locus]
        b_val = profile_b[locus]
        try:
            int(a_val)
            int(b_val)
        except (ValueError, TypeError):
            continue
        shared += 1
        if str(a_val) != str(b_val):
            diff += 1
    return diff, shared


def _single_linkage_clusters(n: int, pairs: List[Tuple[int, int]]) -> List[List[int]]:
    """Single-linkage clustering via union-find.

    Args:
        n: number of items
        pairs: list of (i, j) index pairs that are within threshold

    Returns:
        List of clusters, each cluster is a list of indices.
    """
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, j in pairs:
        union(i, j)

    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    # Only return clusters with 2+ members
    return [members for members in groups.values() if len(members) >= 2]


def detect_clusters(
    project_id: str,
    db,
    ani_matrix: Optional[List[List[float]]] = None,
    ani_sample_ids: Optional[List[str]] = None,
    cgmlst_threshold: Optional[int] = None,
) -> Dict:
    """Detect outbreak clusters in a project.

    Uses cgMLST allelic distances and/or ANI values.

    Returns:
        {
            "clusters": [
                {
                    "id": 1,
                    "samples": [{"name": ..., "sample_id": ..., "species": ..., "st": ...}],
                    "size": N,
                    "method": "cgmlst" | "ani" | "both",
                    "max_distance": int,
                    "min_distance": int,
                    "mean_distance": float,
                    "shared_args": ["gene1", ...],
                    "shared_drug_classes": ["class1", ...],
                    "shared_replicons": ["IncF", ...],
                    "date_range": {"earliest": ..., "latest": ...},
                    "locations": ["loc1", ...],
                },
                ...
            ],
            "total_samples": N,
            "clustered_samples": N,
            "threshold_used": int,
            "species": str,
        }
    """
    samples = (
        db.query(Sample)
        .filter(Sample.project_id == project_id, Sample.status == SampleStatus.complete)
        .order_by(Sample.name)
        .all()
    )
    if len(samples) < 2:
        return {"clusters": [], "total_samples": len(samples), "clustered_samples": 0,
                "threshold_used": 0, "species": None}

    sample_ids = [str(s.id) for s in samples]
    sample_names = [s.name for s in samples]
    n = len(samples)

    # Determine species (use majority species for threshold)
    species_counts = defaultdict(int)
    sample_species = {}
    for s in samples:
        sr = db.query(SpeciesResult).filter(SpeciesResult.sample_id == s.id).first()
        sp = sr.species.lower() if sr and sr.species else "unknown"
        species_counts[sp] += 1
        sample_species[str(s.id)] = sr.species if sr else None

    majority_species = max(species_counts, key=species_counts.get) if species_counts else "unknown"

    if cgmlst_threshold is None:
        cgmlst_threshold = _CGMLST_THRESHOLDS.get(majority_species, _DEFAULT_CGMLST_THRESHOLD)

    # Load cgMLST profiles
    cgmlst_profiles = {}
    for s in samples:
        cg = db.query(CgMLSTResult).filter(CgMLSTResult.sample_id == s.id).first()
        if cg and cg.allelic_profile:
            cgmlst_profiles[str(s.id)] = cg.allelic_profile

    # Load MLST STs
    sample_st = {}
    for s in samples:
        mlst = db.query(MLSTResult).filter(MLSTResult.sample_id == s.id).first()
        sample_st[str(s.id)] = mlst.sequence_type if mlst else None

    # Build ANI lookup (sample_id → index in ANI matrix)
    ani_lookup = {}
    if ani_matrix and ani_sample_ids:
        for idx, sid in enumerate(ani_sample_ids):
            ani_lookup[sid] = idx

    # Find pairs within threshold
    close_pairs = []
    pair_distances = {}  # (i,j) → distance
    pair_methods = {}    # (i,j) → method used

    for i in range(n):
        for j in range(i + 1, n):
            sid_i = sample_ids[i]
            sid_j = sample_ids[j]
            is_close = False
            method = None
            dist = None

            # Check cgMLST distance
            if sid_i in cgmlst_profiles and sid_j in cgmlst_profiles:
                d, shared = _allelic_distance(cgmlst_profiles[sid_i], cgmlst_profiles[sid_j])
                if shared >= 100 and d <= cgmlst_threshold:
                    is_close = True
                    method = "cgmlst"
                    dist = d

            # Check ANI
            if sid_i in ani_lookup and sid_j in ani_lookup:
                ai, aj = ani_lookup[sid_i], ani_lookup[sid_j]
                ani_val = ani_matrix[ai][aj]
                if ani_val >= _ANI_CLONAL_THRESHOLD:
                    if is_close:
                        method = "both"
                    else:
                        is_close = True
                        method = "ani"
                    if dist is None:
                        dist = round((100 - ani_val) * 100, 1)  # approximate distance

            if is_close:
                close_pairs.append((i, j))
                pair_distances[(i, j)] = dist
                pair_methods[(i, j)] = method

    # Cluster
    cluster_groups = _single_linkage_clusters(n, close_pairs)

    # Build cluster details
    clusters = []
    clustered_count = 0

    for idx, members in enumerate(cluster_groups, 1):
        clustered_count += len(members)
        member_sids = [sample_ids[m] for m in members]
        member_names = [sample_names[m] for m in members]

        # Pairwise distances within cluster
        dists = []
        methods_used = set()
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                key = (min(members[a], members[b]), max(members[a], members[b]))
                if key in pair_distances:
                    dists.append(pair_distances[key])
                    methods_used.add(pair_methods.get(key, "unknown"))

        # Shared ARGs
        sample_args = {}
        for sid in member_sids:
            args = db.query(ARGResult).filter(ARGResult.sample_id == sid).all()
            sample_args[sid] = {a.gene for a in args}

        shared_args = set.intersection(*sample_args.values()) if sample_args else set()

        # Shared drug classes
        sample_classes = {}
        for sid in member_sids:
            args = db.query(ARGResult).filter(ARGResult.sample_id == sid).all()
            classes = set()
            for a in args:
                if a.drug_class:
                    for c in a.drug_class.split(";")[0].split("/"):
                        c = c.strip()
                        if c:
                            classes.add(c)
            sample_classes[sid] = classes
        shared_classes = set.intersection(*sample_classes.values()) if sample_classes else set()

        # Shared plasmid replicons
        sample_replicons = {}
        for sid in member_sids:
            plasmids = db.query(PlasmidResult).filter(PlasmidResult.sample_id == sid).all()
            sample_replicons[sid] = {p.replicon for p in plasmids if p.replicon}
        shared_replicons = set.intersection(*sample_replicons.values()) if sample_replicons else set()

        # Temporal span
        dates = []
        locations = set()
        for sid in member_sids:
            meta = db.query(Metadata).filter(Metadata.sample_id == sid).first()
            if meta:
                if meta.collection_date:
                    dates.append(str(meta.collection_date))
                if meta.location:
                    locations.add(meta.location)

        date_range = None
        if dates:
            dates.sort()
            date_range = {"earliest": dates[0], "latest": dates[-1]}

        cluster_method = "both" if len(methods_used) > 1 else (methods_used.pop() if methods_used else "unknown")

        clusters.append({
            "id": idx,
            "samples": [
                {
                    "name": sample_names[m],
                    "sample_id": sample_ids[m],
                    "species": sample_species.get(sample_ids[m]),
                    "st": sample_st.get(sample_ids[m]),
                }
                for m in members
            ],
            "size": len(members),
            "method": cluster_method,
            "max_distance": max(dists) if dists else 0,
            "min_distance": min(dists) if dists else 0,
            "mean_distance": round(sum(dists) / len(dists), 1) if dists else 0,
            "shared_args": sorted(shared_args),
            "shared_drug_classes": sorted(shared_classes),
            "shared_replicons": sorted(shared_replicons),
            "date_range": date_range,
            "locations": sorted(locations),
        })

    clusters.sort(key=lambda c: c["size"], reverse=True)

    return {
        "clusters": clusters,
        "total_samples": n,
        "clustered_samples": clustered_count,
        "threshold_used": cgmlst_threshold,
        "species": majority_species,
    }
