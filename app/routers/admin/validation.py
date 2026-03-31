"""
Admin validation router.
Exposes 4 read-only endpoints under /v1/admin/:
  GET /validate-knowledge-pack
  GET /validate-knowledge-pack.csv
  GET /validate-explainability-keys
  GET /explainability-coverage

Role gate: admin only (inherited from router dependency).
Reads: explainability_content table (via services).
"""
import io
import csv
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.deps import get_db
from app import schemas
from app.models import ExplainabilityContent
from app.schemas import (
    User as UserSchema,
    ValidateExplainabilityKeysResponse,
)
from app.auth.auth import require_role, get_current_active_user
from app.services.knowledge_pack_validation import (
    run_validate_knowledge_pack,
    run_validate_explainability_keys,
)

router = APIRouter(
    tags=["Admin Panel"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get(
    "/validate-knowledge-pack",
    tags=["Admin Panel", "admin"],
)
def validate_knowledge_pack(
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    # Import-safe: keep schemas inside the service to avoid startup failures
    return run_validate_knowledge_pack(db)


@router.get(
    "/validate-knowledge-pack.csv",
    tags=["Admin Panel", "admin"],
)
def validate_knowledge_pack_csv(
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    """
    PR12: Admin productivity
    - Export the validation issues as CSV for remediation workflows.
    - Read-only; does not modify ingestion/scoring.
    """
    report = run_validate_knowledge_pack(db)

    headers = ["severity", "code", "message", "sample_json"]

    def _iter_rows():
        yield ",".join(headers) + "\n"
        for issue in report.issues:
            sev = (issue.severity or "").replace('"', '""')
            code = (issue.code or "").replace('"', '""')
            msg = (issue.message or "").replace('"', '""')
            sample_obj = issue.sample if issue.sample is not None else None
            sample_json = json.dumps(sample_obj, ensure_ascii=False, separators=(",", ":"))
            sample_json = sample_json.replace('"', '""')
            yield f'"{sev}","{code}","{msg}","{sample_json}"\n'

    return StreamingResponse(
        _iter_rows(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=knowledge_pack_validation_issues.csv"},
    )


@router.get(
    "/validate-explainability-keys",
    response_model=ValidateExplainabilityKeysResponse,
    tags=["Admin Panel", "admin"],
    summary="PR39: Validate explainability_key taxonomy + coverage (read-only)",
)
def validate_explainability_keys(
    version: str | None = Query(default=None),
    locale: str | None = Query(default=None),
    required_families: str | None = Query(
        default=None,
        description="Comma-separated family list (default: AQ,FACET,SKILL,CAREER,CLUSTER)",
    ),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    families = None
    if required_families:
        families = [x.strip().upper() for x in required_families.split(",") if x.strip()]

    return run_validate_explainability_keys(
        db=db,
        version=version,
        locale=locale,
        required_families=families,
    )


# ============================================================
# PR41 — Locale Coverage Validation (i18n Gate)
# ============================================================
@router.get(
    "/explainability-coverage",
    response_model=schemas.ExplainabilityCoverageResponse,
    tags=["Admin Panel", "admin"],
    summary="PR41: Coverage report for missing explanation keys per locale/version (baseline en)",
)
def explainability_coverage(
    version: str = Query(..., min_length=1, max_length=32),
    locale: str = Query(..., min_length=1, max_length=20),
    baseline_locale: str = Query("en", min_length=1, max_length=20),
    format: str = Query("json", description="json | csv"),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_active_user),
):
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    baseline_rows = (
        db.execute(
            select(ExplainabilityContent.explanation_key)
            .where(
                ExplainabilityContent.version == version,
                ExplainabilityContent.locale == baseline_locale,
                ExplainabilityContent.is_active == True,  # noqa: E712
            )
        )
        .scalars()
        .all()
    )

    target_rows = (
        db.execute(
            select(ExplainabilityContent.explanation_key)
            .where(
                ExplainabilityContent.version == version,
                ExplainabilityContent.locale == locale,
                ExplainabilityContent.is_active == True,  # noqa: E712
            )
        )
        .scalars()
        .all()
    )

    baseline_keys = set([k.strip() for k in baseline_rows if k])
    target_keys = set([k.strip() for k in target_rows if k])
    missing = sorted(list(baseline_keys - target_keys))

    payload = schemas.ExplainabilityCoverageResponse(
        version=version,
        locale=locale,
        baseline_locale=baseline_locale,
        baseline_active_keys=len(baseline_keys),
        target_active_keys=len(target_keys),
        missing_count=len(missing),
        missing_keys=missing,
    )

    if (format or "").lower() == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["version", "baseline_locale", "target_locale", "missing_explanation_key"])
        for k in missing:
            w.writerow([version, baseline_locale, locale, k])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="explainability_coverage_{version}_{locale}.csv"'
            },
        )

    return payload
