"""
Admin questions router.
Exposes 2 endpoints under /v1/admin/:
  POST /questions       — create a single question via JSON (B3)
  POST /questions/bulk  — create questions in bulk via JSON array (B4)

Role gate: admin only (inherited from router dependency).
Reads/writes: questions table.
"""
import logging
from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.deps import get_db
from app import models
from app.schemas import (
    User as UserSchema,
    AdminQuestionCreateRequest,
    AdminQuestionCreateResponse,
    AdminQuestionBulkItem,
    AdminQuestionBulkResponse,
    AdminQuestionBulkErrorEntry,
)
from app.auth.auth import require_role, get_current_active_user
from app.validators.question_ingestion import validate_question_row, RowValidationError

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)


def _parse_optional_int(value):
    """
    Convert optional values to int for DB integer columns.
    Accepts:
      - None, "", "null" -> None
      - "12" -> 12
      - 12 -> 12
    Raises:
      - ValueError for non-numeric strings.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s == "" or s.lower() == "null":
        return None
    return int(s)


# ============================================================
# B3: Single question creation via JSON
# ============================================================

@router.post(
    "/questions",
    response_model=AdminQuestionCreateResponse,
    status_code=201,
    summary="Create a single Question via API (JSON) using shared validator (B3)",
)
def create_question_api(
    payload: AdminQuestionCreateRequest,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    B3 spec:
    - Admin-only (router dependency)
    - Input: JSON body
    - Reuses shared validate_question_row() (B2)
    - No DB writes before validation passes
    - Duplicate question_id => 409 Conflict (explicit error)

    Important:
    - `id` is the internal DB PK (integer)
    - `question_code` is the canonical/external identifier used by student flows
    """
    row_for_validation = payload.dict()
    validated = validate_question_row(db=db, row=row_for_validation, row_index=1)

    if isinstance(validated, RowValidationError):
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "ROW_VALIDATION_ERROR",
                "errors": [{"field": e.field, "message": e.message} for e in validated.errors],
            },
        )

    try:
        qid_int = int(str(payload.question_id).strip())
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_QUESTION_ID",
                "message": f"question_id must be an integer-like value (got '{payload.question_id}')",
                "field": "question_id",
            },
        )

    try:
        prereq_int = _parse_optional_int(payload.prerequisite_qid)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "INVALID_PREREQUISITE_QID",
                "message": "prerequisite_qid must be an integer (or empty/null)",
                "field": "prerequisite_qid",
            },
        )

    q = models.Question(
        id=qid_int,
        assessment_version=validated.assessment_version,
        question_text_en=validated.question_text_en,
        question_text_hi=(validated.question_text_hi or "").strip() or None,
        question_text_ta=(validated.question_text_ta or "").strip() or None,
        skill_id=validated.skill_id,
        weight=payload.weight if payload.weight is not None else 1,
        group_id=(payload.group_id or "").strip() or None,
        prerequisite_qid=prereq_int,
        question_code=(payload.question_code or "").strip() or None,
    )

    db.add(q)
    try:
        db.commit()
        db.refresh(q)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "status": "error",
                "error_code": "DUPLICATE_QUESTION_ID",
                "message": f"Question with id '{qid_int}' already exists.",
                "field": "question_id",
            },
        )
    except Exception as e:
        db.rollback()
        logger.exception("create_question_api: failed DB write")
        raise HTTPException(status_code=500, detail=f"Failed to create question: {e}")

    return AdminQuestionCreateResponse(
        status="created",
        created={
            "question_id": q.id,
            "assessment_version": q.assessment_version,
            "skill_id": q.skill_id,
        },
        errors=[],
    )


# ============================================================
# B4: Bulk question creation via JSON array
# ============================================================

@router.post(
    "/questions/bulk",
    response_model=AdminQuestionBulkResponse,
    status_code=200,
    summary="Create Questions in bulk via API (JSON array) using shared validator (B4)",
)
def bulk_create_questions_api(
    payloads: List[AdminQuestionBulkItem],
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    B4 spec:
    - Admin-only (router dependency)
    - Input: JSON ARRAY
    - Validates first (no writes), writes later
    - Continues on error
    - Skips duplicates (both within request + existing DB rows)
    - Must persist question_code (canonical external identifier)
    - Must store prerequisite_qid as int/None (INTEGER FK column)
    """
    created = 0
    skipped = 0
    errors: List[AdminQuestionBulkErrorEntry] = []

    # Pre-check payload-level duplicates for question_id
    seen_qids = set()
    duplicate_indexes = set()
    for i, item in enumerate(payloads):
        qid = (item.question_id or "").strip()
        if not qid:
            duplicate_indexes.add(i)
            continue
        if qid in seen_qids:
            duplicate_indexes.add(i)
        else:
            seen_qids.add(qid)

    # PASS 1: Validate & normalize (NO DB WRITES)
    valid_items: List[Dict] = []
    valid_meta: List[Dict] = []

    for i, item in enumerate(payloads):
        qid = (item.question_id or "").strip()

        if i in duplicate_indexes:
            skipped += 1
            errors.append(
                AdminQuestionBulkErrorEntry(
                    index=i,
                    question_id=qid or None,
                    errors=[{"field": "question_id", "message": "duplicate question_id in request payload"}],
                )
            )
            continue

        row_for_validation = item.dict()
        validated = validate_question_row(db=db, row=row_for_validation, row_index=i)

        if isinstance(validated, RowValidationError):
            skipped += 1
            errors.append(
                AdminQuestionBulkErrorEntry(
                    index=i,
                    question_id=qid or None,
                    errors=[{"field": e.field, "message": e.message} for e in validated.errors],
                )
            )
            continue

        try:
            qid_int = int(qid)
        except Exception:
            skipped += 1
            errors.append(
                AdminQuestionBulkErrorEntry(
                    index=i,
                    question_id=qid or None,
                    errors=[{"field": "question_id", "message": f"must be an integer-like value (got '{qid}')"}],
                )
            )
            continue

        try:
            prereq_int = _parse_optional_int(item.prerequisite_qid)
        except ValueError:
            skipped += 1
            errors.append(
                AdminQuestionBulkErrorEntry(
                    index=i,
                    question_id=qid or None,
                    errors=[{"field": "prerequisite_qid", "message": "must be an integer (or empty/null)"}],
                )
            )
            continue

        valid_items.append(
            {
                "id": qid_int,
                "assessment_version": validated.assessment_version,
                "question_text_en": validated.question_text_en,
                "question_text_hi": (validated.question_text_hi or "").strip() or None,
                "question_text_ta": (validated.question_text_ta or "").strip() or None,
                "skill_id": validated.skill_id,
                "weight": item.weight if item.weight is not None else 1,
                "group_id": (item.group_id or "").strip() or None,
                "prerequisite_qid": prereq_int,
                "question_code": (getattr(item, "question_code", None) or "").strip() or None,
            }
        )
        valid_meta.append({"index": i, "question_id": qid})

    # PASS 2: Write valid rows (DB writes happen ONLY here)
    for meta, row in zip(valid_meta, valid_items):
        qid = meta["question_id"]
        q = models.Question(**row)
        db.add(q)
        try:
            db.flush()
            created += 1
        except IntegrityError:
            db.rollback()
            skipped += 1
            errors.append(
                AdminQuestionBulkErrorEntry(
                    index=meta["index"],
                    question_id=qid,
                    errors=[{"field": "question_id", "message": "already exists"}],
                )
            )
        except Exception as e:
            db.rollback()
            skipped += 1
            logger.exception("bulk_create_questions_api: unexpected DB error")
            errors.append(
                AdminQuestionBulkErrorEntry(
                    index=meta["index"],
                    question_id=qid,
                    errors=[{"field": "db", "message": f"failed to insert: {e}"}],
                )
            )

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("bulk_create_questions_api: commit failed")
        raise HTTPException(status_code=500, detail=f"Bulk insert commit failed: {e}")

    return AdminQuestionBulkResponse(created=created, skipped=skipped, errors=errors)
