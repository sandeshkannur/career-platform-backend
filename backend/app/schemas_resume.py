from pydantic import BaseModel
from typing import Optional


class ActiveAssessmentResponse(BaseModel):
    active: bool
    assessment_id: Optional[int] = None
    assessment_version: Optional[str] = None
    scoring_config_version: Optional[str] = None
    answered_count: Optional[int] = None
    last_answered_question_id: Optional[str] = None
    next_question_id: Optional[str] = None
    total_questions: Optional[int] = None
