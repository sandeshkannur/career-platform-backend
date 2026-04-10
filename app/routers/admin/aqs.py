"""
Admin read-only endpoints for Associated Qualities (AQs).
Auth: inherited from the admin package router (require_role("admin")).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app import models

router = APIRouter()


class AQOut(BaseModel):
    aq_code: str
    aq_name: str
    domain: Optional[str] = None  # not stored in DB; always None

    model_config = {"from_attributes": True}


@router.get(
    "/aqs",
    response_model=List[AQOut],
    summary="List all Associated Qualities (admin)",
)
def list_aqs(db: Session = Depends(get_db)):
    rows = (
        db.query(models.AssociatedQuality)
        .order_by(models.AssociatedQuality.aq_id)
        .all()
    )
    return [AQOut(aq_code=r.aq_id, aq_name=r.aq_name) for r in rows]
