"""
Pydantic v2 schemas for the weight-approval spine (Stages 2+).

Registered in app/schemas/__init__.py via:
    from .weight_approval import *

Naming convention: WCR prefix (WeightChangeRequest) to avoid any collision
with the existing wildcard-exported schema names.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Request bodies ─────────────────────────────────────────────────────────────

class WCRWeightItem(BaseModel):
    """One key-skill / weight pair inside a proposed_weights list."""
    keyskill_id:       int
    weight_percentage: int = Field(..., ge=0, le=100)


class WCRProposalCreate(BaseModel):
    """
    Request body for POST /v1/admin-portal/careers/{career_id}/keyskill-weights/proposals.

    `proposed_weights` is validated by validate_proposed_weights() before the
    WeightChangeRequest row is created.  `scope` is informational — always
    'single' for per-career proposals created via this endpoint.
    """
    title:            Optional[str]        = Field(None, max_length=200)
    proposed_weights: List[WCRWeightItem]


# ── Response schemas ───────────────────────────────────────────────────────────

class WCROut(BaseModel):
    """Full representation of a WeightChangeRequest row."""
    id:                 int
    title:              Optional[str]
    status:             str
    scope:              str
    changes:            Any        # JSONB array — validated at service layer
    created_by:         int
    created_at:         datetime
    submitted_at:       Optional[datetime]
    reviewed_by:        Optional[int]
    reviewed_at:        Optional[datetime]
    review_level:       int
    decision_comment:   Optional[str]
    promoted_at:        Optional[datetime]
    vectors_recomputed: bool

    model_config = ConfigDict(from_attributes=True)


class WCRListOut(BaseModel):
    """Paginated list response for weight change requests."""
    items: List[WCROut]
    total: int
