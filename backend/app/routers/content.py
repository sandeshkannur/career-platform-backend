from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.deps import get_db
from app.models import ExplainabilityContent
from app.schemas import ExplainabilityContentResponse, ExplainabilityContentItem

router = APIRouter(tags=["Content"])


@router.get("/explainability", response_model=ExplainabilityContentResponse)
def get_explainability_content(
    version: str = Query("v1", description="Content version (e.g., v1)"),
    locale: str = Query("en", description="Locale (e.g., en, kn-IN)"),
    keys: Optional[str] = Query(None, description="Optional comma-separated explanation_key filter"),
    facet_keys: Optional[List[str]] = Query(None, description="Facet keys (repeatable and/or comma-separated)"),
    aq_keys: Optional[List[str]] = Query(None, description="Associated quality keys (repeatable and/or comma-separated)"),
    db: Session = Depends(get_db),
):
    """
    PR16: Public, student-safe content fetch.
    Returns active explainability copy for a given (version, locale).
    - Does NOT return analytics, scores, or internal IDs.
    - Default returns all active rows for the requested version+locale.
    - Optional 'keys' filter enables fetching only a subset for lightweight FE calls.
    """

    stmt = select(ExplainabilityContent).where(
        ExplainabilityContent.version == version,
        ExplainabilityContent.locale == locale,
        ExplainabilityContent.is_active == True,  # noqa: E712
    )

    def _split_mixed(values: Optional[List[str]]) -> List[str]:
        """
        Accepts repeatable query params and/or comma-separated strings.
        Example:
          facet_keys=foo&facet_keys=bar,baz  -> ["foo","bar","baz"]
        """
        if not values:
            return []
        out: List[str] = []
        for v in values:
            if not v:
                continue
            parts = [p.strip() for p in v.split(",") if p.strip()]
            out.extend(parts)
        return out

    def _tokenize_key(k: str) -> str:
        """
        Convert any key to UPPER_SNAKE for stable CMS lookup.
        Example: "analytical_pattern" -> "ANALYTICAL_PATTERN"
        """
        k = k.strip()
        token_chars: List[str] = []
        for ch in k:
            token_chars.append(ch.upper() if ch.isalnum() else "_")
        token = "".join(token_chars)
        while "__" in token:
            token = token.replace("__", "_")
        return token.strip("_")

    expanded_keys: List[str] = []

    # Expand facet keys -> support both legacy numbered keys and future LABEL/DESC keys
    for k in _split_mixed(facet_keys):
        t = _tokenize_key(k)

        # Legacy (your current DB examples): FACET.CONFIDENCE.001
        expanded_keys.append(f"FACET.{t}.001")

        # Future-friendly: FACET.CONFIDENCE.LABEL / FACET.CONFIDENCE.DESC
        expanded_keys.append(f"FACET.{t}.LABEL")
        expanded_keys.append(f"FACET.{t}.DESC")

    # Expand AQ keys -> support both legacy numbered keys and future LABEL/DESC keys
    for k in _split_mixed(aq_keys):
        t = _tokenize_key(k)

        # Legacy (your current DB examples): AQ.INTRO.001
        expanded_keys.append(f"AQ.{t}.001")

        # Future-friendly: AQ.CURIOUS.LABEL / AQ.CURIOUS.DESC
        expanded_keys.append(f"AQ.{t}.LABEL")
        expanded_keys.append(f"AQ.{t}.DESC")

    key_list: List[str] = []

    if keys:
        key_list.extend([k.strip() for k in keys.split(",") if k.strip()])

    if expanded_keys:
        key_list.extend(expanded_keys)

    # De-dupe while keeping order stable
    if key_list:
        seen = set()
        key_list = [k for k in key_list if not (k in seen or seen.add(k))]
        stmt = stmt.where(ExplainabilityContent.explanation_key.in_(key_list))

    rows: List[ExplainabilityContent] = db.execute(stmt).scalars().all()

    items = [
        ExplainabilityContentItem(
            explanation_key=r.explanation_key,
            text=r.text,
        )
        for r in rows
    ]

    return ExplainabilityContentResponse(
        version=version,
        locale=locale,
        items=items,
    )
