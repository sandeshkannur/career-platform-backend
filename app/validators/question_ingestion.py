from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app import models


class FieldError(BaseModel):
    field: str
    message: str


class RowValidationError(BaseModel):
    row_index: Optional[int] = None
    errors: List[FieldError]
    raw: Dict[str, Any] = Field(default_factory=dict)


class ValidatedQuestionRow(BaseModel):
    """
    Shared validated representation for question ingestion.
    This is intentionally minimal (aligned to your current B1 needs),
    and future-proof (optional fields can be added without breaking CSV ingestion).
    """
    assessment_version: str
    skill_id: int
    question_text_en: str

    question_text_hi: Optional[str] = None
    question_text_ta: Optional[str] = None

    # Defaults (future-ready)
    is_active: bool = True

    # Optional enums (only validated if present and rule exists)
    question_type: Optional[str] = None
    response_type: Optional[str] = None

    @field_validator("assessment_version")
    @classmethod
    def assessment_version_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("assessment_version is required")
        return v

    @field_validator("question_text_en")
    @classmethod
    def question_text_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("question_text_en is required")
        return v


# Version-aware rules registry (future-proof)
QUESTION_SCHEMA_RULES: Dict[str, Dict[str, Any]] = {
    "v1": {
        "required": {"assessment_version", "skill_id", "question_text_en"},
        "defaults": {"is_active": True},
        "enums": {
            # Add later when you introduce these fields in CSV/API
            # "question_type": {"likert", "mcq"},
            # "response_type": {"likert_5"},
        },
    }
}


def _norm_key(k: str) -> str:
    return (k or "").strip().lower()


def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {_norm_key(k): v for k, v in (row or {}).items()}


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _coerce_bool(value: Any) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "t", "yes", "y", "1"}:
        return True
    if s in {"false", "f", "no", "n", "0"}:
        return False
    return None


def validate_question_row(
    *,
    db: Session,
    row: Dict[str, Any],
    row_index: Optional[int] = None,
) -> Union[ValidatedQuestionRow, RowValidationError]:
    """
    Shared validation layer.
    - NO DB WRITES
    - DB READS: skills existence check
    - version-aware rules based on assessment_version
    """
    raw = row or {}
    normalized = _normalize_row(raw)

    # Accept schema_version as alias (future-proof); normalize into assessment_version
    av = normalized.get("assessment_version") or normalized.get("schema_version")
    if av is not None:
        av = str(av).strip()
    normalized["assessment_version"] = av

    rules = QUESTION_SCHEMA_RULES.get(av, QUESTION_SCHEMA_RULES["v1"])

    errors: List[FieldError] = []

    # Apply defaults
    for k, default_val in (rules.get("defaults") or {}).items():
        nk = _norm_key(k)
        if normalized.get(nk) in (None, ""):
            normalized[nk] = default_val

    # Required fields
    required: Set[str] = set(rules.get("required") or set())
    for req in required:
        nk = _norm_key(req)
        if normalized.get(nk) in (None, ""):
            errors.append(FieldError(field=req, message="Missing required field"))

    if errors:
        return RowValidationError(row_index=row_index, errors=errors, raw=raw)

    # Coerce skill_id
    normalized["skill_id"] = _coerce_int(normalized.get("skill_id"))
    if normalized["skill_id"] is None:
        return RowValidationError(
            row_index=row_index,
            errors=[FieldError(field="skill_id", message="skill_id must be an integer")],
            raw=raw,
        )

    # Coerce is_active if present
    if "is_active" in normalized:
        b = _coerce_bool(normalized.get("is_active"))
        if b is None and normalized.get("is_active") not in (None, ""):
            return RowValidationError(
                row_index=row_index,
                errors=[FieldError(field="is_active", message="is_active must be a boolean")],
                raw=raw,
            )
        if b is not None:
            normalized["is_active"] = b

    # Enum checks (only if field present + rule exists)
    enum_rules = rules.get("enums") or {}
    for fname, allowed in enum_rules.items():
        nk = _norm_key(fname)
        if normalized.get(nk) in (None, ""):
            continue
        val = str(normalized[nk]).strip()
        if val not in allowed:
            errors.append(
                FieldError(
                    field=fname,
                    message=f"Invalid value '{val}'. Allowed: {sorted(list(allowed))}",
                )
            )

    if errors:
        return RowValidationError(row_index=row_index, errors=errors, raw=raw)

    # Pydantic validation
    try:
        validated = ValidatedQuestionRow.model_validate(normalized)
    except ValidationError as ve:
        ve_errors: List[FieldError] = []
        for e in ve.errors():
            loc = ".".join([str(x) for x in e.get("loc", [])]) or "unknown"
            ve_errors.append(FieldError(field=loc, message=e.get("msg", "Invalid value")))
        return RowValidationError(row_index=row_index, errors=ve_errors, raw=raw)

    # DB READ: ensure skill exists
    skill_exists = (
        db.query(models.Skill.id)
        .filter(models.Skill.id == validated.skill_id)
        .first()
    )
    if not skill_exists:
        return RowValidationError(
            row_index=row_index,
            errors=[FieldError(field="skill_id", message=f"skill_id {validated.skill_id} does not exist")],
            raw=raw,
        )

    return validated
