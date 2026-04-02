# backend/app/projections/student_safe.py
"""
PR38: Unified Student-Safe Projection Layer

Goal:
- Centralize redaction/sanitization for ALL student-facing responses.
- Prevent numeric leakage: raw scores, weights, percentages, x/100 patterns, etc.
- Keep structure stable to avoid breaking UI contracts.

IMPORTANT:
- This module must NEVER change scoring logic.
- It only projects an existing payload into a student-safe view.
"""

from __future__ import annotations

from typing import Any
import re


# Numeric leakage patterns to remove from any free-text fields
_NUM_PATTERNS = [
    re.compile(r"\(\s*\d+\s*/\s*\d+\s*\)"),  # (35/100)
    re.compile(r"\(\s*\d+\s*%\s*\)"),        # (35%)
    re.compile(r"\b\d+\s*/\s*\d+\b"),        # 35/100
    re.compile(r"\b\d+\s*%\b"),              # 35%
]


# Keys that commonly leak numeric internals (remove at ANY depth)
_BLOCK_KEYS = {
    "score",
    "scores",
    "weight",
    "weights",
    "points",
    "raw_score",
    "scaled_score",
    "normalized_score",
    "percentage",
    "percent",
    "rank",
    "confidence",
    "top_keyskill_weights",
}

# Numeric values that are safe to keep even though they are integers.
# Without this allowlist, project_student_safe drops ALL int-valued dict entries
# (e.g. career_id) because the generic guard treats any numeric leaf as a score leak.
_ALLOW_NUMERIC_KEYS = {
    "career_id",
    "cluster_id",
    "question_id",
    "skill_id",
    "keyskill_id",
    "student_id",
    "assessment_id",
    "chapter_id",
}


def _strip_numbers_from_text(text: str) -> str:
    """
    Remove numeric leak patterns from a string while keeping the sentence readable.
    """
    t = text
    for rx in _NUM_PATTERNS:
        t = rx.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def project_student_safe(obj: Any) -> Any:
    """
    Recursively project a payload into a student-safe version.

    Rules:
    - Remove blocked numeric keys at any depth.
    - Remove numeric leaf values when they are likely to be internal scoring.
    - Strip numeric leak patterns from strings (e.g., "35%", "35/100", "(35%)").
    - Preserve overall structure (dict/list nesting) to avoid UI breakage.
    """
    # Dict
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key = str(k)

            # Drop known numeric/internal keys entirely
            if key in _BLOCK_KEYS:
                continue

            projected = project_student_safe(v)

            # If projected becomes a pure number, drop it (defensive) —
            # UNLESS the key is explicitly allowlisted as a safe identifier.
            if isinstance(projected, (int, float)) and key not in _ALLOW_NUMERIC_KEYS:
                continue

            out[key] = projected
        return out

    # List
    if isinstance(obj, list):
        return [project_student_safe(x) for x in obj]

    # String: strip numeric leakage patterns
    if isinstance(obj, str):
        return _strip_numbers_from_text(obj)

    # Primitive numbers: keep ONLY if they are clearly non-scoring identifiers.
    # We cannot reliably infer intent everywhere, so default is to KEEP numbers
    # (to avoid breaking IDs), but endpoints can block additional keys using _BLOCK_KEYS.
    return obj
