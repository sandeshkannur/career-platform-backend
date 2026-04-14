"""
Career Feature Vector Service.

Builds and stores per-career feature vectors for similarity search.

Vectors built
-------------
keyskill_vec  : sparse {keyskill_id: normalised_weight} from career_keyskill_association
market_vec    : dense [salary_entry, salary_mid, salary_peak,
                       automation_risk_score, future_outlook_score]
                each component normalised to [0, 1] using dataset-wide min/max
tfidf_vec     : TF-IDF vector (dict of term → score) over title + description text
aq_vec        : optional; from promoted CareerAQWeight rows (aq_01…aq_25 ordered)
student_vec   : NOT computed here (would require assessment data joins — skipped
                in this phase, stored as null)

Clustering
----------
k-means (sklearn) on concatenation of keyskill_vec + market_vec + tfidf_vec.
k defaults to min(8, n_careers // 3) with a floor of 2.
archetype_id  = cluster index (0-based integer)
archetype_label = "Cluster-{archetype_id}" (placeholder — admins can relabel later)
centrality_score = cosine similarity between this career vector and its cluster centroid

Public API
----------
recompute_all_vectors(db)             → summary dict
get_career_neighbours(db, career_id, top_n=5) → list of {career_id, title, similarity}
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    Career,
    CareerAQWeight,
    CareerFeatureVector,
    career_keyskill_association,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
AQ_KEYS: List[str] = [f"aq_{i:02d}" for i in range(1, 26)]  # aq_01 … aq_25
KMEANS_RANDOM_STATE: int = 42

# Ordinal encoding for string fields
_AUTOMATION_RISK_MAP: Dict[str, float] = {
    "low": 0.0, "medium": 0.5, "high": 1.0,
}
_FUTURE_OUTLOOK_MAP: Dict[str, float] = {
    "declining": 0.0, "stable": 0.33, "growing": 0.67, "high_growth": 1.0,
}


# ── Helpers ────────────────────────────────────────────────────────────────

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D arrays. Returns 0.0 if either is zero."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _minmax_normalise(values: List[float]) -> List[float]:
    """Min-max normalise a list. Returns zeros if all values are identical."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


# ── Key-skill vector ───────────────────────────────────────────────────────

def _build_keyskill_vecs(
    db: Session,
    career_ids: List[int],
    all_ks_ids: List[int],
) -> Dict[int, np.ndarray]:
    """
    Build a dense keyskill vector for each career.

    The vector has length = len(all_ks_ids), where each position holds the
    normalised weight_percentage for that key skill (0 if not mapped).
    """
    ks_index = {ks_id: i for i, ks_id in enumerate(all_ks_ids)}
    dim = len(all_ks_ids)

    rows = db.execute(
        text(
            "SELECT career_id, keyskill_id, weight_percentage "
            "FROM career_keyskill_association "
            "WHERE career_id = ANY(:ids)"
        ),
        {"ids": career_ids},
    ).mappings().all()

    vecs: Dict[int, np.ndarray] = {cid: np.zeros(dim, dtype=float) for cid in career_ids}
    for row in rows:
        cid = row["career_id"]
        idx = ks_index.get(row["keyskill_id"])
        if idx is not None:
            vecs[cid][idx] = _safe_float(row["weight_percentage"])

    # L2-normalise each vector
    for cid in vecs:
        norm = np.linalg.norm(vecs[cid])
        if norm > 0:
            vecs[cid] = vecs[cid] / norm

    return vecs


# ── Market vector ──────────────────────────────────────────────────────────

def _build_market_vecs(careers: List[Career]) -> Dict[int, np.ndarray]:
    """
    5-component market signal vector per career:
      [salary_entry, salary_mid, salary_peak, automation_risk, future_outlook]
    Each component is min-max normalised across the dataset.
    """
    raw: Dict[int, List[float]] = {}
    for c in careers:
        raw[c.id] = [
            _safe_float(c.salary_entry_inr),
            _safe_float(c.salary_mid_inr),
            _safe_float(c.salary_peak_inr),
            _AUTOMATION_RISK_MAP.get((c.automation_risk or "").lower(), 0.5),
            _FUTURE_OUTLOOK_MAP.get((c.future_outlook or "").lower(), 0.5),
        ]

    # Normalise each component across all careers
    n = len(raw)
    if n == 0:
        return {}

    # Transpose: component_values[i] = list of component i across all careers
    ids = list(raw.keys())
    component_matrix = [[raw[cid][j] for cid in ids] for j in range(5)]
    normalised_components = [_minmax_normalise(col) for col in component_matrix]

    vecs: Dict[int, np.ndarray] = {}
    for k, cid in enumerate(ids):
        vec = np.array([normalised_components[j][k] for j in range(5)], dtype=float)
        vecs[cid] = vec

    return vecs


# ── TF-IDF vector ──────────────────────────────────────────────────────────

def _build_tfidf_vecs(careers: List[Career]) -> Tuple[Dict[int, np.ndarray], List[str]]:
    """
    TF-IDF vectors over concatenated title + description text.

    Returns (vecs_dict, feature_names).
    """
    ids = [c.id for c in careers]
    docs = [
        f"{c.title or ''} {c.description or ''}".strip() or "unknown"
        for c in careers
    ]

    vectorizer = TfidfVectorizer(
        max_features=200,
        sublinear_tf=True,
        stop_words="english",
        min_df=1,
    )
    matrix = vectorizer.fit_transform(docs)  # shape (n_careers, n_features)
    feature_names: List[str] = vectorizer.get_feature_names_out().tolist()

    vecs: Dict[int, np.ndarray] = {}
    for i, cid in enumerate(ids):
        vecs[cid] = matrix[i].toarray().flatten()

    return vecs, feature_names


# ── AQ vector ─────────────────────────────────────────────────────────────

def _build_aq_vecs(db: Session, career_ids: List[int]) -> Dict[int, Optional[np.ndarray]]:
    """
    Build a 25-component AQ vector from promoted CareerAQWeight rows.
    Returns None for careers without promoted AQ weights.
    """
    rows = (
        db.query(CareerAQWeight)
        .filter(
            CareerAQWeight.career_id.in_(career_ids),
            CareerAQWeight.is_promoted.is_(True),
        )
        .all()
    )

    # Group by career_id
    by_career: Dict[int, Dict[str, float]] = {}
    for row in rows:
        by_career.setdefault(row.career_id, {})[row.aq_code] = _safe_float(row.final_weight)

    vecs: Dict[int, Optional[np.ndarray]] = {}
    for cid in career_ids:
        aq_map = by_career.get(cid)
        if not aq_map:
            vecs[cid] = None
            continue
        # ordered aq_01 … aq_25
        vec = np.array(
            [aq_map.get(k, 0.0) for k in AQ_KEYS],
            dtype=float,
        )
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        vecs[cid] = vec

    return vecs


# ── Clustering ─────────────────────────────────────────────────────────────

def _cluster_careers(
    combined_vecs: Dict[int, np.ndarray],
    n_clusters: int,
) -> Tuple[Dict[int, int], np.ndarray]:
    """
    Run k-means on combined vectors.

    Returns (labels_dict, centroids).
    """
    ids = list(combined_vecs.keys())
    matrix = np.vstack([combined_vecs[cid] for cid in ids])

    km = KMeans(n_clusters=n_clusters, random_state=KMEANS_RANDOM_STATE, n_init="auto")
    km.fit(matrix)

    labels = {cid: int(km.labels_[i]) for i, cid in enumerate(ids)}
    return labels, km.cluster_centers_


# ── Public API ─────────────────────────────────────────────────────────────

def recompute_all_vectors(db: Session) -> Dict[str, Any]:
    """
    Recompute feature vectors for all active careers and upsert them into
    career_feature_vectors.

    Returns a summary dict:
    {
        "careers_processed": int,
        "careers_skipped":   int,
        "archetypes":        int,
        "computed_at":       str (ISO 8601),
    }
    """
    careers: List[Career] = (
        db.query(Career).filter(Career.is_active.is_(True)).all()
    )
    if not careers:
        return {
            "careers_processed": 0,
            "careers_skipped": 0,
            "archetypes": 0,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    career_ids = [c.id for c in careers]

    # ── Collect all keyskill IDs used across these careers ─────────────────
    ks_rows = db.execute(
        text("SELECT DISTINCT keyskill_id FROM career_keyskill_association WHERE career_id = ANY(:ids)"),
        {"ids": career_ids},
    ).mappings().all()
    all_ks_ids = sorted({r["keyskill_id"] for r in ks_rows})

    # ── Build per-component vectors ────────────────────────────────────────
    if all_ks_ids:
        ks_vecs = _build_keyskill_vecs(db, career_ids, all_ks_ids)
    else:
        ks_vecs = {cid: np.zeros(1, dtype=float) for cid in career_ids}

    mkt_vecs = _build_market_vecs(careers)
    tfidf_vecs, _tfidf_terms = _build_tfidf_vecs(careers)
    aq_vecs = _build_aq_vecs(db, career_ids)

    # ── Concatenate for clustering ─────────────────────────────────────────
    combined: Dict[int, np.ndarray] = {}
    for cid in career_ids:
        combined[cid] = np.concatenate([
            ks_vecs.get(cid, np.zeros(len(all_ks_ids) or 1)),
            mkt_vecs.get(cid, np.zeros(5)),
            tfidf_vecs.get(cid, np.zeros(1)),
        ])

    # ── Cluster ────────────────────────────────────────────────────────────
    n_clusters = max(2, min(8, len(careers) // 3))
    if len(careers) < 2:
        n_clusters = 1
        cluster_labels = {cid: 0 for cid in career_ids}
        centroids = np.vstack([combined[career_ids[0]]])
    else:
        cluster_labels, centroids = _cluster_careers(combined, n_clusters)

    # ── Upsert rows ────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    processed = 0
    skipped = 0
    for career in careers:
        cid = career.id
        try:
            ks_vec = ks_vecs.get(cid, np.zeros(len(all_ks_ids) or 1))
            mkt_vec = mkt_vecs.get(cid, np.zeros(5))
            tf_vec = tfidf_vecs.get(cid, np.zeros(1))
            aq_vec_arr: Optional[np.ndarray] = aq_vecs.get(cid)

            arch_id = cluster_labels.get(cid, 0)
            centroid = centroids[arch_id]
            combined_vec = combined[cid]
            centrality = _cosine_similarity(combined_vec, centroid)

            existing: Optional[CareerFeatureVector] = (
                db.query(CareerFeatureVector)
                .filter(CareerFeatureVector.career_id == cid)
                .first()
            )

            row_kwargs = dict(
                keyskill_vec     = ks_vec.tolist(),
                market_vec       = mkt_vec.tolist(),
                tfidf_vec        = tf_vec.tolist(),
                aq_vec           = aq_vec_arr.tolist() if aq_vec_arr is not None else None,
                student_vec      = None,
                archetype_id     = arch_id,
                archetype_label  = f"Cluster-{arch_id}",
                centrality_score = round(centrality, 6),
                computed_at      = now,
            )

            if existing:
                for k, v in row_kwargs.items():
                    setattr(existing, k, v)
            else:
                db.add(CareerFeatureVector(career_id=cid, **row_kwargs))

            processed += 1
        except Exception as exc:
            logger.warning("Vector recompute skipped career_id=%s: %s", cid, exc)
            skipped += 1

    db.commit()
    logger.info("Vector recompute complete: processed=%s skipped=%s", processed, skipped)

    return {
        "careers_processed": processed,
        "careers_skipped": skipped,
        "archetypes": n_clusters,
        "computed_at": now.isoformat(),
    }


def get_career_neighbours(
    db: Session,
    career_id: int,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """
    Return the top_n most similar careers to career_id based on cosine
    similarity of their concatenated (keyskill + market + tfidf) vectors.

    Returns
    -------
    List of dicts, sorted by similarity descending:
    [
        {"career_id": int, "title": str, "similarity": float},
        ...
    ]

    Raises
    ------
    ValueError  if career_id has no stored feature vector.
    """
    target: Optional[CareerFeatureVector] = (
        db.query(CareerFeatureVector)
        .filter(CareerFeatureVector.career_id == career_id)
        .first()
    )
    if target is None:
        raise ValueError(
            f"No feature vector found for career_id={career_id}. "
            "Run POST /admin/careers/recompute-vectors first."
        )

    all_rows: List[CareerFeatureVector] = (
        db.query(CareerFeatureVector)
        .filter(CareerFeatureVector.career_id != career_id)
        .all()
    )

    # Reconstruct target vector
    target_vec = np.concatenate([
        np.array(target.keyskill_vec, dtype=float),
        np.array(target.market_vec, dtype=float),
        np.array(target.tfidf_vec, dtype=float),
    ])

    # Build (career_id, similarity) pairs
    similarities: List[Tuple[int, float]] = []
    for row in all_rows:
        try:
            candidate_vec = np.concatenate([
                np.array(row.keyskill_vec, dtype=float),
                np.array(row.market_vec, dtype=float),
                np.array(row.tfidf_vec, dtype=float),
            ])
            # Vectors may differ in dim if recomputed at different times — pad shorter
            len_t, len_c = len(target_vec), len(candidate_vec)
            if len_t != len_c:
                pad = abs(len_t - len_c)
                if len_t < len_c:
                    target_vec = np.pad(target_vec, (0, pad))
                else:
                    candidate_vec = np.pad(candidate_vec, (0, pad))
            sim = _cosine_similarity(target_vec, candidate_vec)
            similarities.append((row.career_id, sim))
        except Exception as exc:
            logger.debug("Skipping neighbour career_id=%s: %s", row.career_id, exc)

    # Sort and take top_n
    similarities.sort(key=lambda x: x[1], reverse=True)
    top = similarities[:top_n]

    # Fetch titles
    if not top:
        return []

    top_ids = [cid for cid, _ in top]
    careers: List[Career] = (
        db.query(Career).filter(Career.id.in_(top_ids)).all()
    )
    title_map = {c.id: c.title for c in careers}

    return [
        {
            "career_id": cid,
            "title": title_map.get(cid, "Unknown"),
            "similarity": round(sim, 6),
        }
        for cid, sim in top
    ]
