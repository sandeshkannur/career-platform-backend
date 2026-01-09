from fastapi import APIRouter
from app.auth.auth import get_current_active_user, require_role
from fastapi import Depends

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_active_user)],
)

@router.get("/analytics/health")
def analytics_placeholder():
    return {"message": "Analytics module will be built soon."}