from sqlalchemy.orm import Session
from app import models
from collections import defaultdict
from typing import Optional

# =========================================================
# CPS weight cache — mirrors fit_band_cache pattern in
# app/services/explanations.py.
#
# None  = not yet loaded (first call triggers a DB read)
# dict  = {factor_key: weight}, populated from cps_factor_config
#
# Falls back to hardcoded defaults if the table is empty,
# missing, or throws — scoring NEVER breaks.
# =========================================================

_HARDCODED_CPS_WEIGHTS: dict[str, float] = {
    "ses_band":        0.35,
    "education_board": 0.25,
    "support_level":   0.25,
    "resource_access": 0.15,
}

_cps_weight_cache: Optional[dict[str, float]] = None


def _load_cps_weights(db: Session) -> Optional[dict[str, float]]:
    """Read cps_factor_config from DB. Returns None on any failure."""
    try:
        rows = db.query(models.CPSFactorConfig).all()
        if rows:
            return {r.factor_key: float(r.weight) for r in rows}
    except Exception:
        pass  # table may not exist during initial migration
    return None


def clear_cps_weight_cache() -> None:
    """Called by the admin PUT /cps-factors endpoint after saving new weights."""
    global _cps_weight_cache
    _cps_weight_cache = None

def compute_skill_scores(assessment_id: int, db: Session, dataset_version: str = "v1") -> dict:
    """
    Deterministic scoring:
    Priority 1: question_student_skill_map (many-to-many question -> student skill)
    Fallback: questions.skill_id (legacy single-skill mapping)

    Note: Keeps existing API behavior; dataset_version defaults to 'v1'.
    """
    responses = db.query(models.AssessmentResponse).filter_by(assessment_id=assessment_id).all()
    skill_scores = defaultdict(float)

    for response in responses:
        # PR32: Prefer canonical integer answer_value; fallback to parsing answer (legacy rows)
        try:
            raw = response.answer_value if response.answer_value is not None else response.answer
            score = float(raw) if raw is not None else 1.0
        except Exception:
            score = 1.0

        # ✅ Priority 1: Use question_student_skill_map if present
        mappings = (
            db.query(models.QuestionStudentSkillMap)
              .filter_by(question_id=response.question_id, dataset_version=dataset_version)
              .all()
        )

        if mappings:
            for m in mappings:
                # weight is stored on mapping table
                skill_scores[m.skill_id] += score * float(m.weight)
            continue

        # ✅ Fallback: legacy single-skill mapping on questions table
        question = db.query(models.Question).get(response.question_id)
        if question:
            skill_scores[question.skill_id] += score * float(getattr(question, "weight", 1) or 1)

    return dict(skill_scores)

def assign_tiers(skill_scores: dict) -> dict:
    """
    Tiering on a 0..100 scale (aligned to scaled_0_100 and HSI outputs).

    Low:    < 40
    Medium: 40..69.999...
    High:   >= 70

    NOTE: keys are returned as strings for stable JSON output.
    """
    tiers = {}
    for skill_id, score in skill_scores.items():
        s = float(score)

        if s < 40.0:
            tiers[str(skill_id)] = "Low"
        elif s < 70.0:
            tiers[str(skill_id)] = "Medium"
        else:
            tiers[str(skill_id)] = "High"

    return tiers

def assign_tiers_scaled_0_100(skill_scores: dict) -> dict:
    """
    Tiering for scaled_0_100 (0..100).
    Low: <40, Medium: 40-69.999..., High: >=70
    """
    tiers = {}
    for skill_id, score in skill_scores.items():
        try:
            s = float(score)
        except (TypeError, ValueError):
            s = 0.0

        if s >= 70.0:
            tiers[str(skill_id)] = "High"
        elif s >= 40.0:
            tiers[str(skill_id)] = "Medium"
        else:
            tiers[str(skill_id)] = "Low"
    return tiers

    
def compute_hsi_v1(raw_skill_score: float, cps_score: float) -> float:
    """
    Hybrid Suitability Index (HSI) v1

    Rule (locked):
        FinalScore = RawSkillScore * (1 + (CPS * 0.15 / 100))

    Pure + deterministic:
      - No DB access
      - No side effects
      - Defensive on bad inputs
    """
    try:
        raw = float(raw_skill_score)
    except (TypeError, ValueError):
        raw = 0.0

    try:
        cps = float(cps_score)
    except (TypeError, ValueError):
        cps = 0.0

    # Defensive clamping (keeps replayability stable)
    if raw < 0.0:
        raw = 0.0
    if cps < 0.0:
        cps = 0.0
    if cps > 100.0:
        cps = 100.0

    multiplier = 1.0 + (cps * 0.15 / 100.0)
    return min(100.0, raw * multiplier)

def compute_skill_scores_hsi_v1(
    assessment_id: int,
    db: Session,
    dataset_version: str = "v1",
) -> dict:
    """
    HSI-upgraded scoring (v1):
      1) Compute raw skill scores using existing deterministic method
      2) Fetch CPS from context_profile (assessment_id 1:1)
      3) Apply compute_hsi_v1 per skill score

    Additive: does not change existing compute_skill_scores callers until wired.
    """
    # 1) Raw skill scores (existing logic)
    raw_scores = compute_skill_scores(
        assessment_id=assessment_id,
        db=db,
        dataset_version=dataset_version,
    )

    # 2) Fetch CPS (must exist for HSI path)
    context = (
        db.query(models.ContextProfile)
        .filter_by(assessment_id=assessment_id)
        .first()
    )

    # If CPS is missing, keep behavior safe and deterministic: treat CPS as 0
    cps_score = float(getattr(context, "cps_score", 0.0) or 0.0)

    # 3) Apply HSI per skill
    hsi_scores = {}
    for skill_id, raw in raw_scores.items():
        hsi_scores[skill_id] = compute_hsi_v1(raw, cps_score)

    return hsi_scores    
# =========================================================
# Context Profile Score (CPS) — Hybrid Model v1
# =========================================================

def compute_cps_v1(
    *,
    ses_band: str,
    education_board: str,
    support_level: str,
    resource_access: str = "unknown",
    db: Optional[Session] = None,
) -> float:
    """
    Compute Context Profile Score (CPS) on a 0–100 scale.

    Deterministic, explainable, versioned, fast.

    Weights are read from cps_factor_config (DB) on first call and cached
    in-memory for all subsequent calls. Falls back to hardcoded defaults
    if the table is empty, missing, or throws. Cache is cleared by the
    admin PUT /cps-factors endpoint via clear_cps_weight_cache().
    """
    global _cps_weight_cache

    # Populate cache on first call (or after cache clear)
    if _cps_weight_cache is None:
        if db is not None:
            loaded = _load_cps_weights(db)
            _cps_weight_cache = loaded if loaded else dict(_HARDCODED_CPS_WEIGHTS)
        else:
            _cps_weight_cache = dict(_HARDCODED_CPS_WEIGHTS)

    w = _cps_weight_cache

    # Normalize inputs (defensive)
    ses_band = (ses_band or "unknown").strip().lower()
    education_board = (education_board or "unknown").strip().lower()
    support_level = (support_level or "unknown").strip().lower()
    resource_access = (resource_access or "unknown").strip().lower()

    # --- v1 maps aligned to CURRENT stored values from UI/DB ---

    # DEFAULT POLICY: When context fields are unknown/missing, we assume
    # a low-resource rural student profile (our primary target audience).
    # This ensures the HSI fairness boost HELPS students we cannot profile
    # rather than applying a neutral mid-range adjustment.
    # Result: all-unknown CPS = 0.55*0.35 + 0.70*0.25 + 0.55*0.25 + 0.55*0.15
    #       = 0.1925 + 0.175 + 0.1375 + 0.0825 = 0.5875 → 58.75
    # (vs previous all-unknown = 69.5, which gave a weaker fairness boost)

    # SES band (practical constraints)
    ses_map = {
        "careful": 0.55,       # careful with expenses
        "some": 0.75,          # can manage some extra costs
        "not_barrier": 0.90,   # costs usually not a big barrier
        "unknown": 0.55,       # prefer not to say / default
    }

    # Education board
    board_map = {
        "state": 0.70,
        "cbse": 0.78,
        "icse": 0.82,
        "ib": 0.90,
        "cambridge": 0.90,
        "other": 0.75,
        "unknown": 0.70,
    }

    # Support level
    support_map = {
        "low": 0.55,       # mostly self-supported
        "medium": 0.75,    # some guidance
        "high": 0.95,      # strong support
        "unknown": 0.55,
    }

    # Resource access
    resource_map = {
        "limited": 0.55,
        "moderate": 0.75,
        "good": 0.90,
        "unknown": 0.55,
    }

    ses_score = ses_map.get(ses_band, ses_map["unknown"])
    board_score = board_map.get(education_board, board_map["unknown"])
    support_score = support_map.get(support_level, support_map["unknown"])
    resource_score = resource_map.get(resource_access, resource_map["unknown"])

    # --- Weighted CPS (weights from cache, fallback to hardcoded) ---
    cps_normalized = (
        (ses_score    * w.get("ses_band",        _HARDCODED_CPS_WEIGHTS["ses_band"]))
        + (board_score  * w.get("education_board", _HARDCODED_CPS_WEIGHTS["education_board"]))
        + (support_score * w.get("support_level",   _HARDCODED_CPS_WEIGHTS["support_level"]))
        + (resource_score * w.get("resource_access", _HARDCODED_CPS_WEIGHTS["resource_access"]))
    )

    return round(cps_normalized * 100, 2)