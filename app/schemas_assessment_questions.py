# app/schemas_assessment_questions.py

from typing import List, Optional

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
