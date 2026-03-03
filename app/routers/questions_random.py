# app/routers/questions_random.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.deps import get_db
from app.schemas import RandomQuestionsResponse, RandomQuestionItemOut
from app.models import Question

# ✅ Use the same auth dependency pattern as your project.
from app.auth.auth import get_current_user  # <-- adjust if needed

router = APIRouter(prefix="/questions", tags=["Questions"])

# Supported language → Question model field mapping
LANG_FIELD_MAP = {
    "en": "question_text_en",
    "hi": "question_text_hi",
    "ta": "question_text_ta",
}


@router.get(
    "/random",
    response_model=RandomQuestionsResponse,
    summary="Get randomized questions for an assessment version (student)",
)
def get_random_questions(
    assessment_version: str = Query(
        ..., description="Assessment version, e.g. v1"
    ),
    count: int = Query(
        ...,
        gt=0,
        le=50,
        description="Number of questions to return (max 50)",
    ),
    lang: str | None = Query(
        None,
        description="Optional language code: en, hi, ta (unsupported values fall back to en)",
    ),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    # ------------------------------------------------------------
    # Step 3: Validate availability (version-filtered) BEFORE random selection
    # ------------------------------------------------------------
    available = (
        db.query(Question)
        .filter(Question.assessment_version == assessment_version)
        .count()
    )

    if available == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No questions found for assessment_version='{assessment_version}'"
        )

    if count > available:
        raise HTTPException(
            status_code=409,
            detail=f"Insufficient questions: requested={count}, available={available}"
        )

    # ------------------------------------------------------------
    # Step 4: Random selection (version-filtered + randomized + limited)
    # ------------------------------------------------------------
    rows = (
        db.query(Question)
        .filter(Question.assessment_version == assessment_version)
        .order_by(func.random())
        .limit(count)
        .all()
    )

    # ------------------------------------------------------------
    # Step 5: Language selection + fallback per question
    # ------------------------------------------------------------
    requested_lang = (lang or "en").strip().lower()
    if requested_lang not in LANG_FIELD_MAP:
        # Unsupported lang → fallback to English
        lang_used = "en"
        lang_field = LANG_FIELD_MAP["en"]
    else:
        lang_used = requested_lang
        lang_field = LANG_FIELD_MAP[requested_lang]

    questions_out = []
    for q in rows:
        # If your Question model uses question_id instead of id,
        # change q.id -> q.question_id below.
        text_in_lang = getattr(q, lang_field, None)

        # Fallback to English if requested language text is missing/blank
        if text_in_lang is None or (isinstance(text_in_lang, str) and text_in_lang.strip() == ""):
            text_in_lang = q.question_text_en

        questions_out.append(
            RandomQuestionItemOut(
                question_id=str(q.id),
                question_code=q.question_code,
                skill_id=q.skill_id,
                question_text=text_in_lang,
            )
        )

    return RandomQuestionsResponse(
        assessment_version=assessment_version,
        count_requested=count,
        count_returned=len(questions_out),
        lang=lang,
        lang_used=lang_used,
        questions=questions_out,
    )
