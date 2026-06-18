"""
Weight-snapshot service — Stage 1 (capture only, no restore).

Public surface:
    read_full_table_weights(db)            -> list of all CKA rows
    read_career_weights(db, career_id)     -> CKA rows for one career
    capture_snapshot(db, *, ...)           -> WeightSnapshot (caller commits)
    capture_promote_snapshot(db, wcr, ...) -> WeightSnapshot (commits internally)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import WeightSnapshot

logger = logging.getLogger(__name__)


# ── Name generation ────────────────────────────────────────────────────────────

def _generate_name(source: str, scope_type: str, scope_ref: Optional[int]) -> str:
    """
    Build a system-owned, collision-safe name for a snapshot.

    Format: snap-{YYYYMMDD-HHMMSS}-{source}-{scope}
    where scope is 'full' or 'c{career_id}'.

    Timestamp resolution is 1 second. Two captures within the same second with
    the same source+scope are extremely unlikely (single-threaded admin action),
    but if it happens the caller's UNIQUE constraint will surface the error
    rather than silently overwriting data.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    scope_slug = "full" if scope_type == "full" else f"c{scope_ref}"
    return f"snap-{ts}-{source}-{scope_slug}"


# ── CKA readers ────────────────────────────────────────────────────────────────

def read_full_table_weights(db: Session) -> list[dict[str, Any]]:
    """
    Return all career_keyskill_association rows as plain dicts.
    READ-ONLY — issues a single SELECT, never writes CKA.
    """
    rows = db.execute(
        text("""
            SELECT career_id, keyskill_id, weight_percentage
            FROM career_keyskill_association
            ORDER BY career_id, weight_percentage DESC
        """)
    ).mappings().all()
    return [
        {
            "career_id":        r["career_id"],
            "keyskill_id":      r["keyskill_id"],
            "weight_percentage": r["weight_percentage"],
        }
        for r in rows
    ]


def read_career_weights(db: Session, career_id: int) -> list[dict[str, Any]]:
    """
    Return career_keyskill_association rows for one career as plain dicts.
    READ-ONLY — issues a single SELECT, never writes CKA.
    Each dict includes career_id so the shape matches read_full_table_weights.
    """
    rows = db.execute(
        text("""
            SELECT career_id, keyskill_id, weight_percentage
            FROM career_keyskill_association
            WHERE career_id = :career_id
            ORDER BY weight_percentage DESC
        """),
        {"career_id": career_id},
    ).mappings().all()
    return [
        {
            "career_id":        r["career_id"],
            "keyskill_id":      r["keyskill_id"],
            "weight_percentage": r["weight_percentage"],
        }
        for r in rows
    ]


# ── Core capture ───────────────────────────────────────────────────────────────

def capture_snapshot(
    db: Session,
    *,
    scope_type:    str,
    source:        str,
    snapshot_rows: list[dict[str, Any]],
    created_by:    int,
    scope_ref:     Optional[int] = None,
    alias:         Optional[str] = None,
    reason:        Optional[str] = None,
    wcr_id:        Optional[int] = None,
    _commit:       bool = False,
) -> WeightSnapshot:
    """
    Persist a WeightSnapshot row.

    Does NOT commit by default (_commit=False) — the caller owns the
    transaction and must call db.commit() after this returns.
    Pass _commit=True only from promote-hook callers that need an isolated
    commit (see capture_promote_snapshot).

    Never raises — callers that need fire-and-forget behaviour should wrap in
    try/except themselves (the promote hook does this).
    """
    name = _generate_name(source, scope_type, scope_ref)

    snap = WeightSnapshot(
        name       = name,
        alias      = alias,
        reason     = reason,
        scope_type = scope_type,
        scope_ref  = scope_ref,
        snapshot   = snapshot_rows,
        source     = source,
        wcr_id     = wcr_id,
        created_by = created_by,
    )
    db.add(snap)

    if _commit:
        db.commit()
        db.refresh(snap)

    return snap


# ── Promote-hook convenience ───────────────────────────────────────────────────

def capture_promote_snapshot(
    db:         Session,
    wcr:        Any,  # WeightChangeRequest ORM instance
    created_by: int,
) -> WeightSnapshot:
    """
    Auto-capture called by the W8 promote hook.

    Extracts baseline_weights from wcr.changes (captured at draft time —
    the 'before' state), injects career_id into each row, and writes a
    WeightSnapshot with source='auto_promote'.

    Commits its own transaction (runs after the promote's db.commit() in an
    isolated try/except — must not interfere with the main promote flow).

    scope_type:
        'career' when changes has exactly one entry (single-career WCR)
        'full'   when changes has multiple entries (batch WCR)
    """
    changes: list[dict] = wcr.changes or []

    snapshot_rows: list[dict[str, Any]] = []
    for entry in changes:
        career_id = entry["career_id"]
        baseline  = entry.get("baseline_weights") or []
        # Empty baseline means the career had zero CKA rows at draft time —
        # that is a valid (if unusual) state; store the empty list faithfully.
        for row in baseline:
            snapshot_rows.append(
                {
                    "career_id":        career_id,
                    "keyskill_id":      row["keyskill_id"],
                    "weight_percentage": row["weight_percentage"],
                }
            )

    if len(changes) == 1:
        scope_type = "career"
        scope_ref  = changes[0]["career_id"]
    else:
        scope_type = "full"
        scope_ref  = None

    return capture_snapshot(
        db,
        scope_type    = scope_type,
        scope_ref     = scope_ref,
        source        = "auto_promote",
        snapshot_rows = snapshot_rows,
        created_by    = created_by,
        wcr_id        = wcr.id,
        _commit       = True,
    )
