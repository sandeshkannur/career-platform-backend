# app/routers/chapter_content.py
"""
Chapter content delivery — serves chapter intro/reveal/cta texts
and milestone messages from explanation_translations table.

Role gate: none — content is not student-specific.
Tables read: explanation_translations
Mounted at: /v1/assessments (prefix set in main.py)
Endpoint: GET /v1/assessments/chapter-content?lang=en&content_version=v1

Frontend calls this once when assessment starts and caches locally.
Language fallback: requested locale -> en -> [missing:key] placeholder.
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.deps import get_db
from app import models

router = APIRouter(tags=["Chapter Content"])

CHAPTER_IDS = [1, 2, 3, 4]

CHAPTER_KEYS = [
    "chapter.1.title", "chapter.1.intro", "chapter.1.reveal", "chapter.1.cta",
    "chapter.2.title", "chapter.2.intro", "chapter.2.reveal", "chapter.2.cta",
    "chapter.3.title", "chapter.3.intro", "chapter.3.reveal", "chapter.3.cta",
    "chapter.4.title", "chapter.4.intro", "chapter.4.reveal", "chapter.4.cta",
    "assessment.milestone.20",
    "assessment.milestone.50",
    "assessment.milestone.80",
]


@router.get("/chapter-content")
def get_chapter_content(
    lang: str = Query("en", description="Locale code: en, kn, hi, ta"),
    content_version: str = Query("v1", description="Content version, e.g. v1"),
    db: Session = Depends(get_db),
):
    """
    Returns all chapter intro/reveal/cta texts and milestone messages
    in the requested language, falling back to English if translation missing.
    """
    requested_lang = (lang or "en").strip().lower()

    # Fetch all matching rows for requested locale + English fallback in one query
    rows = db.execute(
        select(
            models.ExplanationTranslation.explanation_key,
            models.ExplanationTranslation.locale,
            models.ExplanationTranslation.text,
        ).where(
            models.ExplanationTranslation.content_version == content_version,
            models.ExplanationTranslation.locale.in_([requested_lang, "en"]),
            models.ExplanationTranslation.explanation_key.in_(CHAPTER_KEYS),
            models.ExplanationTranslation.is_active == True,
        )
    ).all()

    # Build lookup: explanation_key -> {locale: text}
    lookup: dict = {}
    for row in rows:
        key, locale, txt = str(row[0]), str(row[1]), str(row[2])
        if key not in lookup:
            lookup[key] = {}
        lookup[key][locale] = txt

    def resolve(key: str) -> tuple:
        """Return (text, lang_used) with English fallback."""
        entry = lookup.get(key, {})
        if requested_lang in entry:
            return entry[requested_lang], requested_lang
        if "en" in entry:
            return entry["en"], "en"
        return f"[missing:{key}]", "en"

    lang_used = "en"

    # Build chapters payload
    chapters = {}
    for ch_id in CHAPTER_IDS:
        ch = str(ch_id)
        title_text,  tl = resolve(f"chapter.{ch}.title")
        intro_text,  il = resolve(f"chapter.{ch}.intro")
        reveal_text, rl = resolve(f"chapter.{ch}.reveal")
        cta_text,    cl = resolve(f"chapter.{ch}.cta")

        if requested_lang in (tl, il, rl, cl):
            lang_used = requested_lang

        chapters[ch] = {
            "title":  title_text,
            "intro":  intro_text,
            "reveal": reveal_text,
            "cta":    cta_text,
        }

    # Build milestones payload
    milestones = {}
    for pct in ["20", "50", "80"]:
        m_text, ml = resolve(f"assessment.milestone.{pct}")
        if ml == requested_lang:
            lang_used = requested_lang
        milestones[pct] = m_text

    resp = {
        "lang": requested_lang,
        "lang_used": lang_used,
        "content_version": content_version,
        "chapters": chapters,
        "milestones": milestones,
    }

    return JSONResponse(
        content=resp,
        media_type="application/json; charset=utf-8",
    )
