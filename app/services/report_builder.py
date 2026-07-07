"""
PR18 - Report Builder (Canonical Contract)

Goals:
- Deterministic: same inputs => same report structure (copy can change via CMS)
- Projection-based: student/counsellor/admin views from one pipeline
- Mobile + desktop friendly: section/block model
- Beta: JSON + HTML supported; PDF deferred
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Iterable

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app import schemas
from app import models  # expects models.Assessment, models.AssessmentResult, models.Student, models.ExplainabilityContent
import re

# Strict allowlist keys (do NOT expand casually)
_ALLOWED_CAREER_NAME_KEYS = ("career_name", "title", "name")
_ALLOWED_CLUSTER_NAME_KEYS = ("cluster_name", "cluster")

# Basic safety filters (student-safe guard also checks later)
_FORBIDDEN_TOKENS = ("career_id", "facet_id", "aq_id", "score", "weight", "%")

# 5-star fit indicator — same mapping locked on the frontend
_FIT_BAND_STARS = {
    "high_potential": 5,
    "strong": 4,
    "promising": 3,
    "developing": 2,
    "exploring": 1,
}

# Fallback labels — mirror the fit_band_config seed (admin can override in DB)
_FIT_BAND_FALLBACK_LABELS = {
    "high_potential": "High Potential",
    "strong": "Strong",
    "promising": "Promising",
    "developing": "Developing",
    "exploring": "Exploring",
}

# Careers shown in the downloadable PDF summary per tier
_DOWNLOAD_SUMMARY_CAREER_LIMITS = {"free": 5, "paid": 9}


def _normalize_text(s: str) -> str:
    """Normalize whitespace + strip risky junk without being destructive."""
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _extract_first_str(d: dict, keys: Iterable[str]) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return _normalize_text(v)
    return None


def _dedup_preserve_order(seq: list[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def extract_display_lists_from_recommended_careers(rc: Any) -> Tuple[list[str], list[str]]:
    """
    Robust extraction that tolerates multiple shapes:
      - list[str]
      - list[dict]
      - dict with nested list under common keys
    Output:
      clusters: list[str]
      careers: list[str]
    """

    clusters: list[str] = []
    careers: list[str] = []

    # Unwrap common nested shapes: {"items": [...]}, {"careers": [...]}, etc.
    if isinstance(rc, dict):
        for candidate_key in ("items", "careers", "recommended_careers", "results"):
            if isinstance(rc.get(candidate_key), list):
                rc = rc[candidate_key]
                break

    if not isinstance(rc, list):
        return clusters, careers  # empty, deterministic

    for item in rc:
        # ------------------------
        # Case 1: plain string
        # ------------------------
        if isinstance(item, str):
            name = _normalize_text(item)
            if name:
                careers.append(name)
            continue

        # ------------------------
        # Case 2: dict item
        # ------------------------
        if isinstance(item, dict):
            # Handle nested containers inside list items
            for nested_key in ("items", "careers", "recommended_careers", "results"):
                nested_val = item.get(nested_key)
                if isinstance(nested_val, list):
                    sub_clusters, sub_careers = extract_display_lists_from_recommended_careers(nested_val)
                    clusters.extend(sub_clusters)
                    careers.extend(sub_careers)
                    break
            else:
                # Normal record: extract safe display fields only

                # Career name
                c_name = _extract_first_str(item, _ALLOWED_CAREER_NAME_KEYS)
                if c_name:
                    lowered = c_name.lower()
                    if not any(tok in lowered for tok in _FORBIDDEN_TOKENS):
                        careers.append(c_name)

                # Cluster name (optional)
                cl_name = _extract_first_str(item, _ALLOWED_CLUSTER_NAME_KEYS)
                if cl_name:
                    lowered = cl_name.lower()
                    if not any(tok in lowered for tok in _FORBIDDEN_TOKENS):
                        clusters.append(cl_name)

    clusters = _dedup_preserve_order(clusters)
    careers = _dedup_preserve_order(careers)

    return clusters, careers

# ----------------------------
# Exceptions (router maps to HTTP status)
# ----------------------------

class ReportNotReadyError(Exception):
    pass


class ReportSourceNotFoundError(Exception):
    pass


# ----------------------------
# Source resolution (deterministic snapshot)
# ----------------------------

def resolve_report_source(
    db: Session,
    *,
    student_id: int,
    assessment_id: Optional[int] = None,
) -> Tuple["models.Student", "models.Assessment", "models.AssessmentResult"]:
    """
    Deterministic source rule (locked):
    - If assessment_id provided => use it (must belong to student)
    - Else => latest assessment by submitted_at desc
    """
    student = db.query(models.Student).filter(models.Student.id == student_id).first()
    if not student:
        raise ReportSourceNotFoundError(f"Student not found: {student_id}")

    # Students table has user_id; Assessments are tied to users.id (per your DB)
    user_id = student.user_id
    if not user_id:
        raise ReportSourceNotFoundError(f"Student has no user_id linked: {student_id}")

    q = db.query(models.Assessment).filter(models.Assessment.user_id == user_id)

    if assessment_id is not None:
        assessment = q.filter(models.Assessment.id == assessment_id).first()
        if not assessment:
            raise ReportSourceNotFoundError(f"Assessment not found: {assessment_id}")
    else:
        assessment = q.order_by(desc(models.Assessment.submitted_at)).first()
        if not assessment:
            raise ReportSourceNotFoundError(f"No assessments for student_id={student_id}")

    result = (
        db.query(models.AssessmentResult)
        .filter(models.AssessmentResult.assessment_id == assessment.id)
        .first()
    )
    if not result:
        # Beta choice: treat as report not ready
        raise ReportNotReadyError(f"AssessmentResult missing for assessment_id={assessment.id}")

    return student, assessment, result


# ----------------------------
# CMS explainability resolver (PR16)
# ----------------------------

def resolve_explainability_text(
    db: Session,
    *,
    version: str,
    locale: str,
    explanation_key: str,
) -> str:
    """
    Deterministic fallback:
    1) requested locale
    2) 'en'
    3) fixed placeholder
    """
    row = (
        db.query(models.ExplainabilityContent)
        .filter(
            models.ExplainabilityContent.version == version,
            models.ExplainabilityContent.locale == locale,
            models.ExplainabilityContent.explanation_key == explanation_key,
            models.ExplainabilityContent.is_active == True,  # noqa: E712
        )
        .first()
    )
    if row:
        return row.text

    if locale != "en":
        row_en = (
            db.query(models.ExplainabilityContent)
            .filter(
                models.ExplainabilityContent.version == version,
                models.ExplainabilityContent.locale == "en",
                models.ExplainabilityContent.explanation_key == explanation_key,
                models.ExplainabilityContent.is_active == True,  # noqa: E712
            )
            .first()
        )
        if row_en:
            return row_en.text

    return "Explanation coming soon."


# ----------------------------
# Download-summary helpers (PDF variant)
# ----------------------------

def _shorten(text: str, max_len: int = 240) -> str:
    """Trim long copy to a short, word-boundary-safe snippet for the PDF card."""
    t = _normalize_text(text)
    if len(t) <= max_len:
        return t
    cut = t[:max_len].rsplit(" ", 1)[0].rstrip(",;:.")
    return cut + "…"


def resolve_fit_band_label(db: Session, band_key: str | None) -> str | None:
    """
    Resolve the student-facing band label the same way the frontend does:
    fit_band_config.label (admin-adjustable), falling back to the seeded defaults.
    """
    if not band_key:
        return None
    try:
        row = (
            db.query(models.FitBandConfig)
            .filter(models.FitBandConfig.band_key == band_key)
            .first()
        )
        if row and row.label:
            return str(row.label)
    except Exception:
        pass  # table may be absent in minimal environments; fall back
    return _FIT_BAND_FALLBACK_LABELS.get(band_key)


def extract_career_entries_from_recommended_careers(rc: Any) -> list[dict]:
    """
    Structured (allowlist-only) extraction for the PDF download summary.
    Each entry carries ONLY display-safe fields:
      title, fit_band_key, description, cluster
    plus career_id — an internal join key for locale-aware content re-resolution
    (never rendered; the snapshot stores it because project_student_safe
    allowlists it).
    Everything else in the stored payload (salary, pathways, matched_keyskills,
    automation risk, future outlook, explainability, …) is dropped by construction.
    """
    entries: list[dict] = []

    if isinstance(rc, dict):
        for candidate_key in ("items", "careers", "recommended_careers", "results"):
            if isinstance(rc.get(candidate_key), list):
                rc = rc[candidate_key]
                break

    if not isinstance(rc, list):
        return entries

    seen_titles: set[str] = set()
    for item in rc:
        if isinstance(item, str):
            title = _normalize_text(item)
            if title and title not in seen_titles:
                seen_titles.add(title)
                entries.append({"title": title, "fit_band_key": None, "description": None, "cluster": None, "career_id": None})
            continue

        if not isinstance(item, dict):
            continue

        # Tolerate nested containers inside list items
        for nested_key in ("items", "careers", "recommended_careers", "results"):
            nested_val = item.get(nested_key)
            if isinstance(nested_val, list):
                entries.extend(extract_career_entries_from_recommended_careers(nested_val))
                break
        else:
            title = _extract_first_str(item, _ALLOWED_CAREER_NAME_KEYS)
            if not title or title in seen_titles:
                continue
            if any(tok in title.lower() for tok in _FORBIDDEN_TOKENS):
                continue
            seen_titles.add(title)

            band_key = item.get("fit_band_key")
            band_key = band_key if band_key in _FIT_BAND_STARS else None

            description = item.get("description")
            description = _shorten(description) if isinstance(description, str) and description.strip() else None

            cluster = _extract_first_str(item, _ALLOWED_CLUSTER_NAME_KEYS)

            career_id = item.get("career_id")
            career_id = career_id if isinstance(career_id, int) else None

            entries.append(
                {
                    "title": title,
                    "fit_band_key": band_key,
                    "description": description,
                    "cluster": cluster,
                    "career_id": career_id,
                }
            )

    return entries


# ----------------------------
# Report Builder (canonical ReportDocument)
# ----------------------------

def build_report_document(
    db: Session,
    *,
    student: "models.Student",
    assessment: "models.Assessment",
    assessment_result: "models.AssessmentResult",
    view: str,
    locale: str,
    tier: str = "free",
    variant: str = "full",
) -> schemas.ReportDocument:
    """
    Build the canonical report document:
    - sections[] containing renderable blocks
    - no internal IDs / raw scoring in student view
    - can be expanded later without breaking contract

    tier: "free" | "paid" — resolved by the router from the student's User.tier
          (only affects the download_summary variant: 5 vs 9 careers)
    variant:
      - "full" (default): existing on-screen section set, unchanged
      - "download_summary": reduced section set for the downloadable PDF
        (summary, careers, cluster_signals, return_to_account)
    """

    # Choose a stable content versioning rule:
    # For beta: use assessment.assessment_version as the CMS version key.
    cms_version = assessment.assessment_version

    meta = schemas.ReportMeta(
        student_id=student.id,
        assessment_id=assessment.id,
        assessment_version=assessment.assessment_version,
        scoring_config_version=assessment.scoring_config_version,
        content_version=(assessment_result.content_version or assessment.assessment_version),
        generated_at=datetime.utcnow(),
        locale=locale,
        view=view,  # already enforced by router for role
    )

    sections: List[schemas.ReportSection] = []

    # --- Summary section (qualitative) ---
    sections.append(
        schemas.ReportSection(
            type="summary",
            title="Your Career Fit Summary",
            blocks=[
                schemas.ReportBlock(
                    kind="paragraph",
                    text="Here are your top matching areas based on your latest assessment.",
                )
            ],
        )
    )

    # --- Download-summary variant (PDF): reduced, deliberately lightweight ---
    if variant == "download_summary":
        ui = _get_pdf_ui_strings(locale)
        content_lang = locale_to_content_lang(locale)

        # 1) Summary section — same structure, locale-aware copy
        #    (for "en" these strings are identical to the section appended above)
        sections[0] = schemas.ReportSection(
            type="summary",
            title=ui["summary_title"],
            blocks=[schemas.ReportBlock(kind="paragraph", text=ui["summary_body"])],
        )

        entries = extract_career_entries_from_recommended_careers(
            assessment_result.recommended_careers or []
        )
        max_careers = _DOWNLOAD_SUMMARY_CAREER_LIMITS.get(tier, _DOWNLOAD_SUMMARY_CAREER_LIMITS["free"])
        entries = entries[:max_careers]

        # The snapshot is always English (computed with lang="en" at submit time),
        # so non-English locales re-resolve description / indian_job_title from
        # career_content and cluster names from cluster_translations here.
        if content_lang != "en":
            _localize_career_entries(db, entries, content_lang)
            cluster_names = {e["cluster"] for e in entries if e.get("cluster")}
            translated_clusters = _get_cluster_name_translations(db, cluster_names, content_lang)
            for e in entries:
                if e.get("cluster"):
                    e["cluster"] = translated_clusters.get(e["cluster"], e["cluster"])

        # 2) Careers — title + fit band + short description + cluster ONLY
        #    (career title stays English by design, product-wide behavior)
        career_blocks: List[schemas.ReportBlock] = []
        for e in entries:
            career_blocks.append(
                schemas.ReportBlock(
                    kind="career_card",
                    career_title=e["title"],
                    fit_band_key=e["fit_band_key"],
                    fit_band_label=resolve_fit_band_label(db, e["fit_band_key"]),
                    description=e["description"],
                    cluster_name=e["cluster"],
                    indian_job_title=e.get("indian_job_title"),
                )
            )
        if career_blocks:
            sections.append(
                schemas.ReportSection(
                    type="careers",
                    title=ui["careers_title"],
                    blocks=career_blocks,
                )
            )

        # 3) Cluster signals — same grouping as ClusterStrengthMap (group + count)
        cluster_counts: Dict[str, int] = {}
        for e in entries:
            if e["cluster"]:
                cluster_counts[e["cluster"]] = cluster_counts.get(e["cluster"], 0) + 1
        if cluster_counts:
            signal_items = [
                (
                    ui["cluster_signal_item_singular"] if count == 1 else ui["cluster_signal_item_plural"]
                ).format(name=name, count=count)
                for name, count in cluster_counts.items()
            ]
            sections.append(
                schemas.ReportSection(
                    type="cluster_signals",
                    title=ui["cluster_signals_title"],
                    blocks=[schemas.ReportBlock(kind="bullets", items=signal_items)],
                )
            )

        # 4) Closing CTA + disclaimer
        sections.append(
            schemas.ReportSection(
                type="return_to_account",
                title=ui["closing_title"],
                blocks=[
                    schemas.ReportBlock(kind="callout", text=ui["closing_callout"]),
                    schemas.ReportBlock(kind="paragraph", text=ui["closing_disclaimer"]),
                ],
            )
        )

        doc = schemas.ReportDocument(report_meta=meta, sections=sections)

        # Guard rail runs unconditionally for the downloadable artifact —
        # it is student-facing regardless of who requested it.
        _assert_student_safe(doc)
        return doc

    # --- Clusters & Careers from assessment_result ---
    # assessment_result.recommended_careers is jsonb; keep it flexible.
    # We will safely extract names only.

    rc = assessment_result.recommended_careers or []

    clusters, careers = extract_display_lists_from_recommended_careers(rc)

    if isinstance(rc, list):
        for item in rc:
            # Support both strings and small dicts
            if isinstance(item, str):
                careers.append(item)
            elif isinstance(item, dict):
                # try common keys safely
                name = item.get("career_name") or item.get("title") or item.get("name")
                if name:
                    careers.append(str(name))
                # optional cluster name if present
                c = item.get("cluster_name") or item.get("cluster")
                if c:
                    clusters.append(str(c))

    # De-dup, keep order
    def dedup(seq: List[str]) -> List[str]:
        seen = set()
        out = []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    clusters = dedup(clusters)
    careers = dedup(careers)

    if clusters:
        sections.append(
            schemas.ReportSection(
                type="clusters",
                title="Top Career Clusters",
                blocks=[schemas.ReportBlock(kind="cluster_list", items=clusters)],
            )
        )

    if careers:
        sections.append(
            schemas.ReportSection(
                type="careers",
                title="Top Career Options",
                blocks=[schemas.ReportBlock(kind="career_list", items=careers)],
            )
        )

    # --- Explainability section (CMS-driven) ---
    # For beta, include a few placeholder keys; later this will be derived from
    # facets/AQs/skills without exposing internals to students.
    explain_keys = [
        "report.summary",
        "report.clusters",
        "report.careers",
    ]

    explain_blocks: List[schemas.ReportBlock] = []
    for k in explain_keys:
        explain_blocks.append(
            schemas.ReportBlock(
                kind="paragraph",
                explanation_key=k,
                explanation_text=resolve_explainability_text(
                    db, version=cms_version, locale=locale, explanation_key=k
                ),
            )
        )

    sections.append(
        schemas.ReportSection(
            type="explainability",
            title="Why these fit you",
            blocks=explain_blocks,
        )
    )

    # --- Coming soon section (per your note: no data yet for next steps/growth tips) ---
    sections.append(
        schemas.ReportSection(
            type="coming_soon",
            title="Next steps & growth tips",
            blocks=[
                schemas.ReportBlock(
                    kind="callout",
                    text="Coming soon: personalized next steps and growth tips will be added in a future release.",
                )
            ],
        )
    )

    doc = schemas.ReportDocument(report_meta=meta, sections=sections)

    # Enforce student-safe guarantees (guard rail)
    if view == "student":
        _assert_student_safe(doc)

    return doc

def normalize_locale(locale: str) -> str:
    """
    Deterministic locale normalization:
    - trims whitespace
    - maps common variants to canonical ones
    - does not depend on external libraries
    """
    if not locale:
        return "en"
    loc = locale.strip()

    # canonicalize separators
    loc = loc.replace("_", "-")

    # normalize common english variants
    if loc.lower().startswith("en"):
        return "en"

    # Kannada examples:
    # allow "kn" to map to "kn-IN" (India-first)
    if loc.lower() == "kn":
        return "kn-IN"

    # keep as-is for other locales (future-proof)
    return loc


# Report locales are BCP-47-ish ("kn-IN"), but career_content / cluster_translations
# rows are keyed by short lang codes matching languages.code ("kn").
_CONTENT_LANG_BY_LOCALE = {
    "en": "en",
    "kn-IN": "kn",
}


def locale_to_content_lang(locale: str) -> str:
    """
    Map a normalized report locale to the lang code used by content tables
    (career_content.lang, cluster_translations.locale). Unknown locales fall
    back to their primary subtag so future languages keep working ("ta-IN" -> "ta").
    """
    loc = normalize_locale(locale)
    if loc in _CONTENT_LANG_BY_LOCALE:
        return _CONTENT_LANG_BY_LOCALE[loc]
    return loc.split("-", 1)[0].lower() or "en"


# Static UI strings for the download_summary PDF, keyed by normalized locale.
# The "en" values MUST stay byte-identical to the historical hardcoded strings.
# {name}/{count} placeholders are filled via str.format.
_PDF_UI_STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        "summary_title": "Your Career Fit Summary",
        "summary_body": "Here are your top matching areas based on your latest assessment.",
        "careers_title": "Top Career Options",
        "cluster_signals_title": "Cluster Signals",
        "cluster_signal_item_singular": "{name} — {count} career",
        "cluster_signal_item_plural": "{name} — {count} careers",
        "closing_title": "See Your Full Results",
        "closing_callout": (
            "Log in to your account on the web or mobile app to explore your "
            "full results — career pathways, salary ranges, premium insights, "
            "and guided next steps."
        ),
        "closing_disclaimer": (
            "This document is a summary snapshot, not a complete record. The full "
            "assessment methodology and your detailed results are available only in "
            "your account. It is intended for personal and educational reference only "
            "and does not constitute professional career counselling advice."
        ),
    },
    "kn-IN": {
        "summary_title": "ನಿಮ್ಮ ವೃತ್ತಿ ಹೊಂದಾಣಿಕೆಯ ಸಾರಾಂಶ",
        "summary_body": "ನಿಮ್ಮ ಇತ್ತೀಚಿನ ಮೌಲ್ಯಮಾಪನದ ಆಧಾರದ ಮೇಲೆ ನಿಮಗೆ ಹೆಚ್ಚು ಹೊಂದುವ ಕ್ಷೇತ್ರಗಳು ಇಲ್ಲಿವೆ.",
        "careers_title": "ಉನ್ನತ ವೃತ್ತಿ ಆಯ್ಕೆಗಳು",
        "cluster_signals_title": "ವೃತ್ತಿ ಕ್ಷೇತ್ರ ಸೂಚಕಗಳು",
        "cluster_signal_item_singular": "{name} — {count} ವೃತ್ತಿ",
        "cluster_signal_item_plural": "{name} — {count} ವೃತ್ತಿಗಳು",
        "closing_title": "ನಿಮ್ಮ ಪೂರ್ಣ ಫಲಿತಾಂಶಗಳನ್ನು ನೋಡಿ",
        "closing_callout": (
            "ನಿಮ್ಮ ಪೂರ್ಣ ಫಲಿತಾಂಶಗಳನ್ನು — ವೃತ್ತಿ ಮಾರ್ಗಗಳು, ವೇತನ ಶ್ರೇಣಿಗಳು, ಪ್ರೀಮಿಯಂ "
            "ಒಳನೋಟಗಳು ಮತ್ತು ಮಾರ್ಗದರ್ಶಿತ ಮುಂದಿನ ಹೆಜ್ಜೆಗಳನ್ನು — ನೋಡಲು ವೆಬ್ ಅಥವಾ "
            "ಮೊಬೈಲ್ ಆ್ಯಪ್‌ನಲ್ಲಿ ನಿಮ್ಮ ಖಾತೆಗೆ ಲಾಗಿನ್ ಆಗಿ."
        ),
        "closing_disclaimer": (
            "ಈ ದಾಖಲೆಯು ಸಾರಾಂಶ ರೂಪದ ಚಿತ್ರಣ ಮಾತ್ರ; ಸಂಪೂರ್ಣ ದಾಖಲೆ ಅಲ್ಲ. ಪೂರ್ಣ "
            "ಮೌಲ್ಯಮಾಪನ ವಿಧಾನ ಮತ್ತು ನಿಮ್ಮ ವಿವರವಾದ ಫಲಿತಾಂಶಗಳು ನಿಮ್ಮ ಖಾತೆಯಲ್ಲಿ ಮಾತ್ರ "
            "ಲಭ್ಯವಿವೆ. ಇದು ವೈಯಕ್ತಿಕ ಮತ್ತು ಶೈಕ್ಷಣಿಕ ಉಲ್ಲೇಖಕ್ಕಾಗಿ ಮಾತ್ರ "
            "ಉದ್ದೇಶಿಸಲಾಗಿದ್ದು, ವೃತ್ತಿಪರ ವೃತ್ತಿ ಮಾರ್ಗದರ್ಶನ ಸಲಹೆಯಾಗಿ ಪರಿಗಣಿಸಬಾರದು."
        ),
    },
}


def _get_pdf_ui_strings(locale: str) -> Dict[str, str]:
    """Resolve the download-summary UI string set; English is the hard fallback."""
    resolved = dict(_PDF_UI_STRINGS["en"])
    resolved.update(_PDF_UI_STRINGS.get(normalize_locale(locale), {}))
    return resolved


def _localize_career_entries(db: Session, entries: list[dict], content_lang: str) -> None:
    """
    Re-resolve career content in the requested language at render time.

    The recommended_careers snapshot is always computed with lang="en" at submit
    time, so localized description / indian_job_title must come from
    career_content here. Reuses career_engine._get_content (the same resolution
    the recommendations endpoint uses) — entries without a kn row keep their
    English snapshot text (per-career fallback).
    """
    from app.services.career_engine import _get_content
    from app.projections.student_safe import _strip_numbers_from_text

    career_ids = [e["career_id"] for e in entries if e.get("career_id")]
    if not career_ids:
        return

    content_by_career = _get_content(db, career_ids, content_lang)

    for e in entries:
        content = content_by_career.get(e.get("career_id"))
        if not content or content.get("lang_used") != content_lang:
            continue

        description = content.get("description")
        if isinstance(description, str) and description.strip():
            e["description"] = _shorten(_strip_numbers_from_text(description))

        indian_job_title = content.get("indian_job_title")
        if isinstance(indian_job_title, str) and indian_job_title.strip():
            e["indian_job_title"] = _normalize_text(_strip_numbers_from_text(indian_job_title))


def _get_cluster_name_translations(db: Session, names: set[str], content_lang: str) -> Dict[str, str]:
    """
    English cluster name -> translated name via cluster_translations.
    Keyed by name because the snapshot stores cluster display names, not ids.
    Missing translations simply keep the English name.
    """
    if not names or content_lang == "en":
        return {}
    try:
        rows = (
            db.query(models.CareerCluster.name, models.ClusterTranslation.name)
            .join(models.ClusterTranslation, models.ClusterTranslation.cluster_id == models.CareerCluster.id)
            .filter(models.ClusterTranslation.locale == content_lang)
            .filter(models.CareerCluster.name.in_(list(names)))
            .all()
        )
    except Exception:
        return {}  # table may be absent in minimal environments; fall back to English
    return {en: tr for en, tr in rows if isinstance(tr, str) and tr.strip()}


def _assert_student_safe(doc: schemas.ReportDocument) -> None:
    """
    Regression tripwire:
    - ensure no obvious numeric analytics leakage
    - ensure no internal IDs or score/weight tokens
    """
    forbidden_substrings = (
        "career_id",
        "facet_id",
        "aq_id",
        "raw_total",
        "scaled_0_100",
        "normalized",
        "band_breakdown",
        "cluster_scores",
        "career_scores",
        "keyskill_scores",
        "score",
        "weight",
    )

    def check_text(label: str, text: str) -> None:
        t = (text or "").lower()
        for bad in forbidden_substrings:
            if bad in t:
                raise ValueError(f"Student-safe violation: found '{bad}' in {label}")

    # Walk through all sections/blocks
    for si, sec in enumerate(doc.sections):
        check_text(f"section[{si}].title", sec.title)

        for bi, b in enumerate(sec.blocks):
            if b.text:
                check_text(f"section[{si}].block[{bi}].text", b.text)
            if b.explanation_key:
                check_text(f"section[{si}].block[{bi}].explanation_key", b.explanation_key)
            if b.explanation_text:
                check_text(f"section[{si}].block[{bi}].explanation_text", b.explanation_text)

            # career_card fields (PDF download summary)
            if b.career_title:
                check_text(f"section[{si}].block[{bi}].career_title", b.career_title)
            if b.indian_job_title:
                check_text(f"section[{si}].block[{bi}].indian_job_title", b.indian_job_title)
            if b.fit_band_label:
                check_text(f"section[{si}].block[{bi}].fit_band_label", b.fit_band_label)
            if b.description:
                check_text(f"section[{si}].block[{bi}].description", b.description)
            if b.cluster_name:
                check_text(f"section[{si}].block[{bi}].cluster_name", b.cluster_name)
            if b.fit_band_key is not None and b.fit_band_key not in _FIT_BAND_STARS:
                raise ValueError(
                    f"Student-safe violation: unknown fit_band_key in section[{si}].block[{bi}]"
                )

            # items must be list[str] only and must not contain forbidden tokens
            if b.items is not None:
                if not isinstance(b.items, list) or any(not isinstance(x, str) for x in b.items):
                    raise ValueError(f"Student-safe violation: non-string items in section[{si}].block[{bi}]")
                for ii, item in enumerate(b.items):
                    check_text(f"section[{si}].block[{bi}].items[{ii}]", item)


# ----------------------------
# HTML renderer (derived from canonical doc)
# ----------------------------

def render_report_html(doc: schemas.ReportDocument) -> str:
    """
    Minimal beta HTML renderer:
    - single column
    - readable in mobile and desktop
    - PDF can be generated later from this HTML
    """
    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    parts: List[str] = []
    parts.append("<!doctype html><html><head>")
    parts.append("<meta charset='utf-8'/>")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'/>")
    parts.append("<title>Career Report</title>")
    parts.append("</head><body style='font-family:Arial,sans-serif;max-width:900px;margin:0 auto;padding:16px;'>")

    parts.append(f"<h1 style='margin-top:0;'>Career Report</h1>")
    parts.append(
        f"<p><b>Assessment:</b> {esc(doc.report_meta.assessment_version)} "
        f" | <b>Generated:</b> {doc.report_meta.generated_at.isoformat()} "
        f" | <b>Locale:</b> {esc(doc.report_meta.locale)}</p>"
    )

    for sec in doc.sections:
        parts.append(f"<h2>{esc(sec.title)}</h2>")
        for b in sec.blocks:
            if b.kind in ("paragraph", "callout"):
                text = b.text or b.explanation_text or ""
                if b.kind == "callout":
                    parts.append(f"<div style='padding:12px;border:1px solid #ddd;border-radius:8px;'>{esc(text)}</div>")
                else:
                    parts.append(f"<p>{esc(text)}</p>")
            elif b.kind in ("bullets", "career_list", "cluster_list"):
                items = b.items or []
                parts.append("<ul>")
                for it in items:
                    parts.append(f"<li>{esc(it)}</li>")
                parts.append("</ul>")

    parts.append("</body></html>")
    return "".join(parts)


# ----------------------------
# PDF renderer (download summary) — separate from render_report_html on purpose
# ----------------------------

def _render_fit_stars_html(band_key: str | None) -> str:
    """
    Inline-HTML 5-star fit indicator (same mapping as the frontend):
    high_potential=5, strong=4, promising=3, developing=2, exploring=1.
    Filled stars in --color-primary, unfilled at ~22% opacity (via rgba).
    """
    filled = _FIT_BAND_STARS.get(band_key or "", 0)
    if filled <= 0:
        return ""
    empty = 5 - filled
    return (
        "<span style='font-size:13px;letter-spacing:2px;'>"
        f"<span style='color:#2540D9;'>{'★' * filled}</span>"
        f"<span style='color:rgba(37,64,217,0.22);'>{'★' * empty}</span>"
        "</span>"
    )


def render_report_pdf_html(doc: schemas.ReportDocument) -> str:
    """
    Print-friendly HTML for the downloadable PDF summary (WeasyPrint input).

    - Brand tokens from palette-spec.md:
        --color-primary #2540D9 (headings/accents)
        --color-ink-900 #111521 (body text)
        --color-paper   #F8FAF9 (page background)
    - Kannada-safe font stack: 'Noto Sans Kannada', 'Noto Sans', Arial, sans-serif
      (fonts installed at OS level in the backend Docker image)
    - Do NOT reuse for the on-screen format=html path; that stays render_report_html.
    """

    def esc(s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    font_stack = "'Noto Sans Kannada', 'Noto Sans', Arial, sans-serif"

    parts: List[str] = []
    parts.append("<!doctype html><html><head><meta charset='utf-8'/>")
    parts.append("<title>Career Report Summary</title>")
    parts.append(
        "<style>"
        "@page { size: A4; margin: 18mm 16mm; }"
        f"body {{ font-family: {font_stack}; background: #F8FAF9; color: #111521; "
        "font-size: 11.5px; line-height: 1.55; margin: 0; }"
        "h1 { color: #2540D9; font-size: 21px; margin: 0 0 2px 0; }"
        "h2 { color: #2540D9; font-size: 14px; margin: 18px 0 8px 0; "
        "border-bottom: 1.5px solid #2540D9; padding-bottom: 3px; }"
        ".meta { color: #111521; opacity: 0.65; font-size: 9.5px; margin-bottom: 4px; }"
        ".card { border: 1px solid rgba(37,64,217,0.18); border-radius: 8px; "
        "padding: 9px 12px; margin: 0 0 8px 0; background: #ffffff; page-break-inside: avoid; }"
        ".card-title { font-weight: bold; font-size: 12.5px; color: #111521; }"
        ".band-label { color: #2540D9; font-size: 10.5px; font-weight: bold; margin-left: 6px; }"
        ".job-title { font-size: 10.5px; opacity: 0.85; margin-top: 1px; }"
        ".cluster { opacity: 0.7; font-size: 10px; margin-top: 1px; }"
        ".desc { margin-top: 4px; }"
        ".callout { border-left: 3px solid #2540D9; background: rgba(37,64,217,0.06); "
        "padding: 8px 12px; border-radius: 4px; margin: 6px 0; }"
        ".disclaimer { font-size: 9px; opacity: 0.7; margin-top: 8px; }"
        "ul { margin: 4px 0 4px 18px; padding: 0; }"
        "li { margin-bottom: 2px; }"
        "</style></head><body>"
    )

    parts.append("<h1>Career Report — Summary</h1>")
    parts.append(
        f"<p class='meta'>Generated: {doc.report_meta.generated_at.strftime('%d %b %Y')}"
        f" &nbsp;•&nbsp; Assessment version: {esc(doc.report_meta.assessment_version)}"
        f" &nbsp;•&nbsp; Locale: {esc(doc.report_meta.locale)}</p>"
    )

    for sec in doc.sections:
        parts.append(f"<h2>{esc(sec.title)}</h2>")
        for b in sec.blocks:
            if b.kind == "career_card":
                parts.append("<div class='card'>")
                parts.append(
                    "<div>"
                    f"<span class='card-title'>{esc(b.career_title or '')}</span>"
                    f" &nbsp;{_render_fit_stars_html(b.fit_band_key)}"
                    + (f"<span class='band-label'>{esc(b.fit_band_label)}</span>" if b.fit_band_label else "")
                    + "</div>"
                )
                if b.indian_job_title:
                    parts.append(f"<div class='job-title'>{esc(b.indian_job_title)}</div>")
                if b.cluster_name:
                    parts.append(f"<div class='cluster'>{esc(b.cluster_name)}</div>")
                if b.description:
                    parts.append(f"<div class='desc'>{esc(b.description)}</div>")
                parts.append("</div>")
            elif b.kind == "callout":
                parts.append(f"<div class='callout'>{esc(b.text or b.explanation_text or '')}</div>")
            elif b.kind == "paragraph":
                css_class = " class='disclaimer'" if sec.type == "return_to_account" else ""
                parts.append(f"<p{css_class}>{esc(b.text or b.explanation_text or '')}</p>")
            elif b.kind in ("bullets", "career_list", "cluster_list"):
                parts.append("<ul>")
                for it in (b.items or []):
                    parts.append(f"<li>{esc(it)}</li>")
                parts.append("</ul>")

    parts.append("</body></html>")
    return "".join(parts)
