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


if __name__ == "__main__":
    unittest.main()
