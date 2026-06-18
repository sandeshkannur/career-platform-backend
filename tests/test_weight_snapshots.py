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
