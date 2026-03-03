from pydantic import BaseModel
from typing import Optional


class SubmitResponseOut(BaseModel):
    success: bool
    assessment_id: int
    question_id: str

    answered_count: int
    last_answered_question_id: Optional[str] = None
    next_question_id: Optional[str] = None
    total_questions: int
    is_complete: bool
