"""Analytics router.
Exposes aggregate analytics endpoints under /v1/analytics/.
Role gate: authenticated users (admin/counsellor for full data, student for own data).
Reads: student_skill_scores, assessment_results, career_clusters.
"""
from fastapi import APIRouter
from app.auth.auth import get_current_active_user, require_role
from fastapi import Depends

router = APIRouter(
    tags=["analytics"],
    dependencies=[Depends(get_current_active_user)],
)

@router.get("/health")
def analytics_placeholder():
    return {"message": "Analytics module will be built soon."}