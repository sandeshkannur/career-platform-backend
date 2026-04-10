"""
Admin endpoints for fit-band threshold configuration.
Auth: inherited from the admin package router (require_role("admin")).

GET /v1/admin/fit-bands   — list all 5 bands ordered by sort_order
PUT /v1/admin/fit-bands   — update all bands in one call
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy.orm import Session

from app.deps import get_db
from app import models
from app.services.explanations import clear_fit_band_cache

router = APIRouter()

_REQUIRED_KEYS = {"high_potential", "strong", "promising", "developing", "exploring"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FitBandOut(BaseModel):
    band_key: str
    label: str
    min_score: float
    sort_order: int

    model_config = {"from_attributes": True}


class FitBandUpdate(BaseModel):
    band_key: str
    label: str
    min_score: float

    @field_validator("min_score")
    @classmethod
    def score_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"min_score must be between 0 and 100, got {v}")
        return v


class FitBandsUpdateRequest(BaseModel):
    bands: List[FitBandUpdate]

    @model_validator(mode="after")
    def validate_bands(self) -> "FitBandsUpdateRequest":
        keys = {b.band_key for b in self.bands}
        missing = _REQUIRED_KEYS - keys
        if missing:
            raise ValueError(f"Missing required band keys: {sorted(missing)}")
        extra = keys - _REQUIRED_KEYS
        if extra:
            raise ValueError(f"Unknown band keys: {sorted(extra)}")

        # min_scores must be strictly descending (highest band first by sort_order)
        # Sort by the canonical sort_order to check order
        _SORT = {"high_potential": 1, "strong": 2, "promising": 3, "developing": 4, "exploring": 5}
        ordered = sorted(self.bands, key=lambda b: _SORT[b.band_key])
        scores = [b.min_score for b in ordered]
        for i in range(len(scores) - 1):
            if scores[i] <= scores[i + 1]:
                raise ValueError(
                    f"min_scores must be strictly descending by band. "
                    f"{ordered[i].band_key}={scores[i]} is not > "
                    f"{ordered[i+1].band_key}={scores[i+1]}"
                )
        # exploring must be 0
        exploring = next(b for b in self.bands if b.band_key == "exploring")
        if exploring.min_score != 0:
            raise ValueError("exploring band must have min_score=0 (it is the catch-all floor)")

        return self


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/fit-bands",
    response_model=List[FitBandOut],
    summary="List fit-band thresholds (admin)",
)
def get_fit_bands(db: Session = Depends(get_db)):
    return (
        db.query(models.FitBandConfig)
        .order_by(models.FitBandConfig.sort_order)
        .all()
    )


@router.put(
    "/fit-bands",
    response_model=List[FitBandOut],
    summary="Update all fit-band thresholds (admin)",
)
def update_fit_bands(
    payload: FitBandsUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update min_score and label for all 5 bands in one atomic call.
    Validates descending order and presence of all required keys.
    Clears the in-memory threshold cache after saving so the next
    fit_band_from_score call picks up the new values.
    """
    _SORT = {"high_potential": 1, "strong": 2, "promising": 3, "developing": 4, "exploring": 5}

    rows = {r.band_key: r for r in db.query(models.FitBandConfig).all()}

    if not rows:
        raise HTTPException(
            status_code=500,
            detail="fit_band_config table is empty — run alembic upgrade head first",
        )

    for band in payload.bands:
        row = rows.get(band.band_key)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Band key not found in DB: {band.band_key!r}")
        row.min_score  = band.min_score
        row.label      = band.label
        row.sort_order = _SORT[band.band_key]

    db.commit()

    # Invalidate the module-level cache in explanations.py
    clear_fit_band_cache()

    return (
        db.query(models.FitBandConfig)
        .order_by(models.FitBandConfig.sort_order)
        .all()
    )
