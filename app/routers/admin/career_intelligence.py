"""
Admin career intelligence endpoints.

  POST /v1/admin/careers/recompute-vectors
      Triggers a full recompute of all career feature vectors.
      Runs synchronously — may take a few seconds for large datasets.
      Logs the action to admin_audit_trail.

  GET /v1/admin/careers/{career_id}/proximity
      Returns the top-N most similar careers to the given career,
      ranked by cosine similarity of their feature vectors.
      Requires vectors to exist (run recompute-vectors first).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import Career, CareerFeatureVector
from app.auth.auth import require_role, get_current_active_user
from app.routers.admin.audit_trail import log_audit
from app.services.career_vector_service import recompute_all_vectors, get_career_neighbours
from app import schemas

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RecomputeVectorsResponse(BaseModel):
    careers_processed: int
    careers_skipped:   int
    archetypes:        int
    computed_at:       str
    message:           str


class CareerNeighbour(BaseModel):
    career_id:  int
    title:      str
    similarity: float


class ProximityResponse(BaseModel):
    career_id:   int
    career_title: str
    neighbours:  List[CareerNeighbour]
    vector_computed_at: Optional[str]


# ---------------------------------------------------------------------------
# POST /careers/recompute-vectors
# ---------------------------------------------------------------------------

@router.post(
    "/careers/recompute-vectors",
    response_model=RecomputeVectorsResponse,
    status_code=200,
    summary="Recompute all career feature vectors (admin)",
    dependencies=[Depends(require_role("admin"))],
)
def recompute_career_vectors(
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user),
):
    """
    Rebuilds keyskill, market, and TF-IDF vectors for every active career,
    runs k-means clustering, and upserts all rows into career_feature_vectors.

    Also records the run in admin_audit_trail.
    """
    try:
        summary = recompute_all_vectors(db)
    except Exception as exc:
        logger.exception("recompute_career_vectors failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Vector recompute failed: {exc}")

    # Audit log (best-effort — separate session state after commit above)
    try:
        log_audit(
            db          = db,
            action      = "create",
            entity_type = "career",
            entity_id   = None,
            entity_name = "career_feature_vectors (batch)",
            user_id     = current_user.id,
            user_email  = current_user.email,
            details     = summary,
            commit      = True,
        )
    except Exception:
        pass  # audit failure must not fail the response

    return RecomputeVectorsResponse(
        careers_processed = summary["careers_processed"],
        careers_skipped   = summary["careers_skipped"],
        archetypes        = summary["archetypes"],
        computed_at       = summary["computed_at"],
        message = (
            f"Recomputed vectors for {summary['careers_processed']} career(s) "
            f"across {summary['archetypes']} archetype cluster(s). "
            f"{summary['careers_skipped']} career(s) skipped due to errors."
        ),
    )


# ---------------------------------------------------------------------------
# GET /careers/{career_id}/proximity
# ---------------------------------------------------------------------------

@router.get(
    "/careers/{career_id}/proximity",
    response_model=ProximityResponse,
    summary="Get nearest-neighbour careers by feature-vector similarity (admin)",
    dependencies=[Depends(require_role("admin"))],
)
def career_proximity(
    career_id: int,
    top_n: int = Query(5, ge=1, le=20, description="Number of neighbours to return (1–20)"),
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    """
    Returns the top_n most similar careers to *career_id*, ranked by cosine
    similarity of their concatenated (keyskill + market + tfidf) vectors.

    Requires at least one recompute-vectors run.  Returns 404 if the target
    career has no stored vector, or 404 if the career itself doesn't exist.
    """
    # Career must exist
    career: Optional[Career] = db.query(Career).filter(Career.id == career_id).first()
    if career is None:
        raise HTTPException(status_code=404, detail=f"Career id={career_id} not found.")

    # Fetch the stored vector for metadata
    fv: Optional[CareerFeatureVector] = (
        db.query(CareerFeatureVector)
        .filter(CareerFeatureVector.career_id == career_id)
        .first()
    )
    if fv is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No feature vector found for career_id={career_id}. "
                "Run POST /admin/careers/recompute-vectors first."
            ),
        )

    try:
        neighbours = get_career_neighbours(db, career_id, top_n=top_n)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("career_proximity failed for career_id=%s: %s", career_id, exc)
        raise HTTPException(status_code=500, detail=f"Proximity computation failed: {exc}")

    return ProximityResponse(
        career_id    = career_id,
        career_title = career.title,
        neighbours   = [CareerNeighbour(**n) for n in neighbours],
        vector_computed_at = fv.computed_at.isoformat() if fv.computed_at else None,
    )
