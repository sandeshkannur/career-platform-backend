from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException,
    Form,
)
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
import csv
import io
import logging
from typing import List, Dict

from app.deps import get_db
from app import models
from app.models import (
    CareerCluster,
    Career,
    KeySkill,
    Student,
    Skill,
    StudentSkillMap,
    StudentKeySkillMap,
    User as UserModel,
    career_keyskill_association,
    Question,
    AQFacet,
    QuestionFacetTag,
)
from app.schemas import (
    UploadResponse,
    UploadQuestionsResult,
    RoleChange,
    GuardianAssign,
    User as UserSchema,
    QuestionFacetTagUploadRow,
    AdminQuestionCreateRequest,
    AdminQuestionCreateResponse,
    AdminQuestionBulkItem,
    AdminQuestionBulkResponse,
    AdminQuestionBulkErrorEntry,
)
from app.auth.auth import require_role, get_current_active_user

# ✅ B2 shared validation import
from app.validators.question_ingestion import (
    validate_question_row,
    RowValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["admin"],
    # Enforce admin at router level
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
# 1. UPLOAD CAREER CLUSTERS
# ============================================================

@router.post(
    "/upload-career-clusters",
    response_model=UploadResponse,
    summary="Bulk upload Career Clusters via CSV",
)
async def upload_career_clusters(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    Expected CSV headers (exact):
      cluster_id,cluster_name

    Behavior:
    - If cluster exists, update name.
    - Else insert.
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text = (await file.read()).decode("utf-8-sig")
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))

    expected_fields = {"cluster_id", "cluster_name"}
    if set(reader.fieldnames or []) != expected_fields:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns exactly {expected_fields}, but got {reader.fieldnames}",
        )

    inserted = 0
    updated = 0
    skipped = 0

    for row in reader:
        cid = (row.get("cluster_id") or "").strip()
        cname = (row.get("cluster_name") or "").strip()

        if not cid or not cname:
            skipped += 1
            continue

        existing = db.query(CareerCluster).filter_by(cluster_id=cid).first()
        if existing:
            if (existing.cluster_name or "").strip() != cname:
                existing.cluster_name = cname
                updated += 1
            else:
                skipped += 1
            continue

        db.add(CareerCluster(cluster_id=cid, cluster_name=cname))
        inserted += 1

    db.commit()
    logger.info(f"upload-career-clusters: inserted={inserted}, updated={updated}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}


# ============================================================
# 2. UPLOAD CAREERS
# ============================================================

@router.post(
    "/upload-careers",
    response_model=UploadResponse,
    summary="Bulk upload Careers via CSV",
)
async def upload_careers(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    Expected CSV headers (exact):
      career_id,career_name,cluster_id

    Behavior:
    - If career exists, update fields.
    - Else insert.
    - cluster_id must exist.
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text = (await file.read()).decode("utf-8-sig")
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))

    expected_fields = {"career_id", "career_name", "cluster_id"}
    if set(reader.fieldnames or []) != expected_fields:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns exactly {expected_fields}, but got {reader.fieldnames}",
        )

    inserted = 0
    updated = 0
    skipped = 0

    for row in reader:
        career_id = (row.get("career_id") or "").strip()
        career_name = (row.get("career_name") or "").strip()
        cluster_id = (row.get("cluster_id") or "").strip()

        if not career_id or not career_name or not cluster_id:
            skipped += 1
            continue

        cluster = db.query(CareerCluster).filter_by(cluster_id=cluster_id).first()
        if not cluster:
            skipped += 1
            continue

        existing = db.query(Career).filter_by(career_id=career_id).first()
        if existing:
            changed = False
            if (existing.career_name or "").strip() != career_name:
                existing.career_name = career_name
                changed = True
            if (existing.cluster_id or "").strip() != cluster_id:
                existing.cluster_id = cluster_id
                changed = True

            if changed:
                updated += 1
            else:
                skipped += 1
            continue

        db.add(Career(career_id=career_id, career_name=career_name, cluster_id=cluster_id))
        inserted += 1

    db.commit()
    logger.info(f"upload-careers: inserted={inserted}, updated={updated}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}


# ============================================================
# 3. UPLOAD KEY SKILLS
# ============================================================

@router.post(
    "/upload-keyskills",
    response_model=UploadResponse,
    summary="Bulk upload KeySkills via CSV",
)
async def upload_keyskills(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    Expected CSV headers (exact):
      keyskill_id,keyskill_name

    Behavior:
    - If exists, update name.
    - Else insert.
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text = (await file.read()).decode("utf-8-sig")
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))

    expected_fields = {"keyskill_id", "keyskill_name"}
    if set(reader.fieldnames or []) != expected_fields:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns exactly {expected_fields}, but got {reader.fieldnames}",
        )

    inserted = 0
    updated = 0
    skipped = 0

    for row in reader:
        kid = (row.get("keyskill_id") or "").strip()
        kname = (row.get("keyskill_name") or "").strip()

        if not kid or not kname:
            skipped += 1
            continue

        existing = db.query(KeySkill).filter_by(keyskill_id=kid).first()
        if existing:
            if (existing.keyskill_name or "").strip() != kname:
                existing.keyskill_name = kname
                updated += 1
            else:
                skipped += 1
            continue

        db.add(KeySkill(keyskill_id=kid, keyskill_name=kname))
        inserted += 1

    db.commit()
    logger.info(f"upload-keyskills: inserted={inserted}, updated={updated}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}


# ============================================================
# 4. CAREER ↔ KEYSKILL MAPPING
# ============================================================

@router.post(
    "/upload-career-keyskill-map",
    response_model=UploadResponse,
    summary="Bulk upload Career ↔ KeySkill mapping via CSV",
)
async def upload_career_keyskill_map(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    Expected CSV headers (exact):
      career_id,keyskill_id

    Behavior:
    - Inserts into association table.
    - Skips invalid FK rows.
    - Skips duplicates (idempotent-ish).
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text = (await file.read()).decode("utf-8-sig")
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))

    expected_fields = {"career_id", "keyskill_id"}
    if set(reader.fieldnames or []) != expected_fields:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns exactly {expected_fields}, but got {reader.fieldnames}",
        )

    inserted = 0
    skipped = 0

    for row in reader:
        career_id = (row.get("career_id") or "").strip()
        keyskill_id = (row.get("keyskill_id") or "").strip()

        if not career_id or not keyskill_id:
            skipped += 1
            continue

        career = db.query(Career).filter_by(career_id=career_id).first()
        keyskill = db.query(KeySkill).filter_by(keyskill_id=keyskill_id).first()
        if not career or not keyskill:
            skipped += 1
            continue

        # Insert into association table if not exists
        exists = db.execute(
            career_keyskill_association.select().where(
                (career_keyskill_association.c.career_id == career_id)
                & (career_keyskill_association.c.keyskill_id == keyskill_id)
            )
        ).first()

        if exists:
            skipped += 1
            continue

        db.execute(
            career_keyskill_association.insert().values(
                career_id=career_id, keyskill_id=keyskill_id
            )
        )
        inserted += 1

    db.commit()
    logger.info(f"upload-career-keyskill-map: inserted={inserted}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}


# ============================================================
# ✅ B3. API-BASED QUESTION CREATION (JSON)
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

    # Convert payload -> dict to match validator signature
    row_for_validation = payload.dict()

    validated = validate_question_row(db=db, row=row_for_validation, row_index=1)

    # Validation failure (400) - do not write anything to DB
    if isinstance(validated, RowValidationError):
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "ROW_VALIDATION_ERROR",
                "errors": [{"field": e.field, "message": e.message} for e in validated.errors],
            },
        )

    # DB write ONLY after validation succeeds
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

    # prerequisite_qid is stored as INTEGER FK -> must be int/None
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

        # Optional fields supported by your questions table
        weight=payload.weight if payload.weight is not None else 1,
        group_id=(payload.group_id or "").strip() or None,
        prerequisite_qid=prereq_int,

        # Canonical external identifier (must be persisted if supplied)
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
# ✅ B4. API-BASED BULK QUESTION CREATION (JSON ARRAY)
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
    - Must persist `question_code` (canonical external identifier)
    - Must store `prerequisite_qid` as int/None (INTEGER FK column)
    """

    created = 0
    skipped = 0
    errors: List[AdminQuestionBulkErrorEntry] = []

    # ---------------------------
    # Pre-check payload-level duplicates for question_id (string compare after strip)
    # ---------------------------
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

    # ---------------------------
    # PASS 1: Validate & normalize (NO DB WRITES)
    # ---------------------------
    valid_items: List[Dict] = []   # insert-ready dicts
    valid_meta: List[Dict] = []    # index + question_id for error reporting

    for i, item in enumerate(payloads):
        qid = (item.question_id or "").strip()

        # Skip payload-level duplicates
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

        # Convert to dict to match validator signature
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

        # id is INTEGER PK in DB
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

        # prerequisite_qid is INTEGER FK -> must be int/None
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

        # Build insert-ready dict (still NO DB write)
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
                # ✅ Persist canonical identifier (external)
                "question_code": (getattr(item, "question_code", None) or "").strip() or None,
            }
        )
        valid_meta.append({"index": i, "question_id": qid})

    # ---------------------------
    # PASS 2: Write valid rows (DB writes happen ONLY here)
    # Flush each row to catch per-row IntegrityError without killing whole batch.
    # ---------------------------
    for meta, row in zip(valid_meta, valid_items):
        qid = meta["question_id"]

        q = models.Question(**row)
        db.add(q)

        try:
            db.flush()  # detect duplicates early
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

    # Final commit for the successful inserts
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("bulk_create_questions_api: commit failed")
        raise HTTPException(status_code=500, detail=f"Bulk insert commit failed: {e}")

    return AdminQuestionBulkResponse(created=created, skipped=skipped, errors=errors)


# ============================================================
# 5. STUDENT SKILL MAPS
# ============================================================

@router.post(
    "/student-skill-map",
    summary="Bulk map Student ↔ Skill",
)
def student_skill_map(
    mappings: List[Dict[str, int]],
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    inserted = 0
    for item in mappings:
        sid = item.get("student_id")
        kid = item.get("skill_id")
        if not db.query(Student).get(sid) or not db.query(Skill).get(kid):
            raise HTTPException(status_code=400, detail="Invalid student_id or skill_id")

        db.add(StudentSkillMap(student_id=sid, skill_id=kid))
        inserted += 1

    db.commit()
    return {"status": "success", "inserted": inserted}


@router.post(
    "/student-keyskill-map",
    summary="Bulk map Student ↔ KeySkill",
)
def student_keyskill_map(
    mappings: List[Dict[str, int]],
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    inserted = 0
    for item in mappings:
        sid = item.get("student_id")
        kkid = item.get("keyskill_id")
        if not db.query(Student).get(sid) or not db.query(KeySkill).get(kkid):
            raise HTTPException(status_code=400, detail="Invalid student_id or keyskill_id")

        db.add(StudentKeySkillMap(student_id=sid, keyskill_id=kkid))
        inserted += 1

    db.commit()
    return {"status": "success", "inserted": inserted}


# ============================================================
# 6. USER MANAGEMENT
# ============================================================

@router.get(
    "/list-users",
    response_model=List[UserSchema],
    summary="List all users",
)
def list_users(
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    return db.query(UserModel).all()


@router.post(
    "/change-role/{user_id}",
    response_model=UserSchema,
    summary="Change a user’s role",
)
def change_role(
    user_id: int,
    payload: RoleChange,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    user = db.query(UserModel).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = payload.role
    db.commit()
    db.refresh(user)

    return user


@router.post(
    "/assign-guardian/{user_id}",
    response_model=UserSchema,
    summary="Assign guardian to a user",
)
def assign_guardian(
    user_id: int,
    payload: GuardianAssign,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    user = db.query(UserModel).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.guardian_email = payload.guardian_email
    db.commit()
    db.refresh(user)

    return user


# ============================================================
# 7. UPLOAD QUESTIONS (B1)
# ============================================================

@router.post(
    "/upload-questions",
    response_model=UploadQuestionsResult,
    summary="Bulk upload Questions via CSV (versioned)",
)
async def upload_questions(
    assessment_version: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    B1 spec:
    - Admin-only (router dependency)
    - Input: multipart/form-data with assessment_version + CSV
    - Strict headers
    - Reads: skills
    - Writes: questions
    - Output: {uploaded:int, skipped:int, errors:list}
    - Non-idempotent: duplicates are skipped

    Notes:
    - `id` is INTERNAL DB PK (integer)
    - `question_code` is the CANONICAL / EXTERNAL identifier used by student flows
    - `prerequisite_qid` is INTEGER FK -> must be int/None
    """
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    raw = await file.read()
    # Excel often writes UTF-8 with BOM -> utf-8-sig handles that safely.
    text = raw.decode("utf-8-sig", errors="replace")

    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))

    # Strict header validation: allow exactly one of the two supported sets (in exact order)
    expected_headers_a = [
        "id",
        "question_code",
        "question_text_en",
        "question_text_hi",
        "question_text_ta",
        "skill_id",
        "weight",
        "group_id",
        "prerequisite_qid",
    ]
    expected_headers_b = [
        "question_id",
        "question_code",
        "question_text_en",
        "question_text_hi",
        "question_text_ta",
        "skill_id",
        "weight",
        "group_id",
        "prerequisite_qid",
    ]

    actual_headers = reader.fieldnames or []
    if actual_headers != expected_headers_a and actual_headers != expected_headers_b:
        raise HTTPException(
            status_code=400,
            detail=f"Header mismatch. Expected exactly {expected_headers_a} OR {expected_headers_b} but got {actual_headers}",
        )

    uploaded = 0
    skipped = 0
    errors: List[str] = []

    for row_num, row in enumerate(reader, start=2):
        # Normalize id field (support both id and question_id)
        qid = (row.get("id") or row.get("question_id") or "").strip()
        if not qid:
            skipped += 1
            errors.append(f"Row {row_num}: missing id/question_id")
            continue

        # DB PK is integer
        try:
            qid_int = int(qid)
        except ValueError:
            skipped += 1
            errors.append(f"Row {row_num}: question id must be integer (got '{qid}')")
            continue

        # Non-idempotent behavior: skip if PK already exists
        if db.query(models.Question).filter_by(id=qid_int).first():
            skipped += 1
            errors.append(f"Row {row_num}: duplicate question id '{qid_int}'")
            continue

        # B2 shared validation (no DB write before validation passes)
        row_for_validation = dict(row)
        row_for_validation["assessment_version"] = (assessment_version or "").strip()

        validated = validate_question_row(db=db, row=row_for_validation, row_index=row_num)
        if isinstance(validated, RowValidationError):
            skipped += 1
            for fe in validated.errors:
                errors.append(f"Row {row_num}: {fe.field} - {fe.message}")
            continue

        # weight (optional default 1)
        weight_raw = (row.get("weight") or "1").strip()
        try:
            weight = int(weight_raw)
        except Exception:
            skipped += 1
            errors.append(f"Row {row_num}: weight must be an integer (got '{weight_raw}')")
            continue

        # prerequisite_qid is INTEGER FK -> must be int/None
        try:
            prereq_int = _parse_optional_int(row.get("prerequisite_qid"))
        except ValueError:
            skipped += 1
            errors.append(f"Row {row_num}: prerequisite_qid must be an integer (or empty/null)")
            continue

        q = models.Question(
            id=qid_int,
            assessment_version=validated.assessment_version,
            question_text_en=validated.question_text_en,
            question_text_hi=(validated.question_text_hi or "").strip() or None,
            question_text_ta=(validated.question_text_ta or "").strip() or None,
            skill_id=validated.skill_id,
            weight=weight,
            group_id=(row.get("group_id") or "").strip() or None,
            prerequisite_qid=prereq_int,
            question_code=(row.get("question_code") or "").strip() or None,
        )

        db.add(q)
        uploaded += 1

    db.commit()
    logger.info(f"upload-questions: uploaded={uploaded}, skipped={skipped}, errors={len(errors)}")
    return {"uploaded": uploaded, "skipped": skipped, "errors": errors}


# ============================================================
# PR1. UPLOAD ASSOCIATED QUALITIES (AQ_MASTER)
# ============================================================
@router.post(
    "/upload-aqs",
    response_model=UploadResponse,
    summary="Bulk upload Associated Qualities (AQ) via CSV",
)
async def upload_aqs(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    PR1 (versioned) expected CSV headers (exact):
      assessment_version,aq_code,name_en,name_hi,name_ta,status

    Required:
      - assessment_version
      - aq_code
      - name_en

    Writes to:
      - associated_qualities_v (versioned knowledge pack table)

    Upsert behavior:
      - Unique key: (assessment_version, aq_code)
      - If exists => update name/status fields
      - Else insert
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text_csv = (await file.read()).decode("utf-8-sig")
    if not text_csv.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text_csv))

    expected_headers = ["assessment_version", "aq_code", "name_en", "name_hi", "name_ta", "status"]
    actual_headers = reader.fieldnames or []
    if actual_headers != expected_headers:
        raise HTTPException(
            status_code=400,
            detail=f"Header mismatch. Expected exactly {expected_headers} but got {actual_headers}",
        )

    inserted = 0
    updated = 0
    skipped = 0

    for row_num, row in enumerate(reader, start=2):
        assessment_version = (row.get("assessment_version") or "").strip()
        aq_code = (row.get("aq_code") or "").strip()
        name_en = (row.get("name_en") or "").strip()

        name_hi = (row.get("name_hi") or "").strip() or None
        name_ta = (row.get("name_ta") or "").strip() or None
        status = (row.get("status") or "").strip() or "active"

        if not assessment_version or not aq_code or not name_en:
            skipped += 1
            continue

        # Pre-check existence to keep inserted vs updated counts accurate
        exists = db.execute(
            text(
                """
                SELECT 1
                FROM associated_qualities_v
                WHERE assessment_version = :v AND aq_code = :c
                LIMIT 1
                """
            ),
            {"v": assessment_version, "c": aq_code},
        ).first()

        db.execute(
            text(
                """
                INSERT INTO associated_qualities_v
                    (assessment_version, aq_code, name_en, name_hi, name_ta, status)
                VALUES
                    (:assessment_version, :aq_code, :name_en, :name_hi, :name_ta, :status)
                ON CONFLICT (assessment_version, aq_code)
                DO UPDATE SET
                    name_en = EXCLUDED.name_en,
                    name_hi = EXCLUDED.name_hi,
                    name_ta = EXCLUDED.name_ta,
                    status  = EXCLUDED.status,
                    updated_at = NOW()
                """
            ),
            {
                "assessment_version": assessment_version,
                "aq_code": aq_code,
                "name_en": name_en,
                "name_hi": name_hi,
                "name_ta": name_ta,
                "status": status,
            },
        )

        if exists:
            updated += 1
        else:
            inserted += 1

    db.commit()
    logger.info(f"upload-aqs(v): inserted={inserted}, updated={updated}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}

# ============================================================
# PR1. UPLOAD AQ FACETS (AQ_FACET_TAXONOMY) - VERSIONED
# ============================================================

@router.post(
    "/upload-aq-facets",
    response_model=UploadResponse,
    summary="Bulk upload AQ Facets via CSV",
)
async def upload_aq_facets(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    PR1 (versioned) expected CSV headers (exact):
      assessment_version,facet_code,aq_code,name_en,name_hi,name_ta,description_en,description_hi,description_ta,status

    Required:
      - assessment_version
      - facet_code
      - aq_code
      - name_en

    Writes to:
      - aq_facets_v (versioned knowledge pack table)

    FK behavior (version-safe):
      - (assessment_version, aq_code) must exist in associated_qualities_v
        otherwise row is skipped (and not inserted)

    Upsert behavior:
      - Unique key: (assessment_version, facet_code)
      - If exists => update fields
      - Else insert
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text_csv = (await file.read()).decode("utf-8-sig")
    if not text_csv.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text_csv))

    expected_headers = [
        "assessment_version",
        "facet_code",
        "aq_code",
        "name_en",
        "name_hi",
        "name_ta",
        "description_en",
        "description_hi",
        "description_ta",
        "status",
    ]
    actual_headers = reader.fieldnames or []
    if actual_headers != expected_headers:
        raise HTTPException(
            status_code=400,
            detail=f"Header mismatch. Expected exactly {expected_headers} but got {actual_headers}",
        )

    inserted = 0
    updated = 0
    skipped = 0

    for row_num, row in enumerate(reader, start=2):
        assessment_version = (row.get("assessment_version") or "").strip()
        facet_code = (row.get("facet_code") or "").strip()
        aq_code = (row.get("aq_code") or "").strip()
        name_en = (row.get("name_en") or "").strip()

        name_hi = (row.get("name_hi") or "").strip() or None
        name_ta = (row.get("name_ta") or "").strip() or None

        description_en = (row.get("description_en") or "").strip() or None
        description_hi = (row.get("description_hi") or "").strip() or None
        description_ta = (row.get("description_ta") or "").strip() or None

        status = (row.get("status") or "").strip() or "active"

        if not assessment_version or not facet_code or not aq_code or not name_en:
            skipped += 1
            continue

        # FK check (version-safe): AQ must exist in associated_qualities_v for same version
        aq_exists = db.execute(
            text(
                """
                SELECT 1
                FROM associated_qualities_v
                WHERE assessment_version = :v AND aq_code = :aq
                LIMIT 1
                """
            ),
            {"v": assessment_version, "aq": aq_code},
        ).first()

        if not aq_exists:
            skipped += 1
            continue

        # Pre-check existence for accurate inserted vs updated counts
        exists = db.execute(
            text(
                """
                SELECT 1
                FROM aq_facets_v
                WHERE assessment_version = :v AND facet_code = :fc
                LIMIT 1
                """
            ),
            {"v": assessment_version, "fc": facet_code},
        ).first()

        db.execute(
            text(
                """
                INSERT INTO aq_facets_v
                    (assessment_version, facet_code, aq_code, name_en, name_hi, name_ta,
                     description_en, description_hi, description_ta, status)
                VALUES
                    (:assessment_version, :facet_code, :aq_code, :name_en, :name_hi, :name_ta,
                     :description_en, :description_hi, :description_ta, :status)
                ON CONFLICT (assessment_version, facet_code)
                DO UPDATE SET
                    aq_code = EXCLUDED.aq_code,
                    name_en = EXCLUDED.name_en,
                    name_hi = EXCLUDED.name_hi,
                    name_ta = EXCLUDED.name_ta,
                    description_en = EXCLUDED.description_en,
                    description_hi = EXCLUDED.description_hi,
                    description_ta = EXCLUDED.description_ta,
                    status = EXCLUDED.status,
                    updated_at = NOW()
                """
            ),
            {
                "assessment_version": assessment_version,
                "facet_code": facet_code,
                "aq_code": aq_code,
                "name_en": name_en,
                "name_hi": name_hi,
                "name_ta": name_ta,
                "description_en": description_en,
                "description_hi": description_hi,
                "description_ta": description_ta,
                "status": status,
            },
        )

        if exists:
            updated += 1
        else:
            inserted += 1

    db.commit()
    logger.info(f"upload-aq-facets(v): inserted={inserted}, updated={updated}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}


# ============================================================
# PR1. UPLOAD QUESTION ↔ AQ_FACET TAGGING (QUESTION_AQ_FACET_TAGGING)
# ============================================================

@router.post(
    "/upload-question-facet-tags",
    response_model=UploadResponse,
    summary="Bulk upload Question ↔ AQ Facet tags via CSV",
)
async def upload_question_facet_tags(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    Expected CSV headers (exact):
      assessment_version,question_code,facet_id,tag_weight

    Behavior:
    - Upsert-like:
      - If exists, update tag_weight
      - Else insert
    - FK checks:
      - question_code must exist for that assessment_version
      - facet_id must exist
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text = (await file.read()).decode("utf-8-sig")
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))

    expected_fields = {"assessment_version", "question_code", "facet_id", "tag_weight"}
    if set(reader.fieldnames or []) != expected_fields:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns exactly {expected_fields}, but got {reader.fieldnames}",
        )

    inserted = 0
    updated = 0
    skipped = 0

    for row_num, row in enumerate(reader, start=2):
        assessment_version = (row.get("assessment_version") or "").strip()
        question_code = (row.get("question_code") or "").strip()
        facet_id = (row.get("facet_id") or "").strip()
        tag_weight_raw = (row.get("tag_weight") or "").strip()

        if not assessment_version or not question_code or not facet_id or not tag_weight_raw:
            skipped += 1
            continue

        try:
            tag_weight = int(tag_weight_raw)
        except ValueError:
            skipped += 1
            continue

        # FK checks
        q = db.query(Question).filter_by(assessment_version=assessment_version, question_code=question_code).first()
        if not q:
            skipped += 1
            continue

        facet = db.query(AQFacet).filter_by(facet_id=facet_id).first()
        if not facet:
            skipped += 1
            continue

        existing = db.query(QuestionFacetTag).filter_by(
            assessment_version=assessment_version,
            question_code=question_code,
            facet_id=facet_id,
        ).first()

        if existing:
            if existing.tag_weight != tag_weight:
                existing.tag_weight = tag_weight
                updated += 1
            else:
                skipped += 1
            continue

        db.add(
            QuestionFacetTag(
                assessment_version=assessment_version,
                question_code=question_code,
                facet_id=facet_id,
                tag_weight=tag_weight,
            )
        )
        inserted += 1

    db.commit()
    logger.info(f"upload-question-facet-tags: inserted={inserted}, updated={updated}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}
