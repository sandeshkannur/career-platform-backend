from pydantic import BaseModel, Field
from typing import List, Optional


class RandomQuestionItemOut(BaseModel):
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


class RandomQuestionsResponse(BaseModel):
    assessment_version: str = Field(
        ...,
        json_schema_extra={"example": "v1"},
    )
    count_requested: int = Field(
        ...,
        json_schema_extra={"example": 2},
    )
    count_returned: int = Field(
        ...,
        json_schema_extra={"example": 2},
    )
    lang: Optional[str] = Field(
        None,
        json_schema_extra={"example": "hi"},
    )
    lang_used: str = Field(
        ...,
        json_schema_extra={"example": "hi"},
    )
    questions: List[RandomQuestionItemOut] = Field(
        default_factory=list
    )
