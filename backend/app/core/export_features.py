"""Export sample analysis results as a wide feature matrix CSV.

Format matches vault/phenotype/data/test_inputs/ CSVs:
  Sample_ID, gene1, gene1_dg_mrna, gene1_dg_total, gene1_expression,
  gene1_promoter_dist, gene1_promoter_ldf, gene1_promoter_tf, gene1_promoter_up,
  gene1_is_count, gene1_is_min_dist, gene1_is_orientation, gene2, ...

Each ARG gene gets up to 12 feature columns:
  - presence (0/1)
  - dg_mrna, dg_total, expression (from OSTIR RBS)
  - promoter_dist, promoter_ldf, promoter_tf, promoter_up (from BPROM)
  - is_count, is_min_dist, is_orientation (from MobileElementFinder)
"""

import csv
import io
import logging
import os
import re
from typing import List, Optional

from app.models.models import (
    ARGResult, PromoterResult, RBSResult, MobilityResult, Sample
)

logger = logging.getLogger(__name__)

# Feature suffixes in column order
FEATURE_SUFFIXES = [
    "",  # presence (0/1)
    "_dg_mrna",
    "_dg_total",
    "_expression",
    "_promoter_dist",
    "_promoter_ldf",
    "_promoter_tf",
    "_promoter_up",
    "_is_count",
    "_is_min_dist",
    "_is_orientation",
]

PROXIMITY_THRESHOLD = 5000  # bp for IS element proximity


def normalize_gene_name(gene: str) -> str:
    """Normalize gene name to match the CSV column naming convention.

    e.g., aac(6')-Ib-cr5 -> aac_6'_ib_cr
          blaCTX-M-15 -> blactx_m_15
          aph(3'')-Ib -> aph_3''_ib
    """
    name = gene.lower()
    name = name.replace("(", "_").replace(")", "")
    name = name.replace("-", "_")
    # Remove trailing numbers that are variant IDs (like _5 in cr5)
    # Keep them actually, the test data has them
    return name


def export_feature_matrix(
    sample_ids: List[str],
    db,
    gene_list: Optional[List[str]] = None,
) -> str:
    """Export a wide feature matrix CSV for the given samples.

    Args:
        sample_ids: List of sample UUIDs
        db: SQLAlchemy session
        gene_list: Optional fixed list of gene column names. If None,
                   uses genes found across all samples.

    Returns:
        CSV string
    """
    # Collect all data per sample
    sample_data = {}  # sample_id -> { normalized_gene -> {features} }

    for sid in sample_ids:
        sample = db.query(Sample).filter(Sample.id == sid).first()
        if not sample:
            continue

        args = db.query(ARGResult).filter(ARGResult.sample_id == sid).all()
        mobility = db.query(MobilityResult).filter(MobilityResult.sample_id == sid).all()

        gene_features = {}
        for arg in args:
            gene_norm = normalize_gene_name(arg.gene)

            features = {
                "presence": 1.0,
                "dg_mrna": 0.0,
                "dg_total": 0.0,
                "expression": 0.0,
                "promoter_dist": 0.0,
                "promoter_ldf": 0.0,
                "promoter_tf": 0.0,
                "promoter_up": 0.0,
                "is_count": 0.0,
                "is_min_dist": 0.0,
                "is_orientation": 0.0,
            }

            # RBS data
            rbs = db.query(RBSResult).filter(RBSResult.arg_result_id == arg.id).first()
            if rbs:
                features["dg_mrna"] = rbs.dg_mrna or 0.0
                features["dg_total"] = rbs.dg_total or 0.0
                features["expression"] = rbs.expression or 0.0

            # Promoter data
            prom = db.query(PromoterResult).filter(PromoterResult.arg_result_id == arg.id).first()
            if prom:
                features["promoter_dist"] = prom.promoter_distance or 0.0
                features["promoter_ldf"] = prom.ldf_score or 0.0
                features["promoter_tf"] = prom.tf_binding_sites or 0.0
                features["promoter_up"] = prom.up_element_at_ratio or 0.0

            # IS element proximity
            if arg.contig and arg.start is not None:
                nearby_is = []
                for mob in mobility:
                    if mob.contig != arg.contig or mob.start is None or mob.end is None:
                        continue
                    if mob.start <= arg.start <= mob.end:
                        dist = 0
                    else:
                        dist = min(abs(arg.start - mob.end), abs(mob.start - arg.start))
                    if dist <= PROXIMITY_THRESHOLD:
                        nearby_is.append((dist, mob))

                features["is_count"] = float(len(nearby_is))
                if nearby_is:
                    features["is_min_dist"] = float(min(d for d, _ in nearby_is))
                    # Orientation: 1 if same strand as nearest IS, 0 otherwise
                    features["is_orientation"] = 1.0 if nearby_is else 0.0

            gene_features[gene_norm] = features

        sample_data[sid] = gene_features

    # Determine gene list
    if gene_list is None:
        all_genes = set()
        for gf in sample_data.values():
            all_genes.update(gf.keys())
        gene_list = sorted(all_genes)

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    header = ["Sample_ID"]
    for gene in gene_list:
        for suffix in FEATURE_SUFFIXES:
            header.append(gene + suffix)
    writer.writerow(header)

    # Rows
    for sid in sample_ids:
        sample = db.query(Sample).filter(Sample.id == sid).first()
        if not sample:
            continue

        gf = sample_data.get(sid, {})
        row = [sample.name]
        for gene in gene_list:
            features = gf.get(gene, None)
            if features:
                row.append(features["presence"])
                row.append(features["dg_mrna"])
                row.append(features["dg_total"])
                row.append(features["expression"])
                row.append(features["promoter_dist"])
                row.append(features["promoter_ldf"])
                row.append(features["promoter_tf"])
                row.append(features["promoter_up"])
                row.append(features["is_count"])
                row.append(features["is_min_dist"])
                row.append(features["is_orientation"])
            else:
                row.extend([0.0] * len(FEATURE_SUFFIXES))
        writer.writerow(row)

    return output.getvalue()
