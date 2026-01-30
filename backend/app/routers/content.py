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
    version: str = Query(..., description="Content version (e.g., v1)"),
    locale: str = Query(..., description="Locale (e.g., en, kn-IN)"),
    keys: Optional[str] = Query(None, description="Optional comma-separated explanation_key filter"),
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

    if keys:
        key_list = [k.strip() for k in keys.split(",") if k.strip()]
        if key_list:
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
