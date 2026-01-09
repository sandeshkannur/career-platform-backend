from pydantic import BaseModel, Field
from typing import List, Optional


class StudentQuestionItemOut(BaseModel):
    question_id: str = Field(..., example="V1_Q1")
    skill_id: int = Field(..., example=1)
    question_text: str = Field(..., example="I enjoy solving logical puzzles.")


class StudentQuestionsResponse(BaseModel):
    assessment_version: str = Field(..., example="v1")
    lang: Optional[str] = Field(None, example="hi")
    lang_used: str = Field(..., example="hi")
    count_returned: int = Field(..., example=2)
    questions: List[StudentQuestionItemOut]
