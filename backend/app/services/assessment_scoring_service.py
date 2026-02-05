from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

SCORING_CONFIG_VERSION = "v1"


class EmptyResponsesError(Exception):
    """Raised when an assessment has no persisted responses."""
    pass


class MissingQSSWError(Exception):
    """Raised when one or more question_ids have no QSSW mapping."""
    def __init__(self, assessment_id: int, missing_question_ids: List[int]):
        self.assessment_id = assessment_id
        self.missing_question_ids = missing_question_ids
        super().__init__(
            f"Missing QSSW mapping for assessment_id={assessment_id}, "
            f"question_ids={missing_question_ids}"
        )


# Canonical beta scale (PR32 enforces this in routers already)
ANSWER_MIN = 1
ANSWER_MAX = 5

# Deterministic rounding for persisted floats (avoid drift across runs)
_Q = Decimal("0.000001")


def _to_decimal(x) -> Decimal:
    # robust conversion for numeric/Decimal/str
    return Decimal(str(x))


def compute_and_persist_skill_scores(
    db: Session,
    assessment_id: int,
    student_id: int,
    scoring_config_version: str = SCORING_CONFIG_VERSION,
) -> dict:
    """
    PR37.1: Deterministic Scoring Engine (Question -> Student Skill) using QSSW.

    IMPORTANT COMPATIBILITY GUARANTEE:
    - avg_raw remains on the 1..5-ish scale so existing tiering thresholds keep working.
    - We assume QSSW weights per question are normalized (sum ~= 1.0), which preserves:
        sum(contributions for a question) == answer_value
      This matches your PR requirement: "Sum of normalized contributions per question respected".
    """

    # ---------------------------------------------------------
    # 1) Load persisted responses (prefer answer_value; fallback to parsing answer)
    # ---------------------------------------------------------
    rows = db.execute(
        select(
            models.AssessmentResponse.question_id,
            models.AssessmentResponse.answer_value,
            models.AssessmentResponse.answer,
        ).where(models.AssessmentResponse.assessment_id == assessment_id)
    ).all()

    if not rows:
        raise EmptyResponsesError("No responses found for this assessment.")

    normalized_responses: List[Tuple[int, int]] = []  # [(question_id:int, answer_value:int)]
    qids: List[int] = []

    for raw_qid, ans_val, ans_str in rows:
        try:
            qid = int(raw_qid)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid question_id (must be int-like): {raw_qid!r}")

        # Prefer canonical integer (PR32). Fallback keeps backward compatibility.
        if ans_val is None:
            try:
                ans_val = int(str(ans_str).strip())
            except Exception:
                raise ValueError(f"Non-numeric answer for question_id={qid}: {ans_str!r}")

        if ans_val < ANSWER_MIN or ans_val > ANSWER_MAX:
            raise ValueError(
                f"Answer out of range ({ANSWER_MIN}-{ANSWER_MAX}) for question_id={qid}: {ans_val}"
            )

        qids.append(qid)
        normalized_responses.append((qid, int(ans_val)))

    unique_qids = sorted(set(qids))

    # ---------------------------------------------------------
    # 2) Load QSSW: question_id -> list[(skill_id, weight)]
    # ---------------------------------------------------------
    qssw_rows = db.execute(
        select(
            models.QuestionStudentSkillWeight.question_id,
            models.QuestionStudentSkillWeight.skill_id,
            models.QuestionStudentSkillWeight.weight,
        ).where(models.QuestionStudentSkillWeight.question_id.in_(unique_qids))
    ).all()

    qssw_map: Dict[int, List[Tuple[int, Decimal]]] = {}
    for qid, skill_id, weight in qssw_rows:
        qid_i = int(qid)
        sid_i = int(skill_id)
        w = _to_decimal(weight)
        qssw_map.setdefault(qid_i, []).append((sid_i, w))

    # ---------------------------------------------------------
    # 3) Coverage check: Missing QSSW -> explicit error
    # ---------------------------------------------------------
    missing_qssw = [qid for qid in unique_qids if qid not in qssw_map]
    if missing_qssw:
        raise MissingQSSWError(assessment_id=assessment_id, missing_question_ids=missing_qssw)

    # ---------------------------------------------------------
    # 4) Aggregate per skill
    # We keep avg_raw on 1..5 scale:
    #   contrib = answer_value * weight
    # If per-question weights sum to 1, then:
    #   sum_skill(contribs_for_question) == answer_value  (respected)
    # ---------------------------------------------------------
    agg: Dict[int, Dict] = {}  # skill_id -> {"raw_total": Decimal, "qids": set[int]}

    for qid, ans_val in normalized_responses:
        ans_d = Decimal(ans_val)

        # Normalize weights per question to ensure deterministic and scale-correct scoring
        weights = qssw_map[qid]
        wsum = sum(w for _, w in weights)

        if wsum <= 0:
            raise ValueError(f"QSSW weights sum to 0 for question_id={qid}")

        for skill_id, weight in weights:
            wnorm = weight / wsum
            contrib = ans_d * wnorm

            if skill_id not in agg:
                agg[skill_id] = {
                                "raw_total": Decimal("0"),
                                "qids": set(),
                                "norm_weight_sum": Decimal("0"),
                            }

            agg[skill_id]["raw_total"] += contrib
            agg[skill_id]["norm_weight_sum"] += wnorm
            agg[skill_id]["qids"].add(qid)

    # ---------------------------------------------------------
    # 4b) Cleanup stale rows (important)
    # If a previous scoring run wrote rows for skills that no longer appear in agg,
    # they must be removed to avoid mixed scoring regimes and incorrect tiers.
    # ---------------------------------------------------------
    agg_skill_ids = sorted(agg.keys())

    if agg_skill_ids:
        (
            db.query(models.StudentSkillScore)
            .filter(
                models.StudentSkillScore.assessment_id == assessment_id,
                models.StudentSkillScore.scoring_config_version == scoring_config_version,
                ~models.StudentSkillScore.skill_id.in_(agg_skill_ids),
            )
            .delete(synchronize_session=False)
        )
        db.flush()
    else:
        # Extremely defensive: if no skills aggregated, clear any prior rows for this scoring version
        (
            db.query(models.StudentSkillScore)
            .filter(
                models.StudentSkillScore.assessment_id == assessment_id,
                models.StudentSkillScore.scoring_config_version == scoring_config_version,
            )
            .delete(synchronize_session=False)
        )
        db.flush()

    # ---------------------------------------------------------
    # 5) Persist into student_skill_scores (idempotent upsert)
    # Unique key already exists: (assessment_id, scoring_config_version, skill_id)
    #
    # IMPORTANT:
    # - raw_total is a weighted sum of answer_value contributions.
    # - To keep avg_raw on the canonical 1..5 scale, divide by the sum of
    #   normalized weights for this skill across contributing questions.
    #   (NOT by question_count, which would shrink scores below 1 and cause negatives.)
    # ---------------------------------------------------------
    for skill_id in sorted(agg.keys()):
        raw_total: Decimal = agg[skill_id]["raw_total"]
        question_count: int = len(agg[skill_id]["qids"])
        norm_weight_sum: Decimal = agg[skill_id]["norm_weight_sum"]

        # Defensive: should never happen, but keeps replayability safe.
        if question_count <= 0:
            continue

        # If a skill has zero normalized weight sum, it has no meaningful evidence.
        if norm_weight_sum <= 0:
            continue

        # avg_raw stays on ~1..5 scale
        avg_raw = raw_total / norm_weight_sum

        # Linear 1..5 -> 0..100 mapping (beta policy)
        scaled_0_100 = ((avg_raw - Decimal("1")) / Decimal("4")) * Decimal("100")

        # Deterministic rounding for persistence (prevents drift across runs)
        raw_total_q = raw_total.quantize(_Q, rounding=ROUND_HALF_UP)
        avg_raw_q = avg_raw.quantize(_Q, rounding=ROUND_HALF_UP)
        scaled_q = scaled_0_100.quantize(_Q, rounding=ROUND_HALF_UP)

        existing = (
            db.query(models.StudentSkillScore)
            .filter_by(
                assessment_id=assessment_id,
                scoring_config_version=scoring_config_version,
                skill_id=skill_id,
            )
            .first()
        )

        if existing:
            existing.student_id = student_id
            existing.raw_total = float(raw_total_q)
            existing.question_count = int(question_count)
            existing.avg_raw = float(avg_raw_q)
            existing.scaled_0_100 = float(scaled_q)
            existing.computed_at = datetime.utcnow()
        else:
            db.add(
                models.StudentSkillScore(
                    assessment_id=assessment_id,
                    student_id=student_id,
                    scoring_config_version=scoring_config_version,
                    skill_id=skill_id,
                    raw_total=float(raw_total_q),
                    question_count=int(question_count),
                    avg_raw=float(avg_raw_q),
                    scaled_0_100=float(scaled_q),
                )
            )

    db.commit()


    # ---------------------------------------------------------
    # 6) Return map (keep existing response contract)
    # NOTE:
    # - This internal return includes computed math.
    # - Routers must keep student-safe projections (tiers only).
    # - Use the SAME denominator as persistence to avoid inconsistencies.
    # ---------------------------------------------------------
    skills_payload = {}

    for skill_id in agg:
        raw_total: Decimal = agg[skill_id]["raw_total"]
        qcount: int = len(agg[skill_id]["qids"])
        norm_weight_sum: Decimal = agg[skill_id]["norm_weight_sum"]

        # Mirror persistence guards for deterministic behavior
        if qcount <= 0 or norm_weight_sum <= 0:
            continue

        avg_raw = raw_total / norm_weight_sum
        scaled_0_100 = ((avg_raw - Decimal("1")) / Decimal("4")) * Decimal("100")

        skills_payload[skill_id] = {
            "raw_total": float(raw_total.quantize(_Q, rounding=ROUND_HALF_UP)),
            "question_count": qcount,
            "avg_raw": float(avg_raw.quantize(_Q, rounding=ROUND_HALF_UP)),
            "scaled_0_100": float(scaled_0_100.quantize(_Q, rounding=ROUND_HALF_UP)),
        }

    return {
        "assessment_id": assessment_id,
        "scoring_config_version": scoring_config_version,
        "skills": skills_payload,
        # Preserve existing "skill_scores" contract: avg_raw per skill, keys as strings for stable JSON
        "skill_scores": {str(k): float(v["avg_raw"]) for k, v in skills_payload.items()},
    }
