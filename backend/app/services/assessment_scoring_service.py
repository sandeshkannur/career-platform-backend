from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime
from app import models

SCORING_CONFIG_VERSION = "v1"

class EmptyResponsesError(Exception):
    pass

def compute_and_persist_skill_scores(
    db: Session,
    assessment_id: int,
    student_id: int,
    scoring_config_version: str = SCORING_CONFIG_VERSION,
) -> dict:
    # 1) Load responses
    responses = db.execute(
        select(models.AssessmentResponse.question_id, models.AssessmentResponse.answer)
        .where(models.AssessmentResponse.assessment_id == assessment_id)
    ).all()

    if not responses:
        raise EmptyResponsesError("No responses found for this assessment.")

    qids = [qid for (qid, _) in responses]

    # 2) Load question -> skill mapping (and weight if you want)
    qrows = db.execute(
        select(models.Question.id, models.Question.skill_id, models.Question.weight)
        .where(models.Question.id.in_(qids))
    ).all()

    qmap = {qid: (skill_id, weight or 1) for (qid, skill_id, weight) in qrows}

    # 3) Aggregate per skill
    agg = {}  # skill_id -> {"raw_total":..., "count":...}

    for qid, ans_str in responses:
        if qid not in qmap:
            # Data integrity issue: response points to unknown question
            # v1 recommendation: fail fast
            raise ValueError(f"Unknown question_id in responses: {qid}")

        skill_id, weight = qmap[qid]

        try:
            ans = int(ans_str)
        except Exception:
            raise ValueError(f"Non-numeric answer for question_id={qid}: {ans_str}")

        if ans < 1 or ans > 5:
            raise ValueError(f"Answer out of range (1-5) for question_id={qid}: {ans}")

        # TEMP scoring (no exact normalization table yet):
        # raw_total accumulates numeric answers (optionally weighted)
        raw = float(ans) * float(weight)

        if skill_id not in agg:
            agg[skill_id] = {"raw_total": 0.0, "count": 0}

        agg[skill_id]["raw_total"] += raw
        agg[skill_id]["count"] += 1

    # 4) Persist with idempotent upsert
    # Strategy: per (assessment_id, version, skill_id), update or insert.
    for skill_id, v in agg.items():
        raw_total = v["raw_total"]
        count = v["count"]
        avg_raw = raw_total / count

        # TEMP scaling for v1 (until you implement the exact table):
        # map avg 1..5 to 0..100 linearly:
        scaled_0_100 = ((avg_raw - 1.0) / 4.0) * 100.0

        existing = db.query(models.StudentSkillScore).filter_by(
            assessment_id=assessment_id,
            scoring_config_version=scoring_config_version,
            skill_id=skill_id,
        ).first()

        if existing:
            existing.student_id = student_id
            existing.raw_total = raw_total
            existing.question_count = count
            existing.avg_raw = avg_raw
            existing.scaled_0_100 = scaled_0_100
            existing.computed_at = datetime.utcnow()
        else:
            db.add(models.StudentSkillScore(
                assessment_id=assessment_id,
                student_id=student_id,
                scoring_config_version=scoring_config_version,
                skill_id=skill_id,
                raw_total=raw_total,
                question_count=count,
                avg_raw=avg_raw,
                scaled_0_100=scaled_0_100,
            ))

    db.commit()

    # 5) Return map (so router can continue tiers/recommendations)
    return {
        "assessment_id": assessment_id,
        "scoring_config_version": scoring_config_version,
        "skills": {
            skill_id: {
                "raw_total": agg[skill_id]["raw_total"],
                "question_count": agg[skill_id]["count"],
                "avg_raw": (agg[skill_id]["raw_total"] / agg[skill_id]["count"]),
                "scaled_0_100": ((agg[skill_id]["raw_total"] / agg[skill_id]["count"] - 1.0) / 4.0) * 100.0,
            }
            for skill_id in agg
        }
    }
