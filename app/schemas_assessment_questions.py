# app/schemas_assessment_questions.py
# DEPRECATED: Import via app.schemas instead. This file kept for backward compatibility.

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class AssessmentQuestionItemOut(BaseModel):
    question_id: str = Field(
        ...,
        json_schema_extra={"example": "12"},
    )
    question_code: str = Field(
        ...,
        json_schema_extra={"example": "V1_Q12"},
    )
    skill_id: int = Field(
        ...,
        json_schema_extra={"example": 1},
    )
    question_text: str = Field(
        ...,
        json_schema_extra={"example": "I enjoy solving logical puzzles."},
    )
    facet_tags: List[str] = Field(
        default_factory=list,
        json_schema_extra={"example": ["AQ01.F1", "AQ01.F2"]},
    )
    chapter_id: Optional[int] = Field(
        default=None,
        json_schema_extra={"example": 1},
    )
    question_type: Optional[str] = Field(
        default="likert",
        json_schema_extra={"example": "likert"},
    )
    response_options: Optional[Any] = Field(
        default=None,
        json_schema_extra={"example": [{"label": "I make a plan", "score_value": 5}]},
    )
    renderer_config: Optional[Any] = Field(
        default=None,
        json_schema_extra={"example": {"left": "Stressed", "right": "Calm"}},
    )


class AssessmentQuestionsResponse(BaseModel):
    assessment_version: str = Field(
        ...,
        json_schema_extra={"example": "v1"},
    )
    lang: Optional[str] = Field(
        None,
        json_schema_extra={"example": "hi"},
    )
    lang_used: str = Field(
        ...,
        json_schema_extra={"example": "hi"},
    )
    count_returned: int = Field(
        ...,
        json_schema_extra={"example": 75},
    )
    questions: List[AssessmentQuestionItemOut]
