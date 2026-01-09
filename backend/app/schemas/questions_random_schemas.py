from pydantic import BaseModel, Field
from typing import List, Optional


class RandomQuestionItemOut(BaseModel):
    question_id: str = Field(..., example="V1_Q1")
    skill_id: int = Field(..., example=1)
    question_text: str = Field(..., example="I enjoy solving logical puzzles.")


class RandomQuestionsResponse(BaseModel):
    assessment_version: str = Field(..., example="v1")
    count_requested: int = Field(..., example=2)
    count_returned: int = Field(..., example=2)
    lang: Optional[str] = Field(None, example="hi")
    lang_used: str = Field(..., example="hi")
    questions: List[RandomQuestionItemOut] = Field(default_factory=list)
