from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.models import Question
from app.services.i18n_resolver import resolve_question_text, normalize_lang
from app.services.explanations import resolve_cms_text
from app.auth.auth import get_current_user

from app.schemas import StudentQuestionsResponse, StudentQuestionItemOut  # from schemas.py

router = APIRouter(prefix="/questions", tags=["Questions"])

def _load_question_facets(db: Session, question_ids: list[int], assessment_version: str, locale: str) -> dict[int, list[dict]]:
    """
    Returns: question_id -> list of facet display names

    Fallback chain for each facet:
      1) facet_translations for requested locale
      2) facet_translations for 'en'
      3) aq_facets.facet_name
      4) facet_id (last resort)
    """
    if not question_ids:
        return {}

    rows = db.execute(
        text(
            """
            SELECT qft.question_id, qft.facet_id
            FROM question_facet_tags qft
            WHERE qft.question_id = ANY(:qids)
            ORDER BY qft.question_id, qft.facet_id
            """
        ),
        {"qids": question_ids},
    ).fetchall()

    if not rows:
        return {}

    qid_to_fids: dict[int, list[str]] = {}
    facet_ids: set[str] = set()

    for qid, fid in rows:
        facet_ids.add(fid)
        qid_to_fids.setdefault(qid, []).append(fid)

    facet_name_rows = db.execute(
        text(
            """
            SELECT
                af.facet_id,
                af.aq_id,
                COALESCE(ft_req.facet_name, ft_en.facet_name, af.facet_name, af.facet_id) AS display_name
            FROM aq_facets af
            LEFT JOIN facet_translations ft_req
                ON ft_req.facet_id = af.facet_id AND ft_req.locale = :loc
            LEFT JOIN facet_translations ft_en
                ON ft_en.facet_id = af.facet_id AND ft_en.locale = 'en'
            WHERE af.facet_id = ANY(:fids)
            """
        ),
        {"loc": locale, "fids": list(facet_ids)},
    ).fetchall()

    fid_to_payload: dict[str, dict] = {}

    for (fid, aq_id, name_en) in facet_name_rows:
        # Try CMS (explainability_content) using explanation_key == facet_code (e.g., AQ06_F1)
        cms_text = resolve_cms_text(
            db,
            version=assessment_version,
            locale=locale,
            explanation_key=fid,
            allow_numbers=True,
        )

        # Fallback: if CMS returns placeholders like [missing:...] or [unsafe:...]
        if isinstance(cms_text, str) and (cms_text.startswith("[missing:") or cms_text.startswith("[unsafe:")):
            facet_name = name_en
            facet_name_used = "en"
        else:
            facet_name = cms_text
            facet_name_used = locale if (facet_name and facet_name != name_en) else "en"

        fid_to_payload[fid] = {
            "facet_code": fid,
            "facet_name_en": name_en,
            "facet_name": facet_name,
            "facet_name_used": facet_name_used,
            "aq_code": aq_id,
        }

    qid_to_tags: dict[int, list[dict]] = {}
    for qid, fids in qid_to_fids.items():
        qid_to_tags[qid] = [fid_to_payload.get(fid, {"facet_code": fid, "facet_name_en": None, "facet_name": None, "facet_name_used": "en", "aq_code": None}) for fid in fids]

    return qid_to_tags

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
    requested_lang = normalize_lang(lang)
    lang_used_overall = "en"

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

    questions_out: list[StudentQuestionItemOut] = []
    question_ids = [q.id for q in rows]
    qid_to_facets = _load_question_facets(db, question_ids, assessment_version, requested_lang)

    for q in rows:
        text_in_lang, lang_used = resolve_question_text(
            db,
            assessment_version=assessment_version,
            question=q,
            requested_lang=requested_lang,
        )

        if lang_used == requested_lang:
            lang_used_overall = requested_lang
        questions_out.append(
            StudentQuestionItemOut(
                question_id=str(q.id),  # ✅ must be string for schema
                question_code=q.question_code,
                skill_id=q.skill_id,
                facet_tags=qid_to_facets.get(q.id, []),
                question_text=text_in_lang,
            )
        )

    # ✅ Always return the response model (never None)
    payload = StudentQuestionsResponse(
        assessment_version=assessment_version,
        lang=lang,
        lang_used=lang_used_overall,
        count_returned=len(questions_out),
        questions=questions_out,
    ).model_dump()

    return JSONResponse(content=payload, media_type="application/json; charset=utf-8")
# ----------------------------------------------------------
# 🧩 Fetch question pool (runner support)
# IMPORTANT: must be defined BEFORE "/{question_id}" to avoid route collision
# ----------------------------------------------------------
@router.get(
    "/pool",
    summary="Fetch question pool for the runner",
)
def get_question_pool(
    lang: str | None = Query(
        None,
        description="Optional language code: en, hi, ta (unsupported values fall back to en)",
    ),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    requested_lang = normalize_lang(lang)
    lang_used_overall = "en"

    questions = db.query(Question).order_by(Question.id.asc()).all()

    question_ids = [q.id for q in questions]
    qid_to_facets = _load_question_facets(db, question_ids, "v1", requested_lang)

    items = []
    for q in questions:
        text_in_lang, lang_used = resolve_question_text(
            db,
            assessment_version=q.assessment_version,
            question=q,
            requested_lang=requested_lang,
        )

        if lang_used == requested_lang:
            lang_used_overall = requested_lang

        items.append(
            {
                "question_id": str(q.id),
                "question_code": q.question_code,
                "assessment_version": q.assessment_version,
                "lang": lang,
                "lang_used": lang_used,
                "skill_id": q.skill_id,
                "facet_tags": qid_to_facets.get(q.id, []),
                "question_text": text_in_lang,
            }
        )

    payload = {
        "assessment_version": "v1",
        "lang": lang,
        "lang_used": lang_used_overall,
        "count_returned": len(items),
        "questions": items,
    }

    return JSONResponse(content=payload, media_type="application/json; charset=utf-8")

# ----------------------------------------------------------
# 📌 Fetch a single question by ID (resume-safe, deterministic)
# ----------------------------------------------------------
@router.get(
    "/{question_id}",
    summary="Fetch a question by ID (resume-safe)",
)
def get_question_by_id(
    question_id: int,
    lang: str | None = Query(
        None,
        description="Optional language code: en, hi, ta (unsupported values fall back to en)",
    ),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Resume-safe question fetch.
    Frontend runner uses next_question_id from /v1/assessments/active and fetches the exact question by ID.

    - Deterministic (by ID)
    - Version-safe (question record contains assessment_version)
    - Localized text with fallback to English
    """

    q = db.get(Question, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    requested_lang = normalize_lang(lang)
    qid_to_facets = _load_question_facets(db, [q.id], q.assessment_version, requested_lang)
    text_in_lang, lang_used = resolve_question_text(
        db,
        assessment_version=q.assessment_version,
        question=q,
        requested_lang=requested_lang,
    )

    payload = {
        "question_id": str(q.id),                 # keep as string (matches your response submit schema style)
        "question_code": q.question_code,
        "assessment_version": q.assessment_version,
        "lang": lang,
        "lang_used": lang_used,
        "skill_id": q.skill_id,                   # legacy field (already used in your StudentQuestionItemOut)
        "facet_tags": qid_to_facets.get(q.id, []),
        "question_text": text_in_lang,
    }

    return JSONResponse(content=payload, media_type="application/json; charset=utf-8")
