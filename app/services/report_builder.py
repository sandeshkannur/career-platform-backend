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
) -> schemas.ReportDocument:
    """
    Build the canonical report document:
    - sections[] containing renderable blocks
    - no internal IDs / raw scoring in student view
    - can be expanded later without breaking contract
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
        "%",
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
