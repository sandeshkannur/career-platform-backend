"""
Tests for the weight-snapshot spine — Stage 1.

Coverage:
  1. read_full_table_weights  — SELECT only, correct shape, CKA never written
  2. read_career_weights      — SELECT only, one career, career_id injected
  3. _generate_name           — format, uniqueness (different timestamps)
  4. capture_snapshot         — row built, name present, no-commit default
  5. capture_promote_snapshot — baseline_weights extracted, career_id injected,
                               multi-career → scope='full', empty-baseline edge case
  6. PROMOTE HOOK isolation   — when capture_promote_snapshot raises, promote
                               still succeeds: weights committed, recompute attempted
  7. CKA write-never guarantee — no INSERT/UPDATE/DELETE on career_keyskill_association
                               from any capture path
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_db(cka_rows: list[dict] | None = None) -> MagicMock:
    """
    Build a mock Session whose execute().mappings().all() returns cka_rows.
    execute().mappings() returns an object whose .all() gives the rows.
    """
    db = MagicMock()
    rows = cka_rows or []
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = rows
    db.execute.return_value = mock_result
    return db


_SAMPLE_CKA = [
    {"career_id": 1, "keyskill_id": 10, "weight_percentage": 40},
    {"career_id": 1, "keyskill_id": 11, "weight_percentage": 35},
    {"career_id": 1, "keyskill_id": 12, "weight_percentage": 25},
    {"career_id": 2, "keyskill_id": 10, "weight_percentage": 50},
    {"career_id": 2, "keyskill_id": 13, "weight_percentage": 30},
    {"career_id": 2, "keyskill_id": 14, "weight_percentage": 20},
]

_CAREER1_CKA = [r for r in _SAMPLE_CKA if r["career_id"] == 1]


# ── 1. read_full_table_weights ─────────────────────────────────────────────────

class TestReadFullTableWeights(unittest.TestCase):

    def test_returns_all_rows_with_correct_shape(self):
        from app.services.weight_snapshots import read_full_table_weights
        db = _mock_db(_SAMPLE_CKA)
        result = read_full_table_weights(db)
        self.assertEqual(len(result), 6)
        self.assertIn("career_id",        result[0])
        self.assertIn("keyskill_id",      result[0])
        self.assertIn("weight_percentage", result[0])

    def test_issues_single_select_never_writes_cka(self):
        from app.services.weight_snapshots import read_full_table_weights

        executed_sql: list[str] = []

        def _capture(stmt, *args, **kwargs):
            executed_sql.append(str(stmt).strip().upper())
            m = MagicMock()
            m.mappings.return_value.all.return_value = []
            return m

        db = MagicMock()
        db.execute.side_effect = _capture
        read_full_table_weights(db)

        self.assertEqual(len(executed_sql), 1)
        sql = executed_sql[0]
        self.assertTrue(sql.startswith("SELECT"), sql[:80])
        self.assertIn("CAREER_KEYSKILL_ASSOCIATION", sql)
        for forbidden in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP"):
            self.assertNotIn(forbidden, sql, f"Forbidden keyword in SQL: {forbidden}")

    def test_empty_table_returns_empty_list(self):
        from app.services.weight_snapshots import read_full_table_weights
        db = _mock_db([])
        self.assertEqual(read_full_table_weights(db), [])


# ── 2. read_career_weights ─────────────────────────────────────────────────────

class TestReadCareerWeights(unittest.TestCase):

    def test_returns_career_rows_with_career_id(self):
        from app.services.weight_snapshots import read_career_weights
        db = _mock_db(_CAREER1_CKA)
        result = read_career_weights(db, career_id=1)
        self.assertEqual(len(result), 3)
        for row in result:
            self.assertIn("career_id", row)
            self.assertEqual(row["career_id"], 1)

    def test_issues_single_select_never_writes_cka(self):
        from app.services.weight_snapshots import read_career_weights

        executed_sql: list[str] = []

        def _capture(stmt, *a, **kw):
            executed_sql.append(str(stmt).strip().upper())
            m = MagicMock()
            m.mappings.return_value.all.return_value = []
            return m

        db = MagicMock()
        db.execute.side_effect = _capture
        read_career_weights(db, career_id=42)

        self.assertEqual(len(executed_sql), 1)
        sql = executed_sql[0]
        self.assertTrue(sql.startswith("SELECT"), sql[:80])
        self.assertIn("CAREER_KEYSKILL_ASSOCIATION", sql)
        for forbidden in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP"):
            self.assertNotIn(forbidden, sql)

    def test_empty_career_returns_empty_list(self):
        from app.services.weight_snapshots import read_career_weights
        db = _mock_db([])
        self.assertEqual(read_career_weights(db, career_id=999), [])


# ── 3. _generate_name ─────────────────────────────────────────────────────────

class TestGenerateName(unittest.TestCase):

    def test_full_scope_format(self):
        from app.services.weight_snapshots import _generate_name
        name = _generate_name("manual", "full", None)
        self.assertTrue(name.startswith("snap-"), name)
        self.assertIn("manual", name)
        self.assertIn("full", name)
        # Format: snap-YYYYMMDD-HHMMSS-source-scope
        parts = name.split("-")
        self.assertEqual(parts[0], "snap")
        self.assertEqual(len(parts[1]), 8)   # YYYYMMDD
        self.assertEqual(len(parts[2]), 6)   # HHMMSS

    def test_career_scope_format(self):
        from app.services.weight_snapshots import _generate_name
        name = _generate_name("auto_promote", "career", 42)
        self.assertIn("auto_promote", name)
        self.assertIn("c42", name)

    def test_two_calls_same_source_same_scope_differ_in_time(self):
        """Names generated in different seconds must differ."""
        import time
        from app.services.weight_snapshots import _generate_name
        n1 = _generate_name("manual", "full", None)
        time.sleep(1.05)
        n2 = _generate_name("manual", "full", None)
        self.assertNotEqual(n1, n2)


# ── 4. capture_snapshot ───────────────────────────────────────────────────────

class TestCaptureSnapshot(unittest.TestCase):

    def _make_snap_db(self):
        """DB mock that tracks add/commit/refresh calls."""
        db = MagicMock()
        return db

    def test_builds_row_and_returns_it(self):
        from app.services.weight_snapshots import capture_snapshot
        from app.models import WeightSnapshot
        db = self._make_snap_db()

        snap = capture_snapshot(
            db,
            scope_type    = "full",
            source        = "manual",
            snapshot_rows = _SAMPLE_CKA,
            created_by    = 7,
            alias         = "my alias",
            reason        = "pre-release",
        )

        self.assertIsInstance(snap, WeightSnapshot)
        self.assertTrue(snap.name.startswith("snap-"))
        self.assertEqual(snap.alias,      "my alias")
        self.assertEqual(snap.reason,     "pre-release")
        self.assertEqual(snap.scope_type, "full")
        self.assertIsNone(snap.scope_ref)
        self.assertEqual(snap.source,     "manual")
        self.assertIsNone(snap.wcr_id)
        self.assertEqual(snap.created_by, 7)
        self.assertEqual(snap.snapshot,   _SAMPLE_CKA)
        db.add.assert_called_once_with(snap)

    def test_no_commit_by_default(self):
        from app.services.weight_snapshots import capture_snapshot
        db = self._make_snap_db()
        capture_snapshot(
            db,
            scope_type    = "career",
            scope_ref     = 1,
            source        = "manual",
            snapshot_rows = _CAREER1_CKA,
            created_by    = 7,
        )
        db.commit.assert_not_called()

    def test_commit_when_flag_set(self):
        from app.services.weight_snapshots import capture_snapshot
        db = self._make_snap_db()
        capture_snapshot(
            db,
            scope_type    = "full",
            source        = "manual",
            snapshot_rows = [],
            created_by    = 7,
            _commit       = True,
        )
        db.commit.assert_called_once()

    def test_wcr_id_stored(self):
        from app.services.weight_snapshots import capture_snapshot
        db = self._make_snap_db()
        snap = capture_snapshot(
            db,
            scope_type    = "career",
            scope_ref     = 5,
            source        = "auto_promote",
            snapshot_rows = [],
            created_by    = 3,
            wcr_id        = 99,
        )
        self.assertEqual(snap.wcr_id, 99)


# ── 5. capture_promote_snapshot ───────────────────────────────────────────────

class TestCapturePromoteSnapshot(unittest.TestCase):

    def _make_wcr(self, changes: list[dict]) -> MagicMock:
        wcr = MagicMock()
        wcr.id      = 42
        wcr.changes = changes
        return wcr

    def test_single_career_scope_career(self):
        from app.services.weight_snapshots import capture_promote_snapshot
        db = MagicMock()
        wcr = self._make_wcr([
            {
                "career_id": 1,
                "baseline_weights": [
                    {"keyskill_id": 10, "weight_percentage": 40},
                    {"keyskill_id": 11, "weight_percentage": 60},
                ],
                "proposed_weights": [],
            }
        ])

        snap = capture_promote_snapshot(db, wcr, created_by=5)

        self.assertEqual(snap.scope_type, "career")
        self.assertEqual(snap.scope_ref,  1)
        self.assertEqual(snap.source,     "auto_promote")
        self.assertEqual(snap.wcr_id,     42)
        self.assertEqual(len(snap.snapshot), 2)
        for row in snap.snapshot:
            self.assertIn("career_id", row)
            self.assertEqual(row["career_id"], 1)

    def test_multi_career_scope_full(self):
        from app.services.weight_snapshots import capture_promote_snapshot
        db = MagicMock()
        wcr = self._make_wcr([
            {
                "career_id": 1,
                "baseline_weights": [{"keyskill_id": 10, "weight_percentage": 100}],
                "proposed_weights": [],
            },
            {
                "career_id": 2,
                "baseline_weights": [{"keyskill_id": 20, "weight_percentage": 100}],
                "proposed_weights": [],
            },
        ])

        snap = capture_promote_snapshot(db, wcr, created_by=5)

        self.assertEqual(snap.scope_type, "full")
        self.assertIsNone(snap.scope_ref)
        self.assertEqual(len(snap.snapshot), 2)
        career_ids_in_snap = {r["career_id"] for r in snap.snapshot}
        self.assertEqual(career_ids_in_snap, {1, 2})

    def test_empty_baseline_stored_faithfully(self):
        """A career with [] baseline_weights must produce no rows in snapshot."""
        from app.services.weight_snapshots import capture_promote_snapshot
        db = MagicMock()
        wcr = self._make_wcr([
            {
                "career_id": 7,
                "baseline_weights": [],  # new career, no prior weights
                "proposed_weights": [{"keyskill_id": 5, "weight_percentage": 100}],
            }
        ])

        snap = capture_promote_snapshot(db, wcr, created_by=5)

        self.assertEqual(snap.snapshot, [],
                         "Empty baseline must yield empty snapshot list")
        self.assertEqual(snap.scope_type, "career")

    def test_missing_baseline_key_handled(self):
        """Entry without 'baseline_weights' key must not raise."""
        from app.services.weight_snapshots import capture_promote_snapshot
        db = MagicMock()
        # No 'baseline_weights' key — simulate a malformed entry
        wcr = self._make_wcr([
            {
                "career_id": 3,
                "proposed_weights": [],
            }
        ])
        # Should not raise
        snap = capture_promote_snapshot(db, wcr, created_by=5)
        self.assertEqual(snap.snapshot, [])

    def test_commits_own_transaction(self):
        """capture_promote_snapshot must commit (it's the isolated post-commit path)."""
        from app.services.weight_snapshots import capture_promote_snapshot
        db = MagicMock()
        wcr = self._make_wcr([
            {"career_id": 1, "baseline_weights": [], "proposed_weights": []}
        ])
        capture_promote_snapshot(db, wcr, created_by=5)
        db.commit.assert_called_once()


# ── 6. PROMOTE HOOK isolation ─────────────────────────────────────────────────

class TestPromoteHookIsolation(unittest.TestCase):
    """
    The promote hook must be purely additive: a snapshot-capture failure must
    not break the promote, and the vector recompute must still be attempted.
    """

    def _build_wcr_mock(self, db: MagicMock) -> MagicMock:
        wcr = MagicMock()
        wcr.id      = 1
        wcr.title   = "Test WCR"
        wcr.status  = "approved"
        wcr.changes = [
            {
                "career_id": 1,
                "baseline_weights": [{"keyskill_id": 10, "weight_percentage": 100}],
                "proposed_weights": [{"keyskill_id": 10, "weight_percentage": 100}],
            }
        ]
        db.query.return_value.filter.return_value.first.return_value = wcr
        return wcr

    def _make_promote_db(self) -> MagicMock:
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        return db

    @patch("app.routers.admin_portal.capture_promote_snapshot", side_effect=RuntimeError("snap boom"))
    @patch("app.routers.admin_portal.recompute_all_vectors")
    @patch("app.routers.admin_portal.validate_proposed_weights", return_value=[])
    def test_promote_succeeds_when_snapshot_raises(
        self,
        mock_validate,
        mock_recompute,
        mock_capture,
    ):
        """
        When capture_promote_snapshot raises, the promote endpoint must:
          - NOT raise
          - NOT roll back (db.commit must be called for the weight write)
          - still attempt vector recompute
        """
        from app.routers.admin_portal import promote_weight_change_request

        db          = self._make_promote_db()
        wcr         = self._build_wcr_mock(db)
        current_user = MagicMock()
        current_user.id    = 99
        current_user.email = "admin@test.com"

        result = promote_weight_change_request(
            request_id   = 1,
            db           = db,
            current_user = current_user,
        )

        # Promote succeeded
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["status"], "promoted")

        # Weight commit happened
        db.commit.assert_called()

        # Snapshot was attempted (and failed — but promote didn't care)
        mock_capture.assert_called_once()

        # Recompute was still attempted after the snapshot failure
        mock_recompute.assert_called_once()

    @patch("app.routers.admin_portal.capture_promote_snapshot", side_effect=RuntimeError("snap boom"))
    @patch("app.routers.admin_portal.recompute_all_vectors", side_effect=RuntimeError("vec boom"))
    @patch("app.routers.admin_portal.validate_proposed_weights", return_value=[])
    def test_promote_succeeds_when_both_hooks_raise(
        self,
        mock_validate,
        mock_recompute,
        mock_capture,
    ):
        """Both post-commit hooks failing must not break promote."""
        from app.routers.admin_portal import promote_weight_change_request

        db           = self._make_promote_db()
        wcr          = self._build_wcr_mock(db)
        current_user = MagicMock()
        current_user.id    = 99
        current_user.email = "admin@test.com"

        result = promote_weight_change_request(
            request_id   = 1,
            db           = db,
            current_user = current_user,
        )

        self.assertEqual(result["ok"], True)
        db.commit.assert_called()
        mock_capture.assert_called_once()
        mock_recompute.assert_called_once()


# ── 7. CKA write-never guarantee ─────────────────────────────────────────────

class TestCKAWriteNever(unittest.TestCase):
    """
    No capture path must issue INSERT, UPDATE, DELETE, or TRUNCATE on
    career_keyskill_association.
    """

    def _spy_db(self) -> tuple[MagicMock, list[str]]:
        executed: list[str] = []

        def _cap(stmt, *a, **kw):
            executed.append(str(stmt).strip().upper())
            m = MagicMock()
            m.mappings.return_value.all.return_value = []
            return m

        db = MagicMock()
        db.execute.side_effect = _cap
        return db, executed

    def _assert_no_cka_writes(self, sqls: list[str]):
        cka_writes = [
            s for s in sqls
            if "CAREER_KEYSKILL_ASSOCIATION" in s
            and any(kw in s for kw in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP"))
        ]
        self.assertEqual(
            cka_writes, [],
            f"Unexpected CKA write statements: {cka_writes}",
        )

    def test_read_full_table_no_cka_write(self):
        from app.services.weight_snapshots import read_full_table_weights
        db, sqls = self._spy_db()
        read_full_table_weights(db)
        self._assert_no_cka_writes(sqls)

    def test_read_career_no_cka_write(self):
        from app.services.weight_snapshots import read_career_weights
        db, sqls = self._spy_db()
        read_career_weights(db, career_id=1)
        self._assert_no_cka_writes(sqls)

    def test_capture_snapshot_no_cka_write(self):
        from app.services.weight_snapshots import capture_snapshot
        db, sqls = self._spy_db()
        capture_snapshot(
            db,
            scope_type    = "full",
            source        = "manual",
            snapshot_rows = _SAMPLE_CKA,
            created_by    = 1,
        )
        self._assert_no_cka_writes(sqls)

    def test_capture_promote_snapshot_no_cka_write(self):
        from app.services.weight_snapshots import capture_promote_snapshot
        db, sqls = self._spy_db()
        wcr = MagicMock()
        wcr.id = 1
        wcr.changes = [
            {
                "career_id": 1,
                "baseline_weights": [{"keyskill_id": 5, "weight_percentage": 100}],
                "proposed_weights": [],
            }
        ]
        capture_promote_snapshot(db, wcr, created_by=1)
        self._assert_no_cka_writes(sqls)


# =============================================================================
# Stage 2 — read-only list / get-one / diff
# =============================================================================

# ── 8. compute_diff ───────────────────────────────────────────────────────────

class TestComputeDiff(unittest.TestCase):
    """
    Unit tests for compute_diff() — pure function, no DB.

    Diff direction (restore semantics):
        'removed'   → in snapshot, not live  → restoring adds it back to live
        'added'     → in live, not snapshot  → restoring removes it from live
        'changed'   → both present, weights differ → restoring updates live
        'unchanged' → both present, weights agree  → restore is a no-op
    """

    def _diff(self, snap, live):
        from app.services.weight_snapshots import compute_diff
        return compute_diff(snap, live)

    # ── no-op (snapshot == live) ──────────────────────────────────────────────

    def test_no_op_all_unchanged(self):
        rows = [
            {"career_id": 1, "keyskill_id": 10, "weight_percentage": 40},
            {"career_id": 1, "keyskill_id": 11, "weight_percentage": 60},
        ]
        result = self._diff(rows, rows)

        self.assertEqual(result["summary"]["total_rows_that_would_change"], 0)
        self.assertEqual(result["summary"]["total_careers_with_changes"],   0)

        career = result["careers"][0]
        self.assertEqual(career["n_unchanged"], 2)
        self.assertEqual(career["n_changed"],   0)
        self.assertEqual(career["n_added"],     0)
        self.assertEqual(career["n_removed"],   0)
        for row in career["rows"]:
            self.assertEqual(row["change"], "unchanged")

    # ── weight changed ─────────────────────────────────────────────────────────

    def test_changed_weight(self):
        snap = [{"career_id": 1, "keyskill_id": 10, "weight_percentage": 40}]
        live = [{"career_id": 1, "keyskill_id": 10, "weight_percentage": 50}]
        result = self._diff(snap, live)

        row = result["careers"][0]["rows"][0]
        self.assertEqual(row["change"],          "changed")
        self.assertEqual(row["snapshot_weight"], 40)
        self.assertEqual(row["live_weight"],     50)
        self.assertEqual(result["summary"]["total_rows_that_would_change"], 1)

    # ── 'removed': in snapshot, missing from live ─────────────────────────────

    def test_removed_restoring_adds_to_live(self):
        """
        Keyskill in snapshot but not in live.
        Restoring this snapshot would ADD it back to live.
        change='removed' from live's perspective.
        """
        snap = [{"career_id": 1, "keyskill_id": 10, "weight_percentage": 40}]
        live: list = []   # live lost it
        result = self._diff(snap, live)

        row = result["careers"][0]["rows"][0]
        self.assertEqual(row["change"],          "removed")
        self.assertEqual(row["snapshot_weight"], 40)
        self.assertIsNone(row["live_weight"])
        self.assertEqual(result["careers"][0]["n_removed"], 1)
        self.assertEqual(result["summary"]["total_rows_that_would_change"], 1)

    # ── 'added': in live, missing from snapshot ───────────────────────────────

    def test_added_restoring_removes_from_live(self):
        """
        Keyskill in live but not in snapshot.
        Restoring this snapshot would REMOVE it from live.
        change='added' from live's perspective (live added it since snapshot).
        """
        snap: list = []   # snapshot didn't have it
        live = [{"career_id": 1, "keyskill_id": 10, "weight_percentage": 30}]
        result = self._diff(snap, live)

        row = result["careers"][0]["rows"][0]
        self.assertEqual(row["change"],          "added")
        self.assertIsNone(row["snapshot_weight"])
        self.assertEqual(row["live_weight"],     30)
        self.assertEqual(result["careers"][0]["n_added"], 1)
        self.assertEqual(result["summary"]["total_rows_that_would_change"], 1)

    # ── multi-career diff ─────────────────────────────────────────────────────

    def test_multi_career_correct_grouping(self):
        snap = [
            {"career_id": 1, "keyskill_id": 10, "weight_percentage": 40},
            {"career_id": 1, "keyskill_id": 11, "weight_percentage": 60},
            {"career_id": 2, "keyskill_id": 10, "weight_percentage": 50},
        ]
        live = [
            {"career_id": 1, "keyskill_id": 10, "weight_percentage": 40},  # unchanged
            {"career_id": 1, "keyskill_id": 11, "weight_percentage": 70},  # changed
            # career 2 keyskill 10 is now missing → removed
        ]
        result = self._diff(snap, live)

        self.assertEqual(len(result["careers"]), 2)
        career1 = next(c for c in result["careers"] if c["career_id"] == 1)
        career2 = next(c for c in result["careers"] if c["career_id"] == 2)

        self.assertEqual(career1["n_unchanged"], 1)
        self.assertEqual(career1["n_changed"],   1)
        self.assertEqual(career2["n_removed"],   1)

        self.assertEqual(result["summary"]["total_careers_with_changes"],   2)
        self.assertEqual(result["summary"]["total_rows_that_would_change"], 2)

    # ── empty snapshot ────────────────────────────────────────────────────────

    def test_empty_snapshot_all_added(self):
        snap: list = []
        live = [
            {"career_id": 1, "keyskill_id": 10, "weight_percentage": 40},
        ]
        result = self._diff(snap, live)
        self.assertEqual(result["careers"][0]["rows"][0]["change"], "added")

    def test_empty_live_all_removed(self):
        snap = [
            {"career_id": 1, "keyskill_id": 10, "weight_percentage": 40},
        ]
        live: list = []
        result = self._diff(snap, live)
        self.assertEqual(result["careers"][0]["rows"][0]["change"], "removed")

    def test_both_empty_no_careers(self):
        result = self._diff([], [])
        self.assertEqual(result["careers"], [])
        self.assertEqual(result["summary"]["total_rows_that_would_change"], 0)

    # ── pure function — no DB reads or writes ─────────────────────────────────

    def test_compute_diff_is_pure_no_db_calls(self):
        """compute_diff must not touch the DB at all."""
        from app.services.weight_snapshots import compute_diff
        snap = [{"career_id": 1, "keyskill_id": 10, "weight_percentage": 40}]
        live = [{"career_id": 1, "keyskill_id": 10, "weight_percentage": 50}]
        # If compute_diff accepted a db arg it could call execute; it doesn't —
        # the function signature has no db parameter.
        import inspect
        sig = inspect.signature(compute_diff)
        self.assertNotIn("db", sig.parameters)


# ── 9. list_weight_snapshots endpoint ─────────────────────────────────────────

class TestListWeightSnapshots(unittest.TestCase):
    """
    Tests for GET /weight-snapshots via the endpoint function directly.
    """

    def _make_db(self, rows: list[dict]) -> MagicMock:
        db = MagicMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = rows
        db.execute.return_value = mock_result
        return db

    def _call(self, db, scope_type=None, source=None, career_id=None):
        from app.routers.admin_portal import list_weight_snapshots
        current_user = MagicMock()
        return list_weight_snapshots(
            scope_type   = scope_type,
            source       = source,
            career_id    = career_id,
            db           = db,
            current_user = current_user,
        )

    def test_returns_items_and_total(self):
        row = {
            "id": 1, "name": "snap-x", "alias": None, "scope_type": "full",
            "scope_ref": None, "source": "manual", "wcr_id": None,
            "created_by": 7, "created_at": None, "row_count": 6,
        }
        db = self._make_db([row])
        result = self._call(db)
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["name"], "snap-x")

    def test_no_full_snapshot_jsonb_in_list(self):
        """The list endpoint must NOT include the snapshot JSONB column."""
        row = {
            "id": 1, "name": "snap-x", "alias": None, "scope_type": "full",
            "scope_ref": None, "source": "manual", "wcr_id": None,
            "created_by": 7, "created_at": None, "row_count": 3,
        }
        db = self._make_db([row])
        result = self._call(db)
        for item in result["items"]:
            self.assertNotIn("snapshot", item)

    def test_filter_scope_type_added_to_query(self):
        """When scope_type filter is given, the SQL must contain the WHERE clause."""
        db = self._make_db([])
        self._call(db, scope_type="career")
        sql_called = str(db.execute.call_args[0][0]).upper()
        self.assertIn("SCOPE_TYPE", sql_called)

    def test_filter_source_added_to_query(self):
        db = self._make_db([])
        self._call(db, source="manual")
        sql_called = str(db.execute.call_args[0][0]).upper()
        self.assertIn("SOURCE", sql_called)

    def test_filter_career_id_added_to_query(self):
        db = self._make_db([])
        self._call(db, career_id=42)
        sql_called = str(db.execute.call_args[0][0]).upper()
        self.assertIn("SCOPE_REF", sql_called)

    def test_no_filter_no_where_clause(self):
        db = self._make_db([])
        self._call(db)
        sql_called = str(db.execute.call_args[0][0]).upper()
        self.assertNotIn("WHERE", sql_called)

    def test_empty_result(self):
        db = self._make_db([])
        result = self._call(db)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)

    def test_list_issues_no_write_to_weight_snapshots_or_cka(self):
        """The list endpoint must NOT write to weight_snapshots or CKA."""
        executed: list[str] = []

        def _cap(stmt, *a, **kw):
            executed.append(str(stmt).strip().upper())
            m = MagicMock()
            m.mappings.return_value.all.return_value = []
            return m

        db = MagicMock()
        db.execute.side_effect = _cap
        self._call(db)

        for sql in executed:
            for tbl in ("WEIGHT_SNAPSHOTS", "CAREER_KEYSKILL_ASSOCIATION"):
                for kw in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    self.assertNotIn(kw, sql, f"Unexpected write: {kw} on {tbl}")
        db.commit.assert_not_called()
        db.add.assert_not_called()


# ── 10. get_weight_snapshot endpoint ──────────────────────────────────────────

class TestGetWeightSnapshot(unittest.TestCase):

    def _make_snap(self, snapshot_data=None):
        snap = MagicMock()
        snap.id         = 5
        snap.name       = "snap-test"
        snap.alias      = "my alias"
        snap.reason     = "pre-release"
        snap.scope_type = "career"
        snap.scope_ref  = 1
        snap.source     = "manual"
        snap.wcr_id     = None
        snap.created_by = 7
        snap.created_at = None
        snap.snapshot   = snapshot_data or [
            {"career_id": 1, "keyskill_id": 10, "weight_percentage": 40},
        ]
        return snap

    def _call(self, db, snapshot_id=5):
        from app.routers.admin_portal import get_weight_snapshot
        return get_weight_snapshot(
            snapshot_id  = snapshot_id,
            db           = db,
            current_user = MagicMock(),
        )

    def test_returns_full_snapshot_jsonb(self):
        snap = self._make_snap()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = snap

        result = self._call(db)

        self.assertIn("snapshot", result)
        self.assertEqual(result["snapshot"], snap.snapshot)
        self.assertEqual(result["row_count"], 1)

    def test_returns_all_metadata_fields(self):
        snap = self._make_snap()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = snap

        result = self._call(db)

        for field in ("id", "name", "alias", "reason", "scope_type",
                      "scope_ref", "source", "wcr_id", "created_by", "created_at"):
            self.assertIn(field, result, f"Missing field: {field}")

    def test_404_on_missing(self):
        from fastapi import HTTPException
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with self.assertRaises(HTTPException) as ctx:
            self._call(db, snapshot_id=999)

        self.assertEqual(ctx.exception.status_code, 404)

    def test_no_writes(self):
        snap = self._make_snap()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = snap
        self._call(db)
        db.commit.assert_not_called()
        db.add.assert_not_called()
        db.execute.assert_not_called()


# ── 11. diff_weight_snapshot endpoint ─────────────────────────────────────────

class TestDiffWeightSnapshotEndpoint(unittest.TestCase):

    def _make_snap(self, scope_type="full", scope_ref=None, snapshot_data=None):
        snap = MagicMock()
        snap.id         = 1
        snap.name       = "snap-test"
        snap.scope_type = scope_type
        snap.scope_ref  = scope_ref
        snap.snapshot   = snapshot_data or []
        return snap

    def _call(self, db, snapshot_id=1):
        from app.routers.admin_portal import diff_weight_snapshot
        return diff_weight_snapshot(
            snapshot_id  = snapshot_id,
            db           = db,
            current_user = MagicMock(),
        )

    def _make_db_with_snap_and_live(self, snap, live_rows):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = snap

        # live weights come from read_career_weights / read_full_table_weights
        live_mock = MagicMock()
        live_mock.mappings.return_value.all.return_value = live_rows
        db.execute.return_value = live_mock
        return db

    def test_404_on_missing_snapshot(self):
        from fastapi import HTTPException
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        with self.assertRaises(HTTPException) as ctx:
            self._call(db, snapshot_id=999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_no_op_snapshot_equals_live(self):
        rows = [
            {"career_id": 1, "keyskill_id": 10, "weight_percentage": 40},
            {"career_id": 1, "keyskill_id": 11, "weight_percentage": 60},
        ]
        snap = self._make_snap(scope_type="full", snapshot_data=rows)
        db   = self._make_db_with_snap_and_live(snap, rows)

        result = self._call(db)

        self.assertEqual(result["summary"]["total_rows_that_would_change"], 0)
        self.assertEqual(result["summary"]["total_careers_with_changes"],   0)

    def test_diff_returns_correct_structure(self):
        snap_data = [{"career_id": 1, "keyskill_id": 10, "weight_percentage": 40}]
        live_data = [{"career_id": 1, "keyskill_id": 10, "weight_percentage": 50}]
        snap = self._make_snap(scope_type="full", snapshot_data=snap_data)
        db   = self._make_db_with_snap_and_live(snap, live_data)

        result = self._call(db)

        self.assertIn("snapshot_id",   result)
        self.assertIn("snapshot_name", result)
        self.assertIn("scope_type",    result)
        self.assertIn("careers",       result)
        self.assertIn("summary",       result)

        row = result["careers"][0]["rows"][0]
        self.assertEqual(row["change"],          "changed")
        self.assertEqual(row["snapshot_weight"], 40)
        self.assertEqual(row["live_weight"],     50)

    def test_career_scope_fetches_only_that_career(self):
        """For scope='career', the endpoint must read only that career's live weights."""
        snap_data = [{"career_id": 7, "keyskill_id": 10, "weight_percentage": 40}]
        snap = self._make_snap(scope_type="career", scope_ref=7, snapshot_data=snap_data)

        executed_sql: list[str] = []

        def _cap(stmt, params=None, *a, **kw):
            executed_sql.append(str(stmt).strip().upper())
            m = MagicMock()
            m.mappings.return_value.all.return_value = snap_data
            return m

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = snap
        db.execute.side_effect = _cap

        self._call(db)

        # Must use a parameterised WHERE career_id = :career_id query
        self.assertTrue(
            any("WHERE" in sql and "CAREER_ID" in sql for sql in executed_sql),
            f"Expected WHERE career_id filter in SQL; got: {executed_sql}",
        )

    def test_diff_writes_nothing(self):
        snap_data = [{"career_id": 1, "keyskill_id": 10, "weight_percentage": 40}]
        snap = self._make_snap(scope_type="full", snapshot_data=snap_data)
        db   = self._make_db_with_snap_and_live(snap, snap_data)

        self._call(db)

        db.commit.assert_not_called()
        db.add.assert_not_called()
