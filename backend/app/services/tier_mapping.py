# backend/app/services/tier_mapping.py

from typing import Dict
from sqlalchemy.orm import Session

from app import models

# ----------------------------------------
# Tier → Numeric score mapping (0–100)
# ----------------------------------------

TIER_TO_SCORE: Dict[str, float] = {
    "very_low": 20.0,
    "low": 40.0,
    "medium": 60.0,
    "high": 80.0,
    "very_high": 100.0,
    # display variants
    "Very Low": 20.0,
    "Low": 40.0,
    "Medium": 60.0,
    "High": 80.0,
    "Very High": 100.0,
}


def tier_to_score(tier_label: str) -> float:
    """
    Convert a tier label into a numeric score [0–100].

    Mapping (Option B):
        Very Low  -> 20
        Low       -> 40
        Medium    -> 60
        High      -> 80
        Very High -> 100
    """
    if tier_label is None:
        return 60.0

    # direct lookup first
    if tier_label in TIER_TO_SCORE:
        return TIER_TO_SCORE[tier_label]

    # normalize variants
    key = tier_label.strip().lower().replace("_", " ")
    lookup = {
        "very low": 20.0,
        "low": 40.0,
        "medium": 60.0,
        "high": 80.0,
        "very high": 100.0,
    }

    return lookup.get(key, 60.0)  # default = Medium


def apply_keyskill_tiers(
    db: Session,
    student_id: int,
    keyskill_tiers: Dict[object, str],
) -> None:
    """
    Upsert StudentKeySkillMap entries using tier labels.

    keyskill_tiers is expected to be { keyskill_id: tier_label }.

    To be robust against current assessment output, we:
      - Try to coerce keys to int
      - Skip anything that isn't a valid int
      - Skip if no KeySkill with that id exists

    This prevents foreign key errors while keeping the function
    ready for a future clean mapping from assessment → keyskill.
    """

    for raw_id, tier_label in keyskill_tiers.items():
        # 1) Try to interpret the key as an integer id
        try:
            keyskill_id = int(raw_id)
        except (TypeError, ValueError):
            # e.g. "Creativity" → skip for now
            continue

        # 2) Ensure the keyskill actually exists
        ks = db.query(models.KeySkill).get(keyskill_id)
        if not ks:
            # No such KeySkill → skip
            continue

        # 3) Convert tier → numeric score
        score = tier_to_score(tier_label)

        # 4) Upsert mapping
        mapping = (
            db.query(models.StudentKeySkillMap)
            .filter(
                models.StudentKeySkillMap.student_id == student_id,
                models.StudentKeySkillMap.keyskill_id == keyskill_id,
            )
            .first()
        )

        if mapping is None:
            mapping = models.StudentKeySkillMap(
                student_id=student_id,
                keyskill_id=keyskill_id,
                score=score,
            )
            db.add(mapping)
        else:
            mapping.score = score

    db.commit()
