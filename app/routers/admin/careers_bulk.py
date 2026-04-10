"""
Admin bulk-import endpoint for careers.
Auth: inherited from the admin package router (require_role("admin")).

POST /v1/admin/careers/bulk-import?dry_run=true|false

CSV columns (title + career_code required, all others optional):
  title, career_code, cluster_name, description, recommended_stream,
  salary_entry_inr, salary_mid_inr, salary_peak_inr,
  automation_risk, future_outlook, indian_job_title, prestige_title

Fields routed to careers table:
  title, career_code, cluster_id (resolved), recommended_stream,
  salary_entry_inr, salary_mid_inr, salary_peak_inr,
  automation_risk, future_outlook

Fields routed to career_content (lang="en"):
  description, indian_job_title, prestige_title
"""
import csv
import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app import models

router = APIRouter()

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------
_VALID_AUTOMATION_RISK = {"low", "medium", "high"}
_VALID_FUTURE_OUTLOOK  = {"growing", "stable", "declining"}

_INT_FIELDS = ("salary_entry_inr", "salary_mid_inr", "salary_peak_inr")

# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class BulkImportError(BaseModel):
    row: int
    field: str
    message: str


class DryRunResult(BaseModel):
    dry_run: bool = True
    valid_rows: int
    error_rows: int
    errors: List[BulkImportError]


class ImportResult(BaseModel):
    dry_run: bool = False
    inserted: int
    updated: int
    errors: List[BulkImportError]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _validate_row(
    row: Dict[str, str],
    line_no: int,
    cluster_map: Dict[str, int],
) -> tuple[list, Optional[dict]]:
    """
    Validates a single CSV row.
    Returns (errors, parsed) where parsed is None if there are errors,
    otherwise a dict ready for DB writes.
    """
    errors: List[BulkImportError] = []

    title       = row.get("title", "").strip()
    career_code = row.get("career_code", "").strip()

    if not title:
        errors.append(BulkImportError(row=line_no, field="title", message="title is required"))
    if not career_code:
        errors.append(BulkImportError(row=line_no, field="career_code", message="career_code is required"))

    if errors:
        return errors, None

    parsed: Dict[str, Any] = {
        "title": title,
        "career_code": career_code,
        # careers table fields
        "cluster_id": None,
        "recommended_stream": row.get("recommended_stream", "").strip() or None,
        "salary_entry_inr": None,
        "salary_mid_inr": None,
        "salary_peak_inr": None,
        "automation_risk": None,
        "future_outlook": None,
        # career_content fields
        "description": row.get("description", "").strip() or None,
        "indian_job_title": row.get("indian_job_title", "").strip() or None,
        "prestige_title": row.get("prestige_title", "").strip() or None,
    }

    # cluster_name → cluster_id
    cluster_name_raw = row.get("cluster_name", "").strip()
    if cluster_name_raw:
        cid = cluster_map.get(cluster_name_raw.lower())
        if cid is None:
            errors.append(BulkImportError(
                row=line_no,
                field="cluster_name",
                message=f"No matching cluster for {cluster_name_raw!r} (case-insensitive)",
            ))
        else:
            parsed["cluster_id"] = cid

    # salary integer fields
    for field in _INT_FIELDS:
        raw = row.get(field, "").strip()
        if raw:
            val = _parse_int(raw)
            if val is None:
                errors.append(BulkImportError(
                    row=line_no,
                    field=field,
                    message=f"{field} must be an integer, got {raw!r}",
                ))
            else:
                parsed[field] = val

    # automation_risk
    ar = row.get("automation_risk", "").strip().lower()
    if ar:
        if ar not in _VALID_AUTOMATION_RISK:
            errors.append(BulkImportError(
                row=line_no,
                field="automation_risk",
                message=f"automation_risk must be one of {sorted(_VALID_AUTOMATION_RISK)}, got {ar!r}",
            ))
        else:
            parsed["automation_risk"] = ar

    # future_outlook
    fo = row.get("future_outlook", "").strip().lower()
    if fo:
        if fo not in _VALID_FUTURE_OUTLOOK:
            errors.append(BulkImportError(
                row=line_no,
                field="future_outlook",
                message=f"future_outlook must be one of {sorted(_VALID_FUTURE_OUTLOOK)}, got {fo!r}",
            ))
        else:
            parsed["future_outlook"] = fo

    if errors:
        return errors, None

    return [], parsed


def _upsert_career(db: Session, parsed: dict) -> str:
    """
    Upsert one career row. Returns "inserted" or "updated".
    Also upserts career_content (lang='en') for content fields.
    """
    career_code = parsed["career_code"]
    existing = db.query(models.Career).filter_by(career_code=career_code).first()

    # Fields that live on careers table
    careers_fields = (
        "title", "cluster_id", "recommended_stream",
        "salary_entry_inr", "salary_mid_inr", "salary_peak_inr",
        "automation_risk", "future_outlook",
    )

    if existing:
        for field in careers_fields:
            val = parsed.get(field)
            if val is not None:
                setattr(existing, field, val)
        db.flush()
        career_id = existing.id
        action = "updated"
    else:
        career = models.Career(
            title=parsed["title"],
            career_code=career_code,
            cluster_id=parsed.get("cluster_id"),
            recommended_stream=parsed.get("recommended_stream"),
            salary_entry_inr=parsed.get("salary_entry_inr"),
            salary_mid_inr=parsed.get("salary_mid_inr"),
            salary_peak_inr=parsed.get("salary_peak_inr"),
            automation_risk=parsed.get("automation_risk"),
            future_outlook=parsed.get("future_outlook"),
        )
        db.add(career)
        db.flush()  # get career.id
        career_id = career.id
        action = "inserted"

    # Upsert career_content (lang="en") for content-layer fields
    content_fields = ("description", "indian_job_title", "prestige_title")
    content_vals = {f: parsed.get(f) for f in content_fields if parsed.get(f) is not None}

    if content_vals:
        existing_content = (
            db.query(models.CareerContent)
            .filter_by(career_id=career_id, lang="en")
            .first()
        )
        if existing_content:
            for field, val in content_vals.items():
                setattr(existing_content, field, val)
        else:
            db.add(models.CareerContent(career_id=career_id, lang="en", **content_vals))

    return action


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/careers/bulk-import",
    summary="Bulk import careers from CSV (admin)",
)
async def bulk_import_careers(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="If true, validate only — no DB writes"),
    db: Session = Depends(get_db),
):
    """
    Upload a CSV of careers. Use dry_run=true to validate before committing.

    Required columns: title, career_code
    Optional columns: cluster_name, description, recommended_stream,
                      salary_entry_inr, salary_mid_inr, salary_peak_inr,
                      automation_risk, future_outlook, indian_job_title, prestige_title
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    # Pre-load all clusters into a lowercased lookup map (one query)
    cluster_rows = db.query(models.CareerCluster.id, models.CareerCluster.name).all()
    cluster_map: Dict[str, int] = {r.name.lower(): r.id for r in cluster_rows}

    all_errors: List[BulkImportError] = []
    valid_parsed: List[dict] = []

    for line_no, row in enumerate(reader, start=2):
        row_errors, parsed = _validate_row(row, line_no, cluster_map)
        if row_errors:
            all_errors.extend(row_errors)
        else:
            valid_parsed.append(parsed)

    if dry_run:
        return DryRunResult(
            valid_rows=len(valid_parsed),
            error_rows=len({e.row for e in all_errors}),
            errors=all_errors,
        )

    # --- Live write ---
    inserted = updated = 0
    write_errors: List[BulkImportError] = list(all_errors)  # carry validation errors through

    for parsed in valid_parsed:
        try:
            action = _upsert_career(db, parsed)
            if action == "inserted":
                inserted += 1
            else:
                updated += 1
        except Exception as exc:
            write_errors.append(BulkImportError(
                row=0,
                field="career_code",
                message=f"DB error for {parsed['career_code']!r}: {exc}",
            ))

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        write_errors.append(BulkImportError(row=0, field="commit", message=str(exc)))
        inserted = updated = 0

    return ImportResult(inserted=inserted, updated=updated, errors=write_errors)
