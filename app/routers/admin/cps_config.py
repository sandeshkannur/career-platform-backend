"""
Admin CPS factor config endpoints.

  GET /v1/admin/cps-factors  — list all 4 factors ordered by sort_order
  PUT /v1/admin/cps-factors  — update weights + labels for all factors

After a successful PUT the module-level CPS weight cache in
app/utils/scoring.py is cleared so the next scoring call picks up
the new values without a restart.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import CPSFactorConfig
from app.auth.auth import require_role, get_current_active_user
from app.utils.scoring import clear_cps_weight_cache

router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)

VALID_FACTOR_KEYS = {"ses_band", "education_board", "support_level", "resource_access"}
WEIGHT_SUM_TOLERANCE = 0.001


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class CPSFactorOut(BaseModel):
    factor_key: str
    label:      str
    weight:     float
    sort_order: int

    model_config = {"from_attributes": True}


class CPSFactorUpdate(BaseModel):
    factor_key: str
    weight:     float
    label:      str

    @field_validator("weight")
    @classmethod
    def weight_range(cls, v: float) -> float:
        if not (0 < v <= 1.0):
            raise ValueError("weight must be > 0 and <= 1.0")
        return round(v, 6)

    @field_validator("factor_key")
    @classmethod
    def valid_key(cls, v: str) -> str:
        if v not in VALID_FACTOR_KEYS:
            raise ValueError(f"factor_key must be one of {sorted(VALID_FACTOR_KEYS)}")
        return v


class CPSFactorBulkUpdate(BaseModel):
    factors: List[CPSFactorUpdate]

    @model_validator(mode="after")
    def validate_bulk(self) -> "CPSFactorBulkUpdate":
        keys = [f.factor_key for f in self.factors]
        if sorted(keys) != sorted(VALID_FACTOR_KEYS):
            raise ValueError(f"All 4 factor keys must be present: {sorted(VALID_FACTOR_KEYS)}")
        total = sum(f.weight for f in self.factors)
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(
                f"Weights must sum to 1.0 (tolerance ±{WEIGHT_SUM_TOLERANCE}). "
                f"Got {round(total, 6)}."
            )
        return self


# ---------------------------------------------------------------------------
# GET /cps-factors
# ---------------------------------------------------------------------------

@router.get(
    "/cps-factors",
    response_model=List[CPSFactorOut],
    summary="List CPS factor weights (admin)",
)
def list_cps_factors(
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    rows = (
        db.query(CPSFactorConfig)
        .order_by(CPSFactorConfig.sort_order)
        .all()
    )
    return rows


# ---------------------------------------------------------------------------
# PUT /cps-factors
# ---------------------------------------------------------------------------

@router.put(
    "/cps-factors",
    response_model=List[CPSFactorOut],
    summary="Update CPS factor weights (admin)",
)
def update_cps_factors(
    body: CPSFactorBulkUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_active_user),
):
    for item in body.factors:
        row = (
            db.query(CPSFactorConfig)
            .filter(CPSFactorConfig.factor_key == item.factor_key)
            .first()
        )
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"factor_key '{item.factor_key}' not found. Run migrations to seed the table.",
            )
        row.weight = item.weight
        row.label  = item.label

    db.commit()

    # Clear the in-memory cache so compute_cps_v1 picks up new weights immediately
    clear_cps_weight_cache()

    rows = (
        db.query(CPSFactorConfig)
        .order_by(CPSFactorConfig.sort_order)
        .all()
    )
    return rows
