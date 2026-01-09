from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Question
from app.auth.auth import get_current_user

from app.schemas import StudentQuestionsResponse, StudentQuestionItemOut  # from schemas.py

router = APIRouter(prefix="/questions", tags=["Questions"])

LANG_FIELD_MAP = {
    "en": "question_text_en",
    "hi": "question_text_hi",
    "ta": "question_text_ta",
}

@router.get(
    "",
    response_model=StudentQuestionsResponse,
    summary="Get localized questions for an assessment version (student)",
)
def get_localized_questions(
    assessment_version: str = Query(..., description="Assessment version, e.g. v1"),
    lang: str | None = Query(
        None,
        description="Optional language code: en, hi, ta (unsupported values fall back to en)",
    ),
    limit: int = Query(50, ge=1, le=200, description="Max items to return (default 50, max 200)"),
    offset: int = Query(0, ge=0, description="Pagination offset (default 0)"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    requested_lang = (lang or "en").strip().lower()
    if requested_lang not in LANG_FIELD_MAP:
        lang_used = "en"
        lang_field = LANG_FIELD_MAP["en"]
    else:
        lang_used = requested_lang
        lang_field = LANG_FIELD_MAP[requested_lang]

    rows = (
        db.query(Question)
        .filter(Question.assessment_version == assessment_version)
        .order_by(Question.id)
        .limit(limit)
        .offset(offset)
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No questions found for assessment_version='{assessment_version}'",
        )

    questions_out = []
    for q in rows:
        text_in_lang = getattr(q, lang_field, None)
        if text_in_lang is None or (isinstance(text_in_lang, str) and text_in_lang.strip() == ""):
            text_in_lang = q.question_text_en

        questions_out.append(
            StudentQuestionItemOut(
                question_id=q.id,
                skill_id=q.skill_id,
                question_text=text_in_lang,
            )
        )

    return StudentQuestionsResponse(
        assessment_version=assessment_version,
        lang=lang,
        lang_used=lang_used,
        count_returned=len(questions_out),
        questions=questions_out,
    )
