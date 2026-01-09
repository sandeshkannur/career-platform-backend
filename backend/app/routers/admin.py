from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException,
    Form,
)
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError  # ✅ NEW
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
)
from app.schemas import (
    UploadResponse,
    UploadQuestionsResult,
    RoleChange,
    GuardianAssign,
    User as UserSchema,

    # ✅ B3 NEW schemas (you will add these in app/schemas.py)
    AdminQuestionCreateRequest,
    AdminQuestionCreateResponse,
    # ✅ B4 NEW schemas
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
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text = (await file.read()).decode("utf-8-sig")

    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))
    inserted = 0
    skipped = 0

    for row in reader:
        name = (row.get("name") or "").strip()
        if not name:
            skipped += 1
            continue

        if db.query(CareerCluster).filter_by(name=name).first():
            skipped += 1
            continue

        cluster = CareerCluster(
            name=name,
            description=(row.get("description") or "").strip() or None,
        )
        db.add(cluster)
        inserted += 1

    db.commit()
    logger.info(f"upload-career-clusters: inserted={inserted}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}


# ============================================================
# 2. UPLOAD CAREERS (supports cluster_id OR cluster_name)
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
    CSV headers supported:
    - title (required)
    - description (optional)
    - cluster_id (int) OR cluster_name (string)
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text = (await file.read()).decode("utf-8-sig")
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))
    inserted = 0
    skipped = 0

    for row in reader:
        title = (row.get("title") or "").strip()
        if not title:
            skipped += 1
            continue

        if db.query(Career).filter_by(title=title).first():
            skipped += 1
            continue

        # Support cluster_id OR cluster_name
        cluster = None

        cluster_id_raw = (row.get("cluster_id") or "").strip()
        if cluster_id_raw:
            try:
                cid = int(cluster_id_raw)
                cluster = db.query(CareerCluster).get(cid)
            except Exception:
                cluster = None

        if cluster is None:
            cluster_name = (row.get("cluster_name") or "").strip()
            if cluster_name:
                cluster = db.query(CareerCluster).filter_by(name=cluster_name).first()

        if cluster is None:
            skipped += 1
            continue

        career = Career(
            title=title,
            description=(row.get("description") or "").strip() or None,
            cluster_id=cluster.id,
        )
        db.add(career)
        inserted += 1

    db.commit()
    logger.info(f"upload-careers: inserted={inserted}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}


# ============================================================
# 3. UPLOAD KEYSKILLS (supports cluster_id OR cluster_name)
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
    CSV headers supported:
    - name (required)
    - description (optional)
    - cluster_id (int) OR cluster_name (string)
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text = (await file.read()).decode("utf-8-sig")
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))
    inserted = 0
    skipped = 0

    for row in reader:
        name = (row.get("name") or "").strip()
        if not name:
            skipped += 1
            continue

        cluster = None

        cluster_id_raw = (row.get("cluster_id") or "").strip()
        if cluster_id_raw:
            try:
                cid = int(cluster_id_raw)
                cluster = db.query(CareerCluster).get(cid)
            except Exception:
                cluster = None

        if cluster is None:
            cluster_name = (row.get("cluster_name") or "").strip()
            if cluster_name:
                cluster = db.query(CareerCluster).filter_by(name=cluster_name).first()

        if cluster is None:
            skipped += 1
            continue

        ks = KeySkill(
            name=name,
            description=(row.get("description") or "").strip() or None,
            cluster_id=cluster.id,
        )
        db.add(ks)
        inserted += 1

    db.commit()
    logger.info(f"upload-keyskills: inserted={inserted}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}


# ============================================================
# 4. NEW ENDPOINT — UPLOAD CAREER ↔ KEYSKILL MAPPINGS
# ============================================================

@router.post(
    "/upload-career-keyskills",
    response_model=UploadResponse,
    summary="Bulk upload Career ↔ KeySkill mappings via CSV",
)
async def upload_career_keyskills(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    CSV format:
    career_title,skill_name
    Data Scientist,Python
    Mechanical Engineer,CAD
    ...
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text = (await file.read()).decode("utf-8-sig")
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))
    inserted = 0
    skipped = 0
    errors = []

    for i, row in enumerate(reader, start=1):
        career_title = (row.get("career_title") or "").strip()
        keyskill_name = (row.get("skill_name") or "").strip()

        if not career_title or not keyskill_name:
            skipped += 1
            errors.append(f"Row {i}: missing career_title or skill_name")
            continue

        career = db.query(Career).filter_by(title=career_title).first()
        if not career:
            skipped += 1
            errors.append(f"Row {i}: career '{career_title}' not found")
            continue

        keyskill = db.query(KeySkill).filter_by(name=keyskill_name).first()
        if not keyskill:
            skipped += 1
            errors.append(f"Row {i}: keyskill '{keyskill_name}' not found")
            continue

        if keyskill in career.keyskills:
            skipped += 1
            continue

        career.keyskills.append(keyskill)
        inserted += 1

    db.commit()

    if errors:
        print("Errors during upload:")
        for e in errors:
            print(" -", e)

    logger.info(f"upload-career-keyskills: inserted={inserted}, skipped={skipped}")
    return {"status": "success", "inserted": inserted}


# ============================================================
# 4b. NEW ENDPOINT — UPLOAD CAREER ↔ KEYSKILL WEIGHTS
# ============================================================

@router.post(
    "/upload-career-keyskill-weights",
    response_model=UploadResponse,
    summary="Bulk update weight_percentage for Career ↔ KeySkill via CSV",
)
async def upload_career_keyskill_weights(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    CSV format (header required):
        career_id,keyskill_id,weight_percentage

    - Updates weight_percentage column in career_keyskill_association
    - 'inserted' in response = number of rows successfully updated
    """
    if file.content_type != "text/csv":
        raise HTTPException(status_code=400, detail="Only text/csv files are accepted")

    text = (await file.read()).decode("utf-8-sig")
    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))

    expected_fields = {"career_id", "keyskill_id", "weight_percentage"}
    if set(reader.fieldnames or []) != expected_fields:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns exactly {expected_fields}, "
                   f"but got {reader.fieldnames}",
        )

    updated = 0
    missing = 0

    try:
        for row in reader:
            try:
                career_id = int(row["career_id"])
                keyskill_id = int(row["keyskill_id"])
                weight = int(row["weight_percentage"])
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid row {row}: {e}")
                continue

            stmt = (
                career_keyskill_association.update()
                .where(
                    career_keyskill_association.c.career_id == career_id,
                    career_keyskill_association.c.keyskill_id == keyskill_id,
                )
                .values(weight_percentage=weight)
            )

            result = db.execute(stmt)

            if result.rowcount == 0:
                logger.warning(
                    f"No association found for (career_id={career_id}, keyskill_id={keyskill_id})"
                )
                missing += 1
            else:
                updated += result.rowcount

        db.commit()

    except Exception as e:
        db.rollback()
        logger.exception("Error while updating career-keyskill weights")
        raise HTTPException(
            status_code=500,
            detail=f"Error while updating weights, rolled back. Error: {e}",
        )

    logger.info(
        f"upload-career-keyskill-weights: updated={updated}, missing_pairs={missing}"
    )
    return UploadResponse(
        status=f"success (updated={updated}, missing_pairs={missing})",
        inserted=updated,
    )


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
    """

    # Convert payload -> dict to match validator signature
    row_for_validation = payload.dict()

    validated = validate_question_row(db=db, row=row_for_validation, row_index=1)

    # ✅ HTTP-native validation failure (400)
    if isinstance(validated, RowValidationError):
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "error_code": "ROW_VALIDATION_ERROR",
                "errors": [{"field": e.field, "message": e.message} for e in validated.errors],
            },
        )

    # ✅ DB write ONLY after validation succeeds
    # NOTE: validator does not provide question_id; payload owns it.
    q = models.Question(
        id=payload.question_id,  # ✅ FIX: use payload
        assessment_version=validated.assessment_version,
        question_text_en=validated.question_text_en,
        question_text_hi=(validated.question_text_hi or "").strip() or None,
        question_text_ta=(validated.question_text_ta or "").strip() or None,
        skill_id=validated.skill_id,

        # Optional fields supported by your questions table
        weight=payload.weight if payload.weight is not None else 1,
        group_id=(payload.group_id or "").strip() or None,
        prerequisite_qid=(payload.prerequisite_qid or "").strip() or None,
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
                "message": f"Question with id '{payload.question_id}' already exists.",  # ✅ FIX
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
    - Input: JSON array
    - Reuses shared validate_question_row() (B2) per item
    - ❌ No DB writes before validation pass completes
    - Validation errors do NOT stop the batch
    - Duplicate question_id handling: skip + error entry
    """

    created = 0
    skipped = 0
    errors: List[AdminQuestionBulkErrorEntry] = []

    # ---------------------------
    # PASS 0: Detect duplicates inside the payload itself
    # ---------------------------
    seen_ids = set()
    duplicate_indexes = set()

    for i, item in enumerate(payloads):
        qid = (item.question_id or "").strip()
        if qid in seen_ids:
            duplicate_indexes.add(i)
        else:
            seen_ids.add(qid)

    # ---------------------------
    # PASS 1: Validate everything first (NO DB WRITES)
    # ---------------------------
    valid_items: List[Dict] = []   # store minimal validated insert data
    valid_meta: List[Dict] = []    # store index + question_id for error reporting

    for i, item in enumerate(payloads):
        qid = (item.question_id or "").strip()

        # Skip payload-level duplicates (preferred behavior)
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

        # Convert to dict to match B2 validator signature
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

        # Build insert-ready dict (but DO NOT write yet)
        valid_items.append(
            {
                "id": qid,  # DB PK
                "assessment_version": validated.assessment_version,
                "question_text_en": validated.question_text_en,
                "question_text_hi": (validated.question_text_hi or "").strip() or None,
                "question_text_ta": (validated.question_text_ta or "").strip() or None,
                "skill_id": validated.skill_id,
                "weight": item.weight if item.weight is not None else 1,
                "group_id": (item.group_id or "").strip() or None,
                "prerequisite_qid": (item.prerequisite_qid or "").strip() or None,
            }
        )
        valid_meta.append({"index": i, "question_id": qid})

    # ---------------------------
    # PASS 2: Write valid rows (DB writes happen ONLY here)
    # Continue on duplicate conflicts (skip + error entry)
    # ---------------------------
    for meta, row in zip(valid_meta, valid_items):
        qid = meta["question_id"]

        q = models.Question(**row)
        db.add(q)

        try:
            # Flush each row so we can catch duplicates without killing the batch
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

    # Commit final successful inserts
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("bulk_create_questions_api: commit failed")
        raise HTTPException(status_code=500, detail=f"Bulk insert commit failed: {e}")

    return AdminQuestionBulkResponse(
        created=created,
        skipped=skipped,
        errors=errors,
    )
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
    """
    # Basic file checks
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")

    if not text.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    reader = csv.DictReader(io.StringIO(text))

    # Strict header validation: allow exactly one of the two supported sets (in exact order)
    expected_headers_a = [
        "id",
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
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):
        # normalize id field
        qid = (row.get("id") or row.get("question_id") or "").strip()
        if not qid:
            skipped += 1
            errors.append(f"Row {row_num}: missing id/question_id")
            continue

        # duplicates (non-idempotent): skip existing primary key
        if db.query(models.Question).filter_by(id=qid).first():
            skipped += 1
            errors.append(f"Row {row_num}: duplicate question id '{qid}'")
            continue

        # ✅ B2 shared validation: assessment_version presence, required fields,
        # enum correctness (future), defaults, and skill_id existence (DB read)
        row_for_validation = dict(row)
        row_for_validation["assessment_version"] = (assessment_version or "").strip()

        validated = validate_question_row(db=db, row=row_for_validation, row_index=row_num)

        if isinstance(validated, RowValidationError):
            skipped += 1
            # flatten structured errors into your existing string list format
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

        q = models.Question(
            id=qid,
            assessment_version=validated.assessment_version,
            question_text_en=validated.question_text_en,
            question_text_hi=(validated.question_text_hi or "").strip() or None,
            question_text_ta=(validated.question_text_ta or "").strip() or None,
            skill_id=validated.skill_id,
            weight=weight,
            group_id=(row.get("group_id") or "").strip() or None,
            prerequisite_qid=(row.get("prerequisite_qid") or "").strip() or None,
        )

        db.add(q)
        uploaded += 1

    db.commit()
    logger.info(f"upload-questions: uploaded={uploaded}, skipped={skipped}, errors={len(errors)}")
    return {"uploaded": uploaded, "skipped": skipped, "errors": errors}
