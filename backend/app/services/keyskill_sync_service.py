# backend/app/services/keyskill_sync_service.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app import models


@dataclass
class SyncResult:
    assessment_id: int
    scoring_config_version: str
    keyskills_upserted_count: int = 0
    skills_seen_count: int = 0
    skills_unmapped_count: int = 0
    notes: List[str] = field(default_factory=list)


def sync_skill_scores_to_keyskills(
    db: Session,
    assessment_id: int,
    scoring_config_version: str,
) -> SyncResult:
    """
    B8 — Internal post-scoring mapping

    Reads:
      - student_skill_scores (filtered by assessment_id + scoring_config_version)
      - skill_keyskill_map (Skill -> KeySkill mapping, with optional weights)

    Writes:
      - student_keyskill_map (student_id + keyskill_id + score)

    Deterministic aggregation:
      - For each keyskill_id: weighted average of scaled_0_100 from contributing skills
      - If weight not provided, default is 1.0 (but your table has NOT NULL weight)

    Idempotency:
      - Upsert by (student_id, keyskill_id) because destination table has no assessment/version fields.
      - Safe re-runs overwrite score consistently.
    """

    result = SyncResult(
        assessment_id=assessment_id,
        scoring_config_version=scoring_config_version,
    )

    # 1) Read all skill scores for this assessment + scoring version
    skill_scores = (
        db.query(models.StudentSkillScore)
        .filter(models.StudentSkillScore.assessment_id == assessment_id)
        .filter(models.StudentSkillScore.scoring_config_version == scoring_config_version)
        .all()
    )

    if not skill_scores:
        result.notes.append("No student_skill_scores found for assessment/version; nothing to sync.")
        return result

    result.skills_seen_count = len(skill_scores)

    # 2) All rows should belong to the same student (because assessment_id is for one student)
    # 2) All rows should belong to the same user (assessment_id is for one user)
    user_id = skill_scores[0].student_id  # this is users.id from B7

    if user_id is None:
        result.notes.append(
            "Missing user mapping (student_id/users.id is NULL). Aborting sync safely."
        )
        return result

    # ✅ NEW: map users.id -> students.id using students.user_id
    student = (
        db.query(models.Student)
        .filter(models.Student.user_id == user_id)
        .first()
    )

    if not student:
        result.notes.append(
            f"Missing student profile mapping: no students.row found for users.id={user_id}. "
            "Skipping keyskill sync."
        )
        return result

    student_id = student.id  # ✅ students.id required by FK in student_keyskill_map

    # 3) Prepare skill_id -> scaled score
    score_by_skill: Dict[int, float] = {ss.skill_id: float(ss.scaled_0_100) for ss in skill_scores}
    skill_ids = list(score_by_skill.keys())

    # 4) Load Skill -> KeySkill mappings for these skills
    mappings = (
        db.query(models.SkillKeySkillMap)
        .filter(models.SkillKeySkillMap.skill_id.in_(skill_ids))
        .all()
    )

    if not mappings:
        result.skills_unmapped_count = len(skill_ids)
        result.notes.append("No Skill->KeySkill mappings found for any skills; nothing written.")
        return result

    # 5) Aggregate into keyskill buckets:
    # keyskill_id -> (weighted_sum, weight_total, contributing_skill_count)
    agg: Dict[int, Tuple[float, float, int]] = {}
    mapped_skill_ids = set()

    for m in mappings:
        skill_id = m.skill_id
        keyskill_id = m.keyskill_id

        if skill_id not in score_by_skill:
            continue

        mapped_skill_ids.add(skill_id)

        weight = float(m.weight) if m.weight is not None else 1.0
        score = score_by_skill[skill_id]

        wsum, wtot, cnt = agg.get(keyskill_id, (0.0, 0.0, 0))
        wsum += score * weight
        wtot += weight
        cnt += 1
        agg[keyskill_id] = (wsum, wtot, cnt)

    # 6) Unmapped skills (scores exist but no mapping rows)
    result.skills_unmapped_count = len(set(skill_ids) - mapped_skill_ids)
    if result.skills_unmapped_count > 0:
        result.notes.append(
            f"{result.skills_unmapped_count} skill(s) had no KeySkill mapping and were skipped."
        )

    # 7) Upsert into student_keyskill_map by (student_id, keyskill_id)
    upserted = 0
    for keyskill_id, (wsum, wtot, cnt) in agg.items():
        if wtot <= 0:
            continue

        keyskill_score = wsum / wtot  # 0..100

        existing = (
            db.query(models.StudentKeySkillMap)
            .filter(models.StudentKeySkillMap.student_id == student_id)
            .filter(models.StudentKeySkillMap.keyskill_id == keyskill_id)
            .first()
        )

        if existing:
            existing.score = keyskill_score
        else:
            new_row = models.StudentKeySkillMap(
                student_id=student_id,
                keyskill_id=keyskill_id,
                score=keyskill_score,
            )
            db.add(new_row)

        upserted += 1

    db.commit()

    result.keyskills_upserted_count = upserted
    return result
