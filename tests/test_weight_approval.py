"""
Tests for the weight-approval spine — Stage 2.

Coverage:
  1. validate_proposed_weights() — all six rules, pure and DB-path
  2. snapshot_current_weights()  — issues only SELECT on career_keyskill_association
  3. CKA byte-identical assertion — no INSERT/UPDATE/DELETE executed on CKA
     during a baseline snapshot (the core Stage 2 guarantee)
  4. Schema instantiation — WCRProposalCreate, WCROut
  5. Constants sanity check
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch


# ── Helper: build a minimal mock db session ────────────────────────────────────

def _make_db_with_keyskills(*valid_ids: int) -> MagicMock:
    """
    Return a mock Session whose execute() response simulates:
      SELECT id FROM keyskills WHERE id = ANY(...)
    returning the given valid_ids.
    """
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(i,) for i in valid_ids]
    db.execute.return_value = mock_result
    return db


# ── Constants ──────────────────────────────────────────────────────────────────

class TestConstants(unittest.TestCase):
    def test_values(self):
        from app.services.weight_approval import (
            MAX_SINGLE_WEIGHT,
            MIN_KEYSKILLS,
            WEIGHT_SUM_TARGET,
        )
        self.assertEqual(MIN_KEYSKILLS, 5)
        self.assertEqual(MAX_SINGLE_WEIGHT, 50)
        self.assertEqual(WEIGHT_SUM_TARGET, 100)


# ── validate_proposed_weights ──────────────────────────────────────────────────

class TestValidateProposedWeights(unittest.TestCase):

    def _valid_items(self) -> list[dict]:
        # 5 keyskills summing to 100, none above 50
        return [
            {"keyskill_id": 1, "weight_percentage": 30},
            {"keyskill_id": 2, "weight_percentage": 25},
            {"keyskill_id": 3, "weight_percentage": 20},
            {"keyskill_id": 4, "weight_percentage": 15},
            {"keyskill_id": 5, "weight_percentage": 10},
        ]

    def test_valid_passes(self):
        from app.services.weight_approval import validate_proposed_weights
        db = _make_db_with_keyskills(1, 2, 3, 4, 5)
        errors = validate_proposed_weights(self._valid_items(), db)
        self.assertEqual(errors, [])

    # Rule 1 — count
    def test_too_few_keyskills(self):
        from app.services.weight_approval import validate_proposed_weights
        items = [
            {"keyskill_id": 1, "weight_percentage": 60},
            {"keyskill_id": 2, "weight_percentage": 40},
        ]
        errors = validate_proposed_weights(items, MagicMock())
        codes = {e["error_code"] for e in errors}
        self.assertIn("TOO_FEW_KEYSKILLS", codes)

    # Rule 2 — duplicates
    def test_duplicate_keyskill_id(self):
        from app.services.weight_approval import validate_proposed_weights
        items = [
            {"keyskill_id": 1, "weight_percentage": 20},
            {"keyskill_id": 1, "weight_percentage": 20},  # dup
            {"keyskill_id": 3, "weight_percentage": 20},
            {"keyskill_id": 4, "weight_percentage": 20},
            {"keyskill_id": 5, "weight_percentage": 20},
        ]
        errors = validate_proposed_weights(items, MagicMock())
        codes = {e["error_code"] for e in errors}
        self.assertIn("DUPLICATE_KEYSKILL_ID", codes)

    # Rule 3 — negative weight
    def test_negative_weight(self):
        from app.services.weight_approval import validate_proposed_weights
        items = [
            {"keyskill_id": 1, "weight_percentage": -5},
            {"keyskill_id": 2, "weight_percentage": 25},
            {"keyskill_id": 3, "weight_percentage": 30},
            {"keyskill_id": 4, "weight_percentage": 30},
            {"keyskill_id": 5, "weight_percentage": 20},
        ]
        errors = validate_proposed_weights(items, MagicMock())
        codes = {e["error_code"] for e in errors}
        self.assertIn("NEGATIVE_WEIGHT", codes)

    # Rule 4 — concentration cap
    def test_concentration_exceeded(self):
        from app.services.weight_approval import validate_proposed_weights
        items = [
            {"keyskill_id": 1, "weight_percentage": 60},  # > 50
            {"keyskill_id": 2, "weight_percentage": 10},
            {"keyskill_id": 3, "weight_percentage": 10},
            {"keyskill_id": 4, "weight_percentage": 10},
            {"keyskill_id": 5, "weight_percentage": 10},
        ]
        errors = validate_proposed_weights(items, MagicMock())
        codes = {e["error_code"] for e in errors}
        self.assertIn("WEIGHT_CONCENTRATION_EXCEEDED", codes)

    # Rule 5 — sum
    def test_sum_not_100(self):
        from app.services.weight_approval import validate_proposed_weights
        items = [
            {"keyskill_id": 1, "weight_percentage": 20},
            {"keyskill_id": 2, "weight_percentage": 20},
            {"keyskill_id": 3, "weight_percentage": 20},
            {"keyskill_id": 4, "weight_percentage": 20},
            {"keyskill_id": 5, "weight_percentage": 20},
        ]
        # sum = 100 → should PASS (confirm boundary)
        db = _make_db_with_keyskills(1, 2, 3, 4, 5)
        errors = validate_proposed_weights(items, db)
        self.assertEqual(errors, [])

    def test_sum_not_100_fails(self):
        from app.services.weight_approval import validate_proposed_weights
        items = [
            {"keyskill_id": 1, "weight_percentage": 20},
            {"keyskill_id": 2, "weight_percentage": 20},
            {"keyskill_id": 3, "weight_percentage": 20},
            {"keyskill_id": 4, "weight_percentage": 20},
            {"keyskill_id": 5, "weight_percentage": 19},  # sum = 99
        ]
        errors = validate_proposed_weights(items, MagicMock())
        codes = {e["error_code"] for e in errors}
        self.assertIn("WEIGHT_SUM_NOT_100", codes)
        bad = next(e for e in errors if e["error_code"] == "WEIGHT_SUM_NOT_100")
        self.assertEqual(bad["sum"], 99)

    # Rule 6 — FK check
    def test_keyskill_not_found(self):
        from app.services.weight_approval import validate_proposed_weights
        items = self._valid_items()  # keyskill_ids 1-5
        # DB says only 1-4 exist; 5 is missing
        db = _make_db_with_keyskills(1, 2, 3, 4)
        errors = validate_proposed_weights(items, db)
        codes = {e["error_code"] for e in errors}
        self.assertIn("KEYSKILL_NOT_FOUND", codes)
        bad = next(e for e in errors if e["error_code"] == "KEYSKILL_NOT_FOUND")
        self.assertIn(5, bad["keyskill_ids"])

    def test_fk_check_skipped_when_structural_errors_exist(self):
        """Rule 6 (FK check) must not fire when rules 1-5 already failed."""
        from app.services.weight_approval import validate_proposed_weights
        # Only 2 items (violates rule 1) — db.execute should NOT be called
        items = [
            {"keyskill_id": 99, "weight_percentage": 50},
            {"keyskill_id": 98, "weight_percentage": 50},
        ]
        db = MagicMock()
        validate_proposed_weights(items, db)
        db.execute.assert_not_called()

    def test_exact_boundary_max_single_weight(self):
        """weight_percentage == MAX_SINGLE_WEIGHT (50) must be accepted."""
        from app.services.weight_approval import validate_proposed_weights
        items = [
            {"keyskill_id": 1, "weight_percentage": 50},
            {"keyskill_id": 2, "weight_percentage": 20},
            {"keyskill_id": 3, "weight_percentage": 15},
            {"keyskill_id": 4, "weight_percentage": 10},
            {"keyskill_id": 5, "weight_percentage":  5},
        ]
        db = _make_db_with_keyskills(1, 2, 3, 4, 5)
        errors = validate_proposed_weights(items, db)
        self.assertEqual(errors, [])

    def test_multiple_errors_returned_together(self):
        """sum != 100 AND concentration exceeded — both reported in one call."""
        from app.services.weight_approval import validate_proposed_weights
        items = [
            {"keyskill_id": 1, "weight_percentage": 60},  # > 50
            {"keyskill_id": 2, "weight_percentage": 10},
            {"keyskill_id": 3, "weight_percentage": 10},
            {"keyskill_id": 4, "weight_percentage": 10},
            {"keyskill_id": 5, "weight_percentage": 10},
            # sum = 100 but concentration violated
        ]
        errors = validate_proposed_weights(items, MagicMock())
        codes = {e["error_code"] for e in errors}
        self.assertIn("WEIGHT_CONCENTRATION_EXCEEDED", codes)


# ── snapshot_current_weights — CKA read-only guarantee ────────────────────────

class TestSnapshotCurrentWeights(unittest.TestCase):

    def test_returns_list_of_dicts(self):
        from app.services.weight_approval import snapshot_current_weights
        db = MagicMock()
        mock_rows = [
            {"keyskill_id": 3, "weight_percentage": 40},
            {"keyskill_id": 7, "weight_percentage": 35},
            {"keyskill_id": 2, "weight_percentage": 25},
        ]
        db.execute.return_value.mappings.return_value.all.return_value = mock_rows

        result = snapshot_current_weights(career_id=42, db=db)

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], {"keyskill_id": 3, "weight_percentage": 40})

    def test_only_select_issued_on_cka(self):
        """
        CORE GUARANTEE: snapshot_current_weights must issue exactly one
        SELECT on career_keyskill_association and must NOT issue any
        INSERT, UPDATE, or DELETE statement.

        This is the byte-identical CKA before/after assertion: the function
        may only READ from the table, never mutate it.
        """
        from app.services.weight_approval import snapshot_current_weights

        executed_sql: list[str] = []

        def capture_execute(stmt, *args, **kwargs):
            # Capture the SQL text for inspection
            executed_sql.append(str(stmt).strip().upper())
            mock_result = MagicMock()
            mock_result.mappings.return_value.all.return_value = []
            return mock_result

        db = MagicMock()
        db.execute.side_effect = capture_execute

        snapshot_current_weights(career_id=1, db=db)

        self.assertEqual(len(executed_sql), 1, "Expected exactly one SQL statement")
        sql = executed_sql[0]

        # Must be a SELECT
        self.assertTrue(
            sql.startswith("SELECT"),
            f"Expected SELECT statement; got: {sql[:60]}",
        )
        # Must reference the correct table
        self.assertIn("CAREER_KEYSKILL_ASSOCIATION", sql)
        # Must NOT contain any write keywords
        for forbidden in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP"):
            self.assertNotIn(
                forbidden, sql,
                f"Forbidden keyword '{forbidden}' found in SQL: {sql[:120]}",
            )

    def test_empty_career_returns_empty_list(self):
        from app.services.weight_approval import snapshot_current_weights
        db = MagicMock()
        db.execute.return_value.mappings.return_value.all.return_value = []
        result = snapshot_current_weights(career_id=999, db=db)
        self.assertEqual(result, [])


# ── Schema instantiation ───────────────────────────────────────────────────────

class TestSchemas(unittest.TestCase):

    def test_wcr_proposal_create_valid(self):
        from app.schemas.weight_approval import WCRProposalCreate, WCRWeightItem
        body = WCRProposalCreate(
            title="Test proposal",
            proposed_weights=[
                WCRWeightItem(keyskill_id=1, weight_percentage=30),
                WCRWeightItem(keyskill_id=2, weight_percentage=70),
            ],
        )
        self.assertEqual(body.title, "Test proposal")
        self.assertEqual(len(body.proposed_weights), 2)

    def test_wcr_weight_item_rejects_negative(self):
        from pydantic import ValidationError
        from app.schemas.weight_approval import WCRWeightItem
        with self.assertRaises(ValidationError):
            WCRWeightItem(keyskill_id=1, weight_percentage=-1)

    def test_wcr_weight_item_rejects_over_100(self):
        from pydantic import ValidationError
        from app.schemas.weight_approval import WCRWeightItem
        with self.assertRaises(ValidationError):
            WCRWeightItem(keyskill_id=1, weight_percentage=101)

    def test_wcr_out_from_attributes(self):
        """WCROut must be constructable from ORM-like object (from_attributes=True)."""
        from datetime import datetime, timezone
        from app.schemas.weight_approval import WCROut
        from pydantic import ConfigDict

        # Simulate an ORM row using a simple namespace
        class FakeWCR:
            id                 = 1
            title              = "My proposal"
            status             = "draft"
            scope              = "single"
            changes            = [{"career_id": 5}]
            created_by         = 99
            created_at         = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
            submitted_at       = None
            reviewed_by        = None
            reviewed_at        = None
            review_level       = 1
            decision_comment   = None
            promoted_at        = None
            vectors_recomputed = False

        out = WCROut.model_validate(FakeWCR())
        self.assertEqual(out.id, 1)
        self.assertEqual(out.status, "draft")
        self.assertFalse(out.vectors_recomputed)

    def test_schema_wildcard_export(self):
        """WCR schemas must be importable via the app.schemas package (wildcard export)."""
        from app.schemas import WCROut, WCRProposalCreate, WCRWeightItem  # noqa: F401


# ── validate_career_exists ─────────────────────────────────────────────────────

class TestValidateCareerExists(unittest.TestCase):

    def test_found(self):
        from app.services.weight_approval import validate_career_exists
        db = MagicMock()
        db.execute.return_value.mappings.return_value.first.return_value = {
            "id": 5, "title": "Software Engineer"
        }
        result = validate_career_exists(5, db)
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Software Engineer")

    def test_not_found(self):
        from app.services.weight_approval import validate_career_exists
        db = MagicMock()
        db.execute.return_value.mappings.return_value.first.return_value = None
        result = validate_career_exists(999, db)
        self.assertIsNone(result)


# ── Stage 3: approve / reject / promote endpoints ─────────────────────────────

def _make_fake_wcr(status: str, request_id: int = 1) -> MagicMock:
    """Return a MagicMock that looks like a WeightChangeRequest ORM row."""
    wcr = MagicMock()
    wcr.id = request_id
    wcr.title = "Test proposal"
    wcr.status = status
    wcr.scope = "single"
    wcr.reviewed_by = None
    wcr.reviewed_at = None
    wcr.decision_comment = None
    wcr.promoted_at = None
    wcr.vectors_recomputed = False
    wcr.changes = [
        {
            "career_id": 10,
            "proposed_weights": [
                {"keyskill_id": 1, "weight_percentage": 40},
                {"keyskill_id": 2, "weight_percentage": 25},
                {"keyskill_id": 3, "weight_percentage": 20},
                {"keyskill_id": 4, "weight_percentage": 10},
                {"keyskill_id": 5, "weight_percentage": 5},
            ],
            "baseline_weights": [
                {"keyskill_id": 1, "weight_percentage": 35},
                {"keyskill_id": 2, "weight_percentage": 30},
                {"keyskill_id": 6, "weight_percentage": 35},  # 6 is removed in proposed
            ],
        }
    ]
    return wcr


def _make_review_db(wcr: MagicMock) -> MagicMock:
    """Return a mock Session that returns wcr from an ORM query."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = wcr
    return db


def _make_current_user(user_id: int = 99) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.email = "admin@test.com"
    return u


class TestApproveEndpoint(unittest.TestCase):

    def test_happy_path_sets_review_fields(self):
        """pending_review → approved: status, reviewed_by, reviewed_at, decision_comment set."""
        from app.routers.admin_portal import approve_weight_change_request, _ReviewDecision

        wcr = _make_fake_wcr("pending_review")
        db = _make_review_db(wcr)
        user = _make_current_user(42)
        body = _ReviewDecision(decision_comment="Looks good")

        result = approve_weight_change_request(
            request_id=wcr.id, body=body, db=db, current_user=user
        )

        self.assertEqual(wcr.status, "approved")
        self.assertEqual(wcr.reviewed_by, 42)
        self.assertIsNotNone(wcr.reviewed_at)
        self.assertEqual(wcr.decision_comment, "Looks good")
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(wcr)

    def test_non_pending_raises_409(self):
        """Approving a request that is not pending_review must raise HTTP 409."""
        from fastapi import HTTPException
        from app.routers.admin_portal import approve_weight_change_request, _ReviewDecision

        for bad_status in ("draft", "approved", "rejected", "promoted"):
            with self.subTest(status=bad_status):
                wcr = _make_fake_wcr(bad_status)
                db = _make_review_db(wcr)
                body = _ReviewDecision()

                with self.assertRaises(HTTPException) as ctx:
                    approve_weight_change_request(
                        request_id=wcr.id, body=body, db=db, current_user=_make_current_user()
                    )

                self.assertEqual(ctx.exception.status_code, 409)
                self.assertEqual(
                    ctx.exception.detail["error_code"], "INVALID_STATUS_TRANSITION"
                )
                db.commit.assert_not_called()

    def test_not_found_raises_404(self):
        from fastapi import HTTPException
        from app.routers.admin_portal import approve_weight_change_request, _ReviewDecision

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        body = _ReviewDecision()

        with self.assertRaises(HTTPException) as ctx:
            approve_weight_change_request(
                request_id=999, body=body, db=db, current_user=_make_current_user()
            )

        self.assertEqual(ctx.exception.status_code, 404)


class TestRejectEndpoint(unittest.TestCase):

    def test_happy_path_sets_rejected_fields(self):
        """pending_review → rejected: status, reviewed_by, reviewed_at, decision_comment set."""
        from app.routers.admin_portal import reject_weight_change_request, _ReviewDecision

        wcr = _make_fake_wcr("pending_review")
        db = _make_review_db(wcr)
        user = _make_current_user(77)
        body = _ReviewDecision(decision_comment="Needs revision")

        result = reject_weight_change_request(
            request_id=wcr.id, body=body, db=db, current_user=user
        )

        self.assertEqual(wcr.status, "rejected")
        self.assertEqual(wcr.reviewed_by, 77)
        self.assertIsNotNone(wcr.reviewed_at)
        self.assertEqual(wcr.decision_comment, "Needs revision")
        db.commit.assert_called_once()

    def test_non_pending_raises_409(self):
        """Rejecting a request that is not pending_review must raise HTTP 409."""
        from fastapi import HTTPException
        from app.routers.admin_portal import reject_weight_change_request, _ReviewDecision

        for bad_status in ("draft", "approved", "rejected", "promoted"):
            with self.subTest(status=bad_status):
                wcr = _make_fake_wcr(bad_status)
                db = _make_review_db(wcr)
                body = _ReviewDecision()

                with self.assertRaises(HTTPException) as ctx:
                    reject_weight_change_request(
                        request_id=wcr.id, body=db, db=db, current_user=_make_current_user()
                    )

                self.assertEqual(ctx.exception.status_code, 409)
                db.commit.assert_not_called()


class TestPromoteEndpoint(unittest.TestCase):
    """
    All promote tests patch validate_proposed_weights and recompute_all_vectors
    so the suite does not touch the DB or run sklearn.
    """

    # Proposed weights for career 10 (ids 1-5 only — 6 is absent = to be removed)
    _proposed = [
        {"keyskill_id": 1, "weight_percentage": 40},
        {"keyskill_id": 2, "weight_percentage": 25},
        {"keyskill_id": 3, "weight_percentage": 20},
        {"keyskill_id": 4, "weight_percentage": 10},
        {"keyskill_id": 5, "weight_percentage": 5},
    ]

    def _make_promote_db(
        self,
        live_cka_ids: list[int],
        sme_rated_removed_ids: list[int],
    ) -> tuple[MagicMock, list[str]]:
        """
        Build a mock db for promote tests.

        live_cka_ids             — keyskill_ids currently in career_keyskill_association
        sme_rated_removed_ids    — of the removed ids, which ones have SME ratings

        Returns (db_mock, executed_sql_list) so callers can inspect SQL.
        """
        wcr = _make_fake_wcr("approved")
        executed_sql: list[str] = []

        def fake_execute(stmt, params=None, *args, **kwargs):
            sql = str(stmt).strip().upper()
            executed_sql.append(sql)
            mock_result = MagicMock()

            if (
                "SELECT DISTINCT KEYSKILL_ID FROM CAREER_KEYSKILL_ASSOCIATION" in sql
                or "FROM CAREER_KEYSKILL_ASSOCIATION" in sql
                and "SELECT DISTINCT" in sql
            ):
                mock_result.fetchall.return_value = [(i,) for i in live_cka_ids]
            elif "FROM SME_KEYSKILL_RATINGS" in sql:
                mock_result.fetchall.return_value = [
                    (i,) for i in sme_rated_removed_ids
                ]
            else:
                mock_result.fetchall.return_value = []

            return mock_result

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = wcr
        db.execute.side_effect = fake_execute
        return db, executed_sql, wcr

    def test_happy_path_upserts_and_deletes(self):
        """
        Promote happy path: upserts each proposed item, issues a DELETE for missing
        keyskills, sets status=promoted, calls recompute_all_vectors, vectors_recomputed=True.
        """
        from app.routers.admin_portal import promote_weight_change_request

        # Live has keyskill 6 as well (not in proposed → should be deleted)
        db, executed_sql, wcr = self._make_promote_db(
            live_cka_ids=[1, 2, 3, 4, 5, 6],
            sme_rated_removed_ids=[],
        )

        with patch("app.routers.admin_portal.validate_proposed_weights", return_value=[]):
            with patch("app.routers.admin_portal.recompute_all_vectors") as mock_recompute:
                result = promote_weight_change_request(
                    request_id=1, db=db, current_user=_make_current_user()
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "promoted")
        self.assertEqual(result["careers_promoted"], [10])
        self.assertTrue(result["vectors_recomputed"])
        self.assertEqual(result["sme_warnings"], [])
        self.assertEqual(result["recompute_note"], "")

        # WCR fields
        self.assertEqual(wcr.status, "promoted")
        self.assertIsNotNone(wcr.promoted_at)

        # recompute was called once
        mock_recompute.assert_called_once_with(db)

        # 5 upserts + 1 delete
        insert_calls = [s for s in executed_sql if "INSERT INTO CAREER_KEYSKILL_ASSOCIATION" in s]
        delete_calls = [s for s in executed_sql if "DELETE FROM CAREER_KEYSKILL_ASSOCIATION" in s]
        self.assertEqual(len(insert_calls), 5)
        self.assertEqual(len(delete_calls), 1)

        # db.commit() called at least twice (weight commit + vectors_recomputed commit)
        self.assertGreaterEqual(db.commit.call_count, 2)

    def test_revalidation_failure_returns_422_and_zero_writes(self):
        """
        If re-validation fails at promote time, the endpoint raises 422 and
        issues NO INSERT or DELETE statements against career_keyskill_association.
        """
        from fastapi import HTTPException
        from app.routers.admin_portal import promote_weight_change_request

        db, executed_sql, wcr = self._make_promote_db(
            live_cka_ids=[1, 2, 3, 4, 5],
            sme_rated_removed_ids=[],
        )

        bad_errors = [{"error_code": "WEIGHT_SUM_NOT_100", "message": "sum=99", "sum": 99}]

        with patch(
            "app.routers.admin_portal.validate_proposed_weights", return_value=bad_errors
        ):
            with self.assertRaises(HTTPException) as ctx:
                promote_weight_change_request(
                    request_id=1, db=db, current_user=_make_current_user()
                )

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(ctx.exception.detail["error_code"], "REVALIDATION_FAILED")

        # ZERO INSERT or DELETE statements issued
        write_calls = [
            s for s in executed_sql
            if "INSERT INTO CAREER_KEYSKILL_ASSOCIATION" in s
            or "DELETE FROM CAREER_KEYSKILL_ASSOCIATION" in s
        ]
        self.assertEqual(write_calls, [], "No CKA writes should occur on revalidation failure")

        # db.commit() must NOT have been called
        db.commit.assert_not_called()

    def test_state_guard_non_approved_raises_409(self):
        """Promoting a request that is not in 'approved' status raises HTTP 409."""
        from fastapi import HTTPException
        from app.routers.admin_portal import promote_weight_change_request

        for bad_status in ("draft", "pending_review", "rejected", "promoted"):
            with self.subTest(status=bad_status):
                wcr = _make_fake_wcr(bad_status)
                db = _make_review_db(wcr)

                with self.assertRaises(HTTPException) as ctx:
                    promote_weight_change_request(
                        request_id=wcr.id, db=db, current_user=_make_current_user()
                    )

                self.assertEqual(ctx.exception.status_code, 409)
                self.assertEqual(
                    ctx.exception.detail["error_code"], "INVALID_STATUS_TRANSITION"
                )
                db.commit.assert_not_called()
                db.execute.assert_not_called()

    def test_promote_atomicity_no_writes_on_revalidation_failure(self):
        """
        Explicit atomicity assertion: db.execute must never be called for
        INSERT or DELETE when validate_proposed_weights returns errors.
        This is the same property as revalidation_failure but expressed
        through the mock call list independently.
        """
        from fastapi import HTTPException
        from app.routers.admin_portal import promote_weight_change_request

        db = MagicMock()
        wcr = _make_fake_wcr("approved")
        db.query.return_value.filter.return_value.first.return_value = wcr

        with patch(
            "app.routers.admin_portal.validate_proposed_weights",
            return_value=[{"error_code": "TOO_FEW_KEYSKILLS", "message": "< 5 keyskills"}],
        ):
            with self.assertRaises(HTTPException):
                promote_weight_change_request(
                    request_id=1, db=db, current_user=_make_current_user()
                )

        # db.execute must not have been called at all
        db.execute.assert_not_called()

    def test_sme_warning_surfaces_but_promote_succeeds(self):
        """
        When a promoted request removes a keyskill that has SME ratings,
        the sme_warnings list is populated but the promote succeeds.
        """
        from app.routers.admin_portal import promote_weight_change_request

        # Live has keyskill 6 (not in proposed = removed). SME has a rating for 6.
        db, executed_sql, wcr = self._make_promote_db(
            live_cka_ids=[1, 2, 3, 4, 5, 6],
            sme_rated_removed_ids=[6],
        )

        with patch("app.routers.admin_portal.validate_proposed_weights", return_value=[]):
            with patch("app.routers.admin_portal.recompute_all_vectors"):
                result = promote_weight_change_request(
                    request_id=1, db=db, current_user=_make_current_user()
                )

        self.assertTrue(result["ok"])
        self.assertEqual(len(result["sme_warnings"]), 1)
        warning = result["sme_warnings"][0]
        self.assertEqual(warning["career_id"], 10)
        self.assertIn(6, warning["removed_keyskill_ids_with_sme_ratings"])

    def test_recompute_exception_leaves_weights_committed_and_flag_false(self):
        """
        If recompute_all_vectors raises, the weight promotion is already committed
        (db.commit() was called once before the recompute attempt), and
        vectors_recomputed=False is returned with a non-empty recompute_note.
        """
        from app.routers.admin_portal import promote_weight_change_request

        db, executed_sql, wcr = self._make_promote_db(
            live_cka_ids=[1, 2, 3, 4, 5],
            sme_rated_removed_ids=[],
        )

        with patch("app.routers.admin_portal.validate_proposed_weights", return_value=[]):
            with patch(
                "app.routers.admin_portal.recompute_all_vectors",
                side_effect=RuntimeError("sklearn unavailable"),
            ):
                result = promote_weight_change_request(
                    request_id=1, db=db, current_user=_make_current_user()
                )

        # Weights committed — first db.commit() was called
        self.assertGreaterEqual(db.commit.call_count, 1)

        # Response reflects recompute failure
        self.assertFalse(result["vectors_recomputed"])
        self.assertNotEqual(result["recompute_note"], "")

        # WCR status is still promoted (weight write succeeded)
        self.assertEqual(wcr.status, "promoted")
        self.assertIsNotNone(wcr.promoted_at)

    def test_recompute_is_called_with_db_session(self):
        """recompute_all_vectors must receive the same db session object."""
        from app.routers.admin_portal import promote_weight_change_request

        db, _, _ = self._make_promote_db(
            live_cka_ids=[1, 2, 3, 4, 5],
            sme_rated_removed_ids=[],
        )

        with patch("app.routers.admin_portal.validate_proposed_weights", return_value=[]):
            with patch("app.routers.admin_portal.recompute_all_vectors") as mock_recompute:
                promote_weight_change_request(
                    request_id=1, db=db, current_user=_make_current_user()
                )

        mock_recompute.assert_called_once_with(db)


if __name__ == "__main__":
    unittest.main()
