# app/routers/student_graph_analytics.py
"""
4 graph analytics endpoints for student drill-down.
Admin-only. Powers the enhanced student analytics panel.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db
from app.auth.auth import require_admin_or_counsellor
from app.services.graph_query_service import get_graph_query_service

router = APIRouter()


def _get_service(db: Session):
    return get_graph_query_service(db)


@router.get("/{student_id}/aq-influence")
def get_aq_influence(
    student_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """Which AQs most influence which careers for this student."""
    try:
        return _get_service(db).get_aq_influence_map(student_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{student_id}/whatif")
def get_whatif(
    student_id: int,
    aq_code: str,
    delta: float = 10.0,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """
    Simulate career changes if student improves a specific AQ.
    ?aq_code=AQ_01&delta=10
    """
    try:
        return _get_service(db).get_whatif_simulation(student_id, aq_code, delta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{student_id}/reachability")
def get_reachability(
    student_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """3-zone cluster reachability map for this student."""
    try:
        return _get_service(db).get_cluster_reachability(student_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{student_id}/pathway")
def get_pathway(
    student_id: int,
    career: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """
    Career pathway analysis — what does this student need to reach a target career.
    ?career=Data Scientist
    """
    try:
        return _get_service(db).get_career_pathway(student_id, career)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
