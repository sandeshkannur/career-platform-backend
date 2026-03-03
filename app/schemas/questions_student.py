from pydantic import BaseModel, Field
from typing import List, Optional


class StudentQuestionItemOut(BaseModel):
    question_id: str = Field(
        ...,
        json_schema_extra={"example": "V1_Q1"},
    )
    skill_id: int = Field(
        ...,
        json_schema_extra={"example": 1},
    )
    question_text: str = Field(
        ...,
        json_schema_extra={"example": "I enjoy solving logical puzzles."},
    )


class StudentQuestionsResponse(BaseModel):
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
        json_schema_extra={"example": 2},
    )
    questions: List[StudentQuestionItemOut]
