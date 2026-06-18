"""
Weight-snapshot service — Stage 1 + Stage 2 (capture + read/diff; no restore).

Public surface:
    read_full_table_weights(db)            -> list of all CKA rows
    read_career_weights(db, career_id)     -> CKA rows for one career
    capture_snapshot(db, *, ...)           -> WeightSnapshot (caller commits)
    capture_promote_snapshot(db, wcr, ...) -> WeightSnapshot (commits internally)
    compute_diff(snapshot_rows, live_rows) -> structured diff (Stage 2, read-only)
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


# ── Diff (Stage 2, read-only) ──────────────────────────────────────────────────

def compute_diff(
    snapshot_rows: list[dict[str, Any]],
    live_rows:     list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compare snapshot weights against live career_keyskill_association weights.

    DIFF DIRECTION — restore semantics:
        Each row is described from the perspective of "what would change in LIVE
        if this snapshot were restored."

        change='removed'   — keyskill exists in snapshot but NOT in live.
                             Restoring would ADD it back to live.
        change='added'     — keyskill exists in live but NOT in snapshot.
                             Restoring would REMOVE it from live.
        change='changed'   — both have the keyskill but weights differ.
                             Restoring would UPDATE live weight to snapshot weight.
        change='unchanged' — both agree; restore would leave it untouched.

    This direction is intentional and must be read the same way by B22.3 (the
    restore endpoint). The label names describe the keyskill's fate in LIVE
    after a restore, NOT the direction of data movement.

    Returns a dict:
        {
          "careers": [
            {
              "career_id": int,
              "rows": [
                {
                  "keyskill_id":       int,
                  "snapshot_weight":   int | None,
                  "live_weight":       int | None,
                  "change":            'added'|'removed'|'changed'|'unchanged'
                },
                ...
              ],
              "n_added":     int,   # restore would remove these from live
              "n_removed":   int,   # restore would add these back to live
              "n_changed":   int,
              "n_unchanged": int,
            },
            ...
          ],
          "summary": {
            "total_careers_with_changes": int,
            "total_rows_that_would_change": int,   # added + removed + changed
          }
        }

    Pure function — reads no DB, writes nothing.
    """
    # Index snapshot: (career_id, keyskill_id) -> weight_percentage
    snap_index: dict[tuple[int, int], int] = {
        (r["career_id"], r["keyskill_id"]): r["weight_percentage"]
        for r in snapshot_rows
    }
    # Index live: (career_id, keyskill_id) -> weight_percentage
    live_index: dict[tuple[int, int], int] = {
        (r["career_id"], r["keyskill_id"]): r["weight_percentage"]
        for r in live_rows
    }

    # Union of all (career_id, keyskill_id) pairs
    all_keys = snap_index.keys() | live_index.keys()

    # Group by career_id
    from collections import defaultdict
    by_career: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for (career_id, keyskill_id) in sorted(all_keys):
        snap_w = snap_index.get((career_id, keyskill_id))
        live_w = live_index.get((career_id, keyskill_id))

        if snap_w is None:
            change = "added"       # live has it, snapshot doesn't → restore removes
        elif live_w is None:
            change = "removed"     # snapshot has it, live doesn't → restore adds back
        elif snap_w != live_w:
            change = "changed"
        else:
            change = "unchanged"

        by_career[career_id].append(
            {
                "keyskill_id":     keyskill_id,
                "snapshot_weight": snap_w,
                "live_weight":     live_w,
                "change":          change,
            }
        )

    careers_out: list[dict[str, Any]] = []
    total_careers_with_changes = 0
    total_rows_that_would_change = 0

    for career_id in sorted(by_career):
        rows = by_career[career_id]
        n_added     = sum(1 for r in rows if r["change"] == "added")
        n_removed   = sum(1 for r in rows if r["change"] == "removed")
        n_changed   = sum(1 for r in rows if r["change"] == "changed")
        n_unchanged = sum(1 for r in rows if r["change"] == "unchanged")
        rows_changing = n_added + n_removed + n_changed

        careers_out.append(
            {
                "career_id":   career_id,
                "rows":        rows,
                "n_added":     n_added,
                "n_removed":   n_removed,
                "n_changed":   n_changed,
                "n_unchanged": n_unchanged,
            }
        )
        if rows_changing > 0:
            total_careers_with_changes   += 1
            total_rows_that_would_change += rows_changing

    return {
        "careers": careers_out,
        "summary": {
            "total_careers_with_changes":   total_careers_with_changes,
            "total_rows_that_would_change": total_rows_that_would_change,
        },
    }
