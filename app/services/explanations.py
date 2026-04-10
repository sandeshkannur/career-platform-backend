# backend/app/services/explanations.py

from sqlalchemy.orm import Session
from sqlalchemy import select
from app import models
import logging
import re
from app.services.scoring import (
    compute_career_scores,
    compute_cluster_scores,
    get_student_keyskill_scores,
)

logger = logging.getLogger(__name__)

def _contains_numbers(text: str) -> bool:
    # blocks digits and percent patterns
    return bool(re.search(r"\d", text)) or ("%" in text)

# --- PR43: Tier Narrative Guardrails (content safety) ---
# These narrative blocks must never read like grades/exams.
_GRADELIKE_PATTERN = re.compile(
    r"\b("
    r"grade|marks?|percentile|percent|score|scored|pass|fail|topper|rank|ranking"
    r")\b|%|\b\d{1,3}\s*/\s*\d{1,3}\b",
    re.IGNORECASE,
)

def _contains_gradelike_language(text: str) -> bool:
    if not text:
        return False
    return bool(_GRADELIKE_PATTERN.search(text))

def _is_tier_narrative_key(explanation_key: str) -> bool:
    # PR43 scope: tier/fit-band narratives used by paid analytics
    # Keep tight to avoid breaking other CMS copy.
    if not explanation_key:
        return False
    return explanation_key.startswith("paid.career.") or explanation_key.startswith("paid.cluster.")


def resolve_cms_text(
    db,
    version: str,
    locale: str,
    explanation_key: str,
    *,
    allow_numbers: bool,
) -> str:
    """
    Resolve CMS text from explainability_content by (version, locale, explanation_key).
    Fallback order:
      1) (version, locale, key)
      2) (version, 'en', key)
      3) placeholder
    Safety:
      - If allow_numbers is False, reject CMS text that contains numbers.
    """
    # Import inside to avoid circular imports
    from app.models import ExplainabilityContent

    row = (
        db.query(ExplainabilityContent)
        .filter(
            ExplainabilityContent.version == version,
            ExplainabilityContent.locale == locale,
            ExplainabilityContent.explanation_key == explanation_key,
            ExplainabilityContent.is_active == True,  # noqa: E712
        )
        .first()
    )

    if not row and locale != "en":
        row = (
            db.query(ExplainabilityContent)
            .filter(
                ExplainabilityContent.version == version,
                ExplainabilityContent.locale == "en",
                ExplainabilityContent.explanation_key == explanation_key,
                ExplainabilityContent.is_active == True,  # noqa: E712
            )
            .first()
        )

    if not row:
        logger.warning(
            "CMS missing: version=%s locale=%s key=%s",
            version,
            locale,
            explanation_key,
        )
        return f"[missing:{explanation_key}]"

    text = (row.text or "").strip()
    if not text:
        logger.warning(
            "CMS empty: version=%s locale=%s key=%s",
            version,
            locale,
            explanation_key,
        )
        return f"[missing:{explanation_key}]"

    # PR43: Guardrails for tier narrative content (never present as grades/exams)
    if (
        _is_tier_narrative_key(explanation_key)
        and _contains_gradelike_language(text)
    ):
        logger.warning(
            "CMS rejected (tier narrative guardrail): version=%s locale=%s key=%s",
            version,
            locale,
            explanation_key,
        )
        return f"[unsafe:{explanation_key}]"
        # Original safety rule: if numbers are not allowed, reject numeric CMS copy
    if not allow_numbers and _contains_numbers(text):
        logger.warning(
            "CMS rejected (numeric text not allowed): version=%s locale=%s key=%s",
            version,
            locale,
            explanation_key,
        )
        return f"[unsafe:{explanation_key}]"
    
    if allow_numbers and _contains_numbers(text):
        logger.warning(
            "CMS contains numeric text (admin allowed, student would reject): version=%s locale=%s key=%s",
            version,
            locale,
            explanation_key,
        )

    return text

def render_text_with_slots(text: str, slots: dict) -> str:
    """
    Replace {slot_name} placeholders with provided slot values.
    Missing slots are left unchanged.
    """
    if not text:
        return text

    rendered = text
    for k, v in (slots or {}).items():
        rendered = rendered.replace("{" + str(k) + "}", str(v))
    return rendered

# --------------------------------------------------
# Template-based explanation builders
# --------------------------------------------------

# --------------------------------------------------
# Fit-band threshold cache
# Loaded from fit_band_config table on first use.
# Cleared by the admin PUT /fit-bands endpoint after saving.
# Falls back to hardcoded values if table is empty or unreadable.
# --------------------------------------------------

_FALLBACK_THRESHOLDS: list[tuple[float, str]] = [
    (80.0, "high_potential"),
    (65.0, "strong"),
    (50.0, "promising"),
    (35.0, "developing"),
    (0.0,  "exploring"),
]

# None = not yet loaded; list[tuple[min_score, band_key]] sorted descending
_band_cache: list[tuple[float, str]] | None = None


def _load_band_cache(db: Session) -> list[tuple[float, str]]:
    """Query fit_band_config and return thresholds sorted descending by min_score."""
    try:
        rows = (
            db.query(models.FitBandConfig)
            .order_by(models.FitBandConfig.sort_order)
            .all()
        )
        if rows:
            return [(float(r.min_score), r.band_key) for r in rows]
    except Exception:
        pass  # table may not exist yet during initial migration
    return []


def clear_fit_band_cache() -> None:
    """Called by the admin endpoint after updating fit_band_config rows."""
    global _band_cache
    _band_cache = None


def fit_band_from_score(score: float, db: Session | None = None) -> str:
    """
    5-level student-facing fit band.
    Thresholds are read from fit_band_config table (admin-adjustable),
    cached in memory after first load. Falls back to hardcoded values
    if the table is empty, missing, or unreadable — scoring never breaks.
    """
    global _band_cache

    try:
        s = float(score)
    except (TypeError, ValueError):
        s = 0.0

    # Populate cache on first call (or after cache clear)
    if _band_cache is None:
        if db is not None:
            loaded = _load_band_cache(db)
            _band_cache = loaded if loaded else list(_FALLBACK_THRESHOLDS)
        else:
            _band_cache = list(_FALLBACK_THRESHOLDS)

    for min_score, band_key in _band_cache:
        if s >= min_score:
            return band_key

    return "exploring"

def explain_cluster(cluster_obj, score, contributing_keyskills, band_breakdown):
    """
    PR54: Choose explanation key based on presence of top keyskills.
    """
    has_keyskills = bool(contributing_keyskills)

    if has_keyskills:
        explanation_key = "paid.cluster.with_keyskills"
        slots = {
            "cluster_name": cluster_obj.name,
            "top_keyskills": ", ".join([ks.name for ks in contributing_keyskills]),
        }
    else:
        explanation_key = "paid.cluster.no_keyskills"
        slots = {
            "cluster_name": cluster_obj.name,
        }

    return {
        "explanation_key": explanation_key,
        "slots": slots,
        "text": None,
    }


def explain_career(career_obj, score, contributing_keyskills, fit_band: str):
    """
    PR54: Choose explanation key based on fit_band.
    """
    explanation_key = f"paid.career.{fit_band}"

    slots = {
        "career_title": career_obj.title,
    }

    if contributing_keyskills:
        slots["top_keyskills"] = ", ".join([ks.name for ks in contributing_keyskills])

    return {
        "explanation_key": explanation_key,
        "slots": slots,
        "text": None,
    }


# --------------------------------------------------
# Full explanation builder – used by /paid-analytics
# --------------------------------------------------

def build_full_explanation(
    db: Session,
    student_id: int,
    *,
    version: str = "v1",
    locale: str = "en",
    allow_numbers_in_text: bool = True,
):
    """
    Computes:
        - career_scores
        - cluster_scores
        - top contributing keyskills
        - cluster band breakdown (core / supporting / auxiliary)
        - explanation strings

    Returns:
        {
            "clusters": [...],
            "careers": [...]
        }
    """

    # 1. Compute scores
    career_scores = compute_career_scores(db, student_id)
    cluster_scores = compute_cluster_scores(db, career_scores)
    student_keyskills = get_student_keyskill_scores(db, student_id)

    # 2. Fetch DB objects
    clusters = db.query(models.CareerCluster).all()
    careers = db.query(models.Career).all()
    keyskills = {ks.id: ks for ks in db.query(models.KeySkill).all()}

    # 3. Sort for top results
    top_clusters = sorted(cluster_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    top_careers = sorted(career_scores.items(), key=lambda x: x[1], reverse=True)[:5]

    cluster_output = []
    career_output = []

    # ---------------------------
    # CLUSTER EXPLANATIONS
    # ---------------------------
    for cluster_id, score in top_clusters:
        cluster = next((c for c in clusters if c.id == cluster_id), None)
        if not cluster:
            continue

        # student keyskills that belong to this cluster
        contributing = []
        for ks_id, val in student_keyskills.items():
            if val <= 0:
                continue
            ks_obj = keyskills.get(ks_id)
            if not ks_obj:
                continue
            if ks_obj.cluster_id == cluster_id:
                contributing.append(ks_obj)
        contributing = contributing[:3]

        # --- cluster band breakdown (core/supporting/auxiliary) ---
        cluster_careers = [c for c in careers if c.cluster_id == cluster_id]

        band_contrib = {"core": 0.0, "supporting": 0.0, "auxiliary": 0.0}

        for career in cluster_careers:
            ks_rows = db.execute(
                select(
                    models.career_keyskill_association.c.keyskill_id,
                    models.career_keyskill_association.c.weight_percentage,
                ).where(
                    models.career_keyskill_association.c.career_id == career.id
                )
            ).all()

            for ks_id, weight in ks_rows:
                # Only count weights for keyskills the student actually has
                if student_keyskills.get(ks_id, 0) <= 0:
                    continue

                # Guard: legacy rows may have NULL weight_percentage
                if weight is None:
                    continue

                # classify into bands using weightage rationale
                if weight >= 30:
                    band = "core"
                elif weight >= 20:
                    band = "supporting"
                else:
                    band = "auxiliary"

                band_contrib[band] += float(weight)

        total_band = sum(band_contrib.values())
        if total_band > 0:
            band_breakdown = {
                band: round((val / total_band) * 100, 2)
                for band, val in band_contrib.items()
                if val > 0
            }
        else:
            band_breakdown = {}

        cluster_item = {
            "cluster_id": cluster_id,
            "cluster_name": cluster.name,
            "score": score,
            "fit_band": fit_band_from_score(score),
            "top_keyskills": [ks.name for ks in contributing],
            "band_breakdown": band_breakdown,
            "explanation": explain_cluster(cluster, score, contributing, band_breakdown),
        }

        # PR37: resolve CMS text
        cluster_item["explanation"]["text"] = resolve_cms_text(
            db,
            version=version,
            locale=locale,
            explanation_key=cluster_item["explanation"]["explanation_key"],
            allow_numbers=allow_numbers_in_text,
        )

        cluster_item["explanation"]["text"] = render_text_with_slots(
            cluster_item["explanation"]["text"],
            cluster_item["explanation"].get("slots", {}),
        )

        cluster_output.append(cluster_item)
    # ---------------------------
    # CAREER EXPLANATIONS
    # ---------------------------
    for career_id, score in top_careers:
        career = next((c for c in careers if c.id == career_id), None)
        if not career:
            continue

        ks_rows = db.execute(
            select(
                models.career_keyskill_association.c.keyskill_id,
                models.career_keyskill_association.c.weight_percentage
            ).where(
                models.career_keyskill_association.c.career_id == career_id
            )
        ).all()

        contributions = []
        for ks_id, weight in ks_rows:
            if student_keyskills.get(ks_id, 0) <= 0:
                continue
            ks_obj = keyskills.get(ks_id)
            if not ks_obj:
                continue
            contributions.append((ks_obj, weight))

        contributions = sorted(contributions, key=lambda x: (x[1] or 0), reverse=True)[:3]

        fit_band = fit_band_from_score(score)

        career_item = {
            "career_id": career_id,
            "career_name": career.title,
            "score": score,
            "fit_band": fit_band,
            "top_keyskills": [k.name for k, _ in contributions],
            "explanation": explain_career(
                career,
                score,
                [k for k, _ in contributions],
                fit_band,
            ),
        }

        # PR37: resolve CMS text
        career_item["explanation"]["text"] = resolve_cms_text(
            db,
            version=version,
            locale=locale,
            explanation_key=career_item["explanation"]["explanation_key"],
            allow_numbers=allow_numbers_in_text,
        )
        career_item["explanation"]["text"] = render_text_with_slots(
            career_item["explanation"]["text"],
            career_item["explanation"].get("slots", {}),
        )

        career_output.append(career_item)

    return {
        "clusters": cluster_output,
        "careers": career_output,
    }
