"""
Weight approval service — shared helpers for Stage 2 draft/submit endpoints.

Public surface (imported by admin_portal.py):
    Constants  : MIN_KEYSKILLS, MAX_SINGLE_WEIGHT, WEIGHT_SUM_TARGET
    Functions  : validate_proposed_weights, snapshot_current_weights,
                 validate_career_exists
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# ── Rule constants ─────────────────────────────────────────────────────────────

MIN_KEYSKILLS     = 5     # minimum number of key skills per career
MAX_SINGLE_WEIGHT = 50    # no single key-skill may exceed this percentage
WEIGHT_SUM_TARGET = 100   # proposed weights must sum to exactly this


# ── Validation ─────────────────────────────────────────────────────────────────

def validate_proposed_weights(
    items: list[dict[str, Any]],
    db: Session,
) -> list[dict[str, Any]]:
    """
    Validate a proposed_weights list for one career.

    items: [{"keyskill_id": int, "weight_percentage": int}, ...]

    Rules (evaluated eagerly so all errors are returned in one call):
        1. Count >= MIN_KEYSKILLS
        2. No duplicate keyskill_ids within the payload
        3. Each weight_percentage >= 0
        4. No single weight > MAX_SINGLE_WEIGHT
        5. SUM(weight_percentage) == WEIGHT_SUM_TARGET
        6. All keyskill_ids exist in the keyskills table (FK check)
           — skipped when rules 1–5 already produced errors, to avoid
             confusing FK errors on otherwise invalid payloads.

    Returns a list of error dicts (empty list = valid).
    Each error dict contains at least {"error_code": str, "message": str}.
    """
    errors: list[dict[str, Any]] = []

    # Rule 1 — minimum count
    if len(items) < MIN_KEYSKILLS:
        errors.append({
            "error_code": "TOO_FEW_KEYSKILLS",
            "message": (
                f"At least {MIN_KEYSKILLS} key skills required; "
                f"got {len(items)}."
            ),
        })

    # Rule 2 — no duplicates within payload
    seen: set[int] = set()
    dupes: list[int] = []
    for item in items:
        kid = item["keyskill_id"]
        if kid in seen:
            dupes.append(kid)
        seen.add(kid)
    if dupes:
        errors.append({
            "error_code": "DUPLICATE_KEYSKILL_ID",
            "message": (
                f"Duplicate keyskill_id(s) in proposed_weights: "
                f"{sorted(set(dupes))}."
            ),
            "keyskill_ids": sorted(set(dupes)),
        })

    # Rule 3 — non-negative
    negative = [item["keyskill_id"] for item in items if item["weight_percentage"] < 0]
    if negative:
        errors.append({
            "error_code": "NEGATIVE_WEIGHT",
            "message": (
                f"weight_percentage must be >= 0; "
                f"affected keyskill_id(s): {sorted(negative)}."
            ),
            "keyskill_ids": sorted(negative),
        })

    # Rule 4 — concentration cap
    heavy = [
        item["keyskill_id"]
        for item in items
        if item["weight_percentage"] > MAX_SINGLE_WEIGHT
    ]
    if heavy:
        errors.append({
            "error_code": "WEIGHT_CONCENTRATION_EXCEEDED",
            "message": (
                f"No single key skill may exceed {MAX_SINGLE_WEIGHT}%; "
                f"affected keyskill_id(s): {sorted(heavy)}."
            ),
            "keyskill_ids": sorted(heavy),
        })

    # Rule 5 — sum
    total = sum(item["weight_percentage"] for item in items)
    if total != WEIGHT_SUM_TARGET:
        errors.append({
            "error_code": "WEIGHT_SUM_NOT_100",
            "message": (
                f"proposed_weights must sum to {WEIGHT_SUM_TARGET}; "
                f"got {total}."
            ),
            "sum": total,
        })

    # Rule 6 — FK existence (only when rules 1-5 passed; avoids noise)
    if not errors and items:
        keyskill_ids = sorted({item["keyskill_id"] for item in items})
        ok_rows = db.execute(
            text("SELECT id FROM keyskills WHERE id = ANY(:ids)"),
            {"ids": keyskill_ids},
        ).fetchall()
        ok_ids = {r[0] for r in ok_rows}
        missing = sorted(set(keyskill_ids) - ok_ids)
        if missing:
            errors.append({
                "error_code": "KEYSKILL_NOT_FOUND",
                "message": (
                    f"keyskill_id(s) not found in keyskills table: {missing}."
                ),
                "keyskill_ids": missing,
            })

    return errors


# ── DB helpers ─────────────────────────────────────────────────────────────────

def snapshot_current_weights(
    career_id: int,
    db: Session,
) -> list[dict[str, Any]]:
    """
    Return the current career_keyskill_association rows for one career as a
    plain list of dicts, ordered by weight_percentage DESC.

    READ-ONLY — issues a single SELECT.  Never writes to
    career_keyskill_association.  The result becomes `baseline_weights` inside
    the changes JSONB snapshot on the WeightChangeRequest row.
    """
    rows = db.execute(
        text("""
            SELECT keyskill_id, weight_percentage
            FROM career_keyskill_association
            WHERE career_id = :career_id
            ORDER BY weight_percentage DESC
        """),
        {"career_id": career_id},
    ).mappings().all()
    return [
        {
            "keyskill_id":       r["keyskill_id"],
            "weight_percentage": r["weight_percentage"],
        }
        for r in rows
    ]


def validate_career_exists(
    career_id: int,
    db: Session,
) -> dict[str, Any] | None:
    """
    Return {"id": int, "title": str} for the career if it exists, else None.
    """
    row = db.execute(
        text("SELECT id, title FROM careers WHERE id = :id"),
        {"id": career_id},
    ).mappings().first()
    return dict(row) if row else None
