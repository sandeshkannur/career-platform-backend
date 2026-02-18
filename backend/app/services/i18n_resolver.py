# app/services/i18n_resolver.py

from __future__ import annotations

from sqlalchemy.orm import Session
from app import models


LEGACY_LANG_FIELD_MAP = {
    "en": "question_text_en",
    "hi": "question_text_hi",
    "ta": "question_text_ta",
    # NOTE: do NOT add "kn" here. Kannada will come from translation tables.
}


def normalize_lang(lang: str | None) -> str:
    """
    Deterministic normalization. Never throws.
    """
    return (lang or "en").strip().lower() or "en"


def resolve_question_text(
    db: Session,
    *,
    assessment_version: str,
    question: models.Question,
    requested_lang: str | None,
) -> tuple[str, str]:
    """
    Returns: (question_text, lang_used)

    Resolution order (deterministic, non-breaking):
    1) question_translations row for requested locale
    2) legacy column (question_text_hi/ta) if requested locale is in LEGACY_LANG_FIELD_MAP
    3) English legacy column question_text_en
    """
    req = normalize_lang(requested_lang)

    # 1) Translation table (supports unlimited locales)
    if req != "en":
        tr = (
            db.query(models.QuestionTranslation)
            .filter(models.QuestionTranslation.assessment_version == assessment_version)
            .filter(models.QuestionTranslation.question_id == question.id)
            .filter(models.QuestionTranslation.locale == req)
            .first()
        )
        if tr and (tr.question_text or "").strip():
            return tr.question_text.strip(), req

    # 2) Legacy column fallback (hi/ta/en)
    if req in LEGACY_LANG_FIELD_MAP:
        col = LEGACY_LANG_FIELD_MAP[req]
        text_in_lang = getattr(question, col, None)
        if text_in_lang and str(text_in_lang).strip():
            return str(text_in_lang).strip(), req

    # 3) English hard fallback (never empty if DB has en populated)
    en = getattr(question, "question_text_en", None) or ""
    return str(en).strip(), "en"
