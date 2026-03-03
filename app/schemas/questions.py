from pydantic import BaseModel, Field
from typing import Optional


class AdminQuestionCreateRequest(BaseModel):
    """
    JSON payload for admin API-based question creation.

    NOTE:
    - We intentionally keep validation minimal here (types/shape only).
    - All business validation (required fields, skill_id existence, etc.)
      is enforced by validate_question_row().
    """
    assessment_version: str = Field(
        ...,
        json_schema_extra={"example": "v1"},
    )
    question_id: str = Field(
        ...,
        json_schema_extra={"example": "V1_Q3"},
    )
    skill_id: int = Field(
        ...,
        json_schema_extra={"example": 1},
    )

    # Minimal required text field (based on your current DB/table sample)
    question_text_en: str = Field(
        ...,
        json_schema_extra={"example": "I like solving complex problems."},
    )

    # Keep optional/future-proof fields without enforcing route logic
    question_text_hi: Optional[str] = Field(
        None,
        json_schema_extra={"example": "मुझे जटिल समस्याएँ हल करना पसंद है।"},
    )


class AdminQuestionCreateSuccess(BaseModel):
    status: str = Field(
        "created",
        json_schema_extra={"example": "created"},
    )
    question_id: str = Field(
        ...,
        json_schema_extra={"example": "V1_Q3"},
    )
    assessment_version: str = Field(
        ...,
        json_schema_extra={"example": "v1"},
    )
    skill_id: int = Field(
        ...,
        json_schema_extra={"example": 1},
    )


class AdminQuestionCreateError(BaseModel):
    status: str = Field(
        "error",
        json_schema_extra={"example": "error"},
    )
    error_code: str = Field(
        ...,
        json_schema_extra={"example": "ROW_VALIDATION_ERROR"},
    )
    message: str = Field(
        ...,
        json_schema_extra={"example": "skill_id does not exist"},
    )
    field: Optional[str] = Field(
        None,
        json_schema_extra={"example": "skill_id"},
    )
