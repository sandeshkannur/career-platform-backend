# app/routers/admin_portal.py
# Admin portal read + update endpoints
# All routes require admin or counsellor role
# READ-HEAVY — minimal writes (update tier/active status only)

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.deps import get_db
from app.auth.auth import require_admin_or_counsellor

# ── Weight-approval spine (Stage 2 + 3) ──────────────────────────────────────
from app.models import WeightChangeRequest
from app.routers.admin.audit_trail import log_audit
from app.schemas.weight_approval import WCRListOut, WCROut, WCRProposalCreate
from app.services.career_vector_service import recompute_all_vectors
from app.services.weight_approval import (
    snapshot_current_weights,
    validate_career_exists,
    validate_proposed_weights,
)

# ── Weight-snapshot spine (Stage 1 + 2) ──────────────────────────────────────
from app.services.weight_snapshots import (
    capture_promote_snapshot,
    capture_snapshot,
    compute_diff,
    read_career_weights,
    read_full_table_weights,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def _safe_int(v):
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Endpoint 1 — Career Clusters list
# GET /v1/admin-portal/career-clusters
# ---------------------------------------------------------------------------

@router.get("/career-clusters")
def list_career_clusters(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    rows = db.execute(text("""
        SELECT
          cc.id,
          cc.name,
          cc.description,
          COUNT(DISTINCT c.id)                                        AS career_count,
          COUNT(DISTINCT c.id) FILTER (WHERE c.is_active = TRUE)     AS active_career_count,
          COUNT(DISTINCT ks.id)                                       AS keyskill_count
        FROM career_clusters cc
        LEFT JOIN careers c   ON c.cluster_id  = cc.id
        LEFT JOIN keyskills ks ON ks.cluster_id = cc.id
        GROUP BY cc.id, cc.name, cc.description
        ORDER BY cc.name
    """)).mappings().all()

    clusters = [
        {
            "id":                  int(r["id"]),
            "name":                r["name"],
            "description":         r["description"],
            "career_count":        _safe_int(r["career_count"]) or 0,
            "active_career_count": _safe_int(r["active_career_count"]) or 0,
            "keyskill_count":      _safe_int(r["keyskill_count"]) or 0,
        }
        for r in rows
    ]
    return {"clusters": clusters, "total": len(clusters)}


# ---------------------------------------------------------------------------
# Endpoint 2 — Careers list with full attributes
# GET /v1/admin-portal/careers
# ---------------------------------------------------------------------------

@router.get("/careers")
def list_careers(
    cluster_id: Optional[int] = Query(None),
    is_active:  Optional[bool] = Query(None),
    tier:       Optional[int]  = Query(None),
    search:     Optional[str]  = Query(None),
    page:       int            = Query(1, ge=1),
    page_size:  int            = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    offset = (page - 1) * page_size
    search_param = f"%{search}%" if search else None

    # Count total matching rows
    count_row = db.execute(text("""
        SELECT COUNT(DISTINCT c.id) AS cnt
        FROM careers c
        WHERE (:cluster_id IS NULL OR c.cluster_id = :cluster_id)
          AND (:is_active  IS NULL OR c.is_active   = :is_active)
          AND (:tier       IS NULL OR c.career_tier  = :tier)
          AND (:search     IS NULL OR LOWER(c.title) LIKE LOWER(:search))
    """), {
        "cluster_id": cluster_id,
        "is_active":  is_active,
        "tier":       tier,
        "search":     search_param,
    }).fetchone()
    total = int(count_row.cnt or 0)

    # Query 1 — main careers list (no joins to aggregation tables)
    rows = db.execute(text("""
        SELECT
          c.id, c.title, c.career_code, c.cluster_id, c.description,
          c.is_active, c.career_tier, c.tier_reason,
          c.deactivated_at, c.deactivated_by,
          c.salary_entry_inr, c.salary_mid_inr, c.salary_peak_inr,
          c.industry_growth_pct, c.automation_risk,
          c.future_outlook, c.recommended_stream,
          cc.name AS cluster_name
        FROM careers c
        LEFT JOIN career_clusters cc ON cc.id = c.cluster_id
        WHERE (:cluster_id IS NULL OR c.cluster_id = :cluster_id)
          AND (:is_active  IS NULL OR c.is_active   = :is_active)
          AND (:tier       IS NULL OR c.career_tier  = :tier)
          AND (:search     IS NULL OR LOWER(c.title) LIKE LOWER(:search))
        ORDER BY cc.name NULLS LAST, c.title
        LIMIT :page_size OFFSET :offset
    """), {
        "cluster_id": cluster_id,
        "is_active":  is_active,
        "tier":       tier,
        "search":     search_param,
        "page_size":  page_size,
        "offset":     offset,
    }).mappings().all()

    career_ids = [int(r["id"]) for r in rows]

    # Query 2 — keyskill counts per career
    keyskill_map: dict = {}
    if career_ids:
        keyskill_rows = db.execute(text("""
            SELECT career_id, COUNT(*) AS keyskill_count
            FROM career_keyskill_association
            WHERE career_id = ANY(:career_ids)
            GROUP BY career_id
        """), {"career_ids": career_ids}).fetchall()
        keyskill_map = {r.career_id: int(r.keyskill_count) for r in keyskill_rows}

    # Query 3 — skill weight stats per career
    weight_map: dict = {}
    if career_ids:
        weight_rows = db.execute(text("""
            SELECT career_id,
                   COUNT(*)                           AS skill_count,
                   ROUND(SUM(weight)::numeric, 2)     AS weight_total
            FROM career_student_skill
            WHERE career_id = ANY(:career_ids)
            GROUP BY career_id
        """), {"career_ids": career_ids}).fetchall()
        weight_map = {
            r.career_id: (int(r.skill_count), float(r.weight_total or 0))
            for r in weight_rows
        }

    # Query 4 — EN content
    content_map: dict = {}
    if career_ids:
        content_rows = db.execute(text("""
            SELECT * FROM career_content
            WHERE career_id = ANY(:career_ids) AND lang = 'en'
        """), {"career_ids": career_ids}).mappings().all()
        content_map = {r["career_id"]: dict(r) for r in content_rows}

    careers = []
    for r in rows:
        cid = int(r["id"])
        content = content_map.get(cid, {})
        skill_count, weight_total = weight_map.get(cid, (0, 0.0))
        careers.append({
            "id":               cid,
            "title":            r["title"],
            "career_code":      r["career_code"],
            "cluster_id":       _safe_int(r["cluster_id"]),
            "cluster_name":     r["cluster_name"],
            "description":      r["description"],
            "is_active":        bool(r["is_active"]) if r["is_active"] is not None else True,
            "career_tier":      _safe_int(r["career_tier"]),
            "tier_reason":      r["tier_reason"],
            "deactivated_at":   r["deactivated_at"].isoformat() if r["deactivated_at"] else None,
            "deactivated_by":     r["deactivated_by"],
            # Salary + market data live on the careers table (language-independent)
            "salary_entry_inr":   _safe_int(r["salary_entry_inr"]),
            "salary_mid_inr":     _safe_int(r["salary_mid_inr"]),
            "salary_peak_inr":    _safe_int(r["salary_peak_inr"]),
            "industry_growth_pct": _safe_int(r["industry_growth_pct"]),
            "automation_risk":    r["automation_risk"],
            "future_outlook":     r["future_outlook"],
            "recommended_stream": r["recommended_stream"],
            "content_en": {
                "prestige_title":     content.get("prestige_title"),
                "indian_job_title":   content.get("indian_job_title"),
                "description":        content.get("description"),
                "domain_category":    content.get("domain_category"),
                "top_tier_potential": content.get("top_tier_potential"),
                "pathway_step1":      content.get("pathway_step1"),
                "pathway_step2":      content.get("pathway_step2"),
                "pathway_step3":      content.get("pathway_step3"),
                "pathway_accessible": content.get("pathway_accessible"),
                "pathway_premium":    content.get("pathway_premium"),
                "pathway_earn_learn": content.get("pathway_earn_learn"),
                "parallel_path":      content.get("parallel_path"),
            } if content else None,
            "keyskill_count":     keyskill_map.get(cid, 0),
            "skill_weight_count": skill_count,
            "skill_weight_total": weight_total,
        })

    import math
    total_pages = math.ceil(total / page_size) if page_size else 1

    return {
        "careers":     careers,
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": total_pages,
    }


# ---------------------------------------------------------------------------
# Endpoint 3 — Single career detail
# GET /v1/admin-portal/careers/{career_id}
# ---------------------------------------------------------------------------

@router.get("/careers/{career_id}")
def get_career_detail(
    career_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    row = db.execute(text("""
        SELECT c.*, cc.name AS cluster_name
        FROM careers c
        LEFT JOIN career_clusters cc ON cc.id = c.cluster_id
        WHERE c.id = :career_id
    """), {"career_id": career_id}).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"Career {career_id} not found")

    # Content (all languages)
    content_rows = db.execute(text("""
        SELECT * FROM career_content
        WHERE career_id = :career_id
        ORDER BY lang
    """), {"career_id": career_id}).mappings().all()
    content_by_lang = {r["lang"]: dict(r) for r in content_rows}

    # Keyskills with weight
    keyskill_rows = db.execute(text("""
        SELECT ks.id, ks.name, ks.description, cka.weight_percentage
        FROM career_keyskill_association cka
        JOIN keyskills ks ON ks.id = cka.keyskill_id
        WHERE cka.career_id = :career_id
        ORDER BY cka.weight_percentage DESC
    """), {"career_id": career_id}).mappings().all()

    # Student skill weights
    skill_rows = db.execute(text("""
        SELECT student_skill, weight
        FROM career_student_skill
        WHERE career_id = :career_id
        ORDER BY weight DESC
    """), {"career_id": career_id}).mappings().all()

    return {
        "id":             int(row["id"]),
        "title":          row["title"],
        "career_code":    row["career_code"],
        "cluster_id":     _safe_int(row["cluster_id"]),
        "cluster_name":   row["cluster_name"],
        "description":    row["description"],
        "is_active":      bool(row["is_active"]) if row["is_active"] is not None else True,
        "career_tier":    _safe_int(row["career_tier"]),
        "tier_reason":    row["tier_reason"],
        "deactivated_at": row["deactivated_at"].isoformat() if row["deactivated_at"] else None,
        "deactivated_by": row["deactivated_by"],
        "content":        content_by_lang,
        "keyskills": [
            {
                "id":                int(r["id"]),
                "name":              r["name"],
                "description":       r["description"],
                "weight_percentage": _safe_int(r["weight_percentage"]),
            }
            for r in keyskill_rows
        ],
        "student_skill_weights": [
            {
                "student_skill": r["student_skill"],
                "weight":        _safe_float(r["weight"]),
            }
            for r in skill_rows
        ],
    }


# ---------------------------------------------------------------------------
# Endpoint 4 — Update career tier / active status
# PATCH /v1/admin-portal/careers/{career_id}/tier
# ---------------------------------------------------------------------------

class CareerTierUpdate(BaseModel):
    is_active:   Optional[bool] = None
    career_tier: Optional[int]  = None
    tier_reason: Optional[str]  = None


@router.patch("/careers/{career_id}/tier")
def update_career_tier(
    career_id: int,
    body: CareerTierUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    # Verify career exists
    exists = db.execute(
        text("SELECT id FROM careers WHERE id = :id"),
        {"id": career_id},
    ).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Career {career_id} not found")

    now = datetime.now(timezone.utc)
    actor = getattr(current_user, "email", None) or getattr(current_user, "username", str(current_user.id))

    # Build SET clauses dynamically for only provided fields
    set_clauses = []
    params: dict = {"career_id": career_id}

    if body.is_active is not None:
        set_clauses.append("is_active = :is_active")
        params["is_active"] = body.is_active
        if not body.is_active:
            set_clauses.append("deactivated_at = :deactivated_at")
            set_clauses.append("deactivated_by = :deactivated_by")
            params["deactivated_at"] = now
            params["deactivated_by"] = actor
        else:
            set_clauses.append("deactivated_at = NULL")
            set_clauses.append("deactivated_by = NULL")

    if body.career_tier is not None:
        set_clauses.append("career_tier = :career_tier")
        params["career_tier"] = body.career_tier

    if body.tier_reason is not None:
        set_clauses.append("tier_reason = :tier_reason")
        params["tier_reason"] = body.tier_reason

    if not set_clauses:
        raise HTTPException(status_code=400, detail="No fields to update")

    db.execute(
        text(f"UPDATE careers SET {', '.join(set_clauses)} WHERE id = :career_id"),
        params,
    )
    db.commit()

    # Return updated career
    return get_career_detail(career_id, db=db, current_user=current_user)


# ---------------------------------------------------------------------------
# Endpoint 5 — Key Skills list
# GET /v1/admin-portal/key-skills
# ---------------------------------------------------------------------------

@router.get("/key-skills")
def list_keyskills(
    cluster_id: Optional[int] = Query(None),
    search:     Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    search_param = f"%{search}%" if search else None

    rows = db.execute(text("""
        SELECT
          ks.id, ks.name, ks.description, ks.cluster_id,
          cc.name                                     AS cluster_name,
          COUNT(DISTINCT cka.career_id)               AS career_count,
          ROUND(AVG(cka.weight_percentage)::numeric, 1) AS weight_percentage_avg
        FROM keyskills ks
        LEFT JOIN career_clusters cc             ON cc.id  = ks.cluster_id
        LEFT JOIN career_keyskill_association cka ON cka.keyskill_id = ks.id
        WHERE (:cluster_id IS NULL OR ks.cluster_id = :cluster_id)
          AND (:search     IS NULL OR LOWER(ks.name) LIKE LOWER(:search))
        GROUP BY ks.id, ks.name, ks.description, ks.cluster_id, cc.name
        ORDER BY cc.name NULLS LAST, ks.name
    """), {"cluster_id": cluster_id, "search": search_param}).mappings().all()

    keyskills = [
        {
            "id":                   int(r["id"]),
            "name":                 r["name"],
            "description":          r["description"],
            "cluster_id":           _safe_int(r["cluster_id"]),
            "cluster_name":         r["cluster_name"],
            "career_count":         _safe_int(r["career_count"]) or 0,
            "weight_percentage_avg": _safe_float(r["weight_percentage_avg"]),
        }
        for r in rows
    ]
    return {"keyskills": keyskills, "total": len(keyskills)}


# ---------------------------------------------------------------------------
# Endpoint 6 — Career ↔ KeySkill mappings
# GET /v1/admin-portal/mappings/career-keyskill
# ---------------------------------------------------------------------------

@router.get("/mappings/career-keyskill")
def list_career_keyskill_mappings(
    career_id:  Optional[int] = Query(None),
    keyskill_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    rows = db.execute(text("""
        SELECT
          cka.career_id,
          c.title       AS career_title,
          cc.name       AS cluster_name,
          cka.keyskill_id,
          ks.name       AS keyskill_name,
          cka.weight_percentage
        FROM career_keyskill_association cka
        JOIN careers c          ON c.id   = cka.career_id
        JOIN keyskills ks       ON ks.id  = cka.keyskill_id
        LEFT JOIN career_clusters cc ON cc.id = c.cluster_id
        WHERE (:career_id   IS NULL OR cka.career_id   = :career_id)
          AND (:keyskill_id IS NULL OR cka.keyskill_id = :keyskill_id)
        ORDER BY cc.name NULLS LAST, c.title, cka.weight_percentage DESC
    """), {"career_id": career_id, "keyskill_id": keyskill_id}).mappings().all()

    mappings = [
        {
            "career_id":         int(r["career_id"]),
            "career_title":      r["career_title"],
            "cluster_name":      r["cluster_name"],
            "keyskill_id":       int(r["keyskill_id"]),
            "keyskill_name":     r["keyskill_name"],
            "weight_percentage": _safe_int(r["weight_percentage"]),
        }
        for r in rows
    ]
    return {"mappings": mappings, "total": len(mappings)}


# ---------------------------------------------------------------------------
# Endpoint 7 — Career student skill weights
# GET /v1/admin-portal/mappings/career-skill-weights
# ---------------------------------------------------------------------------

@router.get("/mappings/career-skill-weights")
def get_career_skill_weights(
    career_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    career_row = db.execute(text(
        "SELECT id, title FROM careers WHERE id = :career_id"
    ), {"career_id": career_id}).fetchone()

    if not career_row:
        raise HTTPException(status_code=404, detail=f"Career {career_id} not found")

    rows = db.execute(text("""
        SELECT student_skill, weight
        FROM career_student_skill
        WHERE career_id = :career_id
        ORDER BY weight DESC
    """), {"career_id": career_id}).mappings().all()

    weights = [
        {
            "student_skill": r["student_skill"],
            "weight":        _safe_float(r["weight"]),
        }
        for r in rows
    ]
    total_weight = sum(w["weight"] for w in weights if w["weight"] is not None)

    return {
        "career_id":    int(career_row.id),
        "career_title": career_row.title,
        "weights":      weights,
        "total_weight": round(total_weight, 2),
        "skill_count":  len(weights),
    }


# ---------------------------------------------------------------------------
# Endpoint 8 — Mapping health summary
# GET /v1/admin-portal/mappings/health
# ---------------------------------------------------------------------------

@router.get("/mappings/health")
def get_mapping_health(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    row = db.execute(text("""
        SELECT
          COUNT(*)                                                        AS total_careers,
          COUNT(*) FILTER (WHERE is_active = TRUE)                        AS active_careers,
          COUNT(*) FILTER (WHERE is_active = FALSE)                       AS inactive_careers,
          COUNT(*) FILTER (WHERE career_tier = 1 AND is_active = TRUE)    AS tier1_active,
          COUNT(*) FILTER (WHERE career_tier = 2 AND is_active = TRUE)    AS tier2_active,
          COUNT(*) FILTER (WHERE career_tier = 3 AND is_active = FALSE)   AS tier3_inactive,
          COUNT(*) FILTER (WHERE career_tier = 4 AND is_active = FALSE)   AS tier4_inactive
        FROM careers
    """)).mappings().first()

    keyskill_row = db.execute(text("""
        SELECT
          COUNT(DISTINCT career_id) AS careers_with_keyskills
        FROM career_keyskill_association
    """)).fetchone()

    skill_weight_row = db.execute(text("""
        SELECT
          COUNT(DISTINCT career_id) AS careers_with_skill_weights
        FROM career_student_skill
        WHERE weight > 0
    """)).fetchone()

    weight_ok_row = db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE ABS(weight_sum - 100) <= 1) AS weight_sum_ok,
          COUNT(*) FILTER (WHERE ABS(weight_sum - 100) >  1) AS weight_sum_wrong
        FROM (
          SELECT career_id, SUM(weight) AS weight_sum
          FROM career_student_skill
          GROUP BY career_id
        ) sub
    """)).mappings().first()

    total_careers = _safe_int(row["total_careers"]) or 0
    careers_with_keyskills = _safe_int(keyskill_row.careers_with_keyskills) or 0

    return {
        "total_careers":              total_careers,
        "active_careers":             _safe_int(row["active_careers"]) or 0,
        "inactive_careers":           _safe_int(row["inactive_careers"]) or 0,
        "careers_with_keyskills":     careers_with_keyskills,
        "careers_without_keyskills":  total_careers - careers_with_keyskills,
        "careers_with_skill_weights": _safe_int(skill_weight_row.careers_with_skill_weights) or 0,
        "careers_weight_sum_ok":      _safe_int(weight_ok_row["weight_sum_ok"]) or 0,
        "careers_weight_sum_wrong":   _safe_int(weight_ok_row["weight_sum_wrong"]) or 0,
        "tier_breakdown": {
            "tier1_active":   _safe_int(row["tier1_active"]) or 0,
            "tier2_active":   _safe_int(row["tier2_active"]) or 0,
            "tier3_inactive": _safe_int(row["tier3_inactive"]) or 0,
            "tier4_inactive": _safe_int(row["tier4_inactive"]) or 0,
        },
    }


# ---------------------------------------------------------------------------
# Endpoint 1 (CRUD) — POST /v1/admin-portal/career-clusters
# ---------------------------------------------------------------------------

@router.post("/career-clusters")
def create_cluster(
    body: dict,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    existing = db.execute(text(
        "SELECT id FROM career_clusters WHERE LOWER(name) = LOWER(:name)"
    ), {"name": name}).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail=f"Cluster '{name}' already exists")
    result = db.execute(text("""
        INSERT INTO career_clusters (name, description)
        VALUES (:name, :desc) RETURNING id, name, description
    """), {"name": name, "desc": (body.get("description") or "").strip()})
    db.commit()
    row = result.fetchone()
    return {"id": row.id, "name": row.name, "description": row.description, "created": True}


# ---------------------------------------------------------------------------
# Endpoint 2 (CRUD) — POST /v1/admin-portal/careers
# ---------------------------------------------------------------------------

@router.post("/careers")
def create_career(
    body: dict,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    title = (body.get("title") or "").strip()
    career_code = (body.get("career_code") or "").strip().upper()
    cluster_id = body.get("cluster_id") or None
    career_tier = int(body.get("career_tier") or 1)
    description = (body.get("description") or "").strip()

    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    if not career_code:
        raise HTTPException(status_code=422, detail="career_code is required")
    if career_tier not in [1, 2, 3, 4]:
        raise HTTPException(status_code=422, detail="career_tier must be 1-4")

    dup = db.execute(text(
        "SELECT id FROM careers WHERE career_code = :code"
    ), {"code": career_code}).fetchone()
    if dup:
        raise HTTPException(status_code=409, detail=f"career_code '{career_code}' already exists")

    result = db.execute(text("""
        INSERT INTO careers (title, description, career_code, cluster_id, is_active, career_tier)
        VALUES (:title, :desc, :code, :cluster_id, TRUE, :tier)
        RETURNING id, title, career_code, cluster_id, is_active, career_tier
    """), {"title": title, "desc": description, "code": career_code,
           "cluster_id": cluster_id, "tier": career_tier})
    db.commit()
    row = result.fetchone()

    cluster_name = None
    if row.cluster_id:
        cc = db.execute(text("SELECT name FROM career_clusters WHERE id = :id"),
                        {"id": row.cluster_id}).fetchone()
        cluster_name = cc.name if cc else None

    return {
        "id": row.id, "title": row.title, "career_code": row.career_code,
        "cluster_id": row.cluster_id, "cluster_name": cluster_name,
        "is_active": row.is_active, "career_tier": row.career_tier, "created": True,
        "next_steps": "Use Bulk Upload to add career_content (salary, pathways) and skill weights",
    }


# ---------------------------------------------------------------------------
# Endpoint 3 (CRUD) — POST /v1/admin-portal/key-skills
# ---------------------------------------------------------------------------

@router.post("/key-skills")
def create_keyskill(
    body: dict,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    dup = db.execute(text(
        "SELECT id FROM keyskills WHERE LOWER(name) = LOWER(:name)"
    ), {"name": name}).fetchone()
    if dup:
        raise HTTPException(status_code=409, detail=f"Key skill '{name}' already exists")

    result = db.execute(text("""
        INSERT INTO keyskills (name, description, cluster_id)
        VALUES (:name, :desc, :cluster_id) RETURNING id, name, description, cluster_id
    """), {"name": name, "desc": (body.get("description") or None),
           "cluster_id": body.get("cluster_id") or None})
    db.commit()
    row = result.fetchone()
    return {"id": row.id, "name": row.name, "description": row.description,
            "cluster_id": row.cluster_id, "created": True}


# ---------------------------------------------------------------------------
# Endpoint 4 (CRUD) — POST /v1/admin-portal/mappings/career-keyskill
# ---------------------------------------------------------------------------

@router.post("/mappings/career-keyskill")
def create_mapping(
    body: dict,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    career_id = body.get("career_id")
    keyskill_id = body.get("keyskill_id")
    weight = int(body.get("weight_percentage") or 0)

    if not career_id:
        raise HTTPException(status_code=422, detail="career_id is required")
    if not keyskill_id:
        raise HTTPException(status_code=422, detail="keyskill_id is required")
    if not (0 <= weight <= 100):
        raise HTTPException(status_code=422, detail="weight_percentage must be 0-100")

    career = db.execute(text("SELECT title FROM careers WHERE id = :id"),
                        {"id": career_id}).fetchone()
    if not career:
        raise HTTPException(status_code=404, detail=f"Career ID {career_id} not found")
    ks = db.execute(text("SELECT name FROM keyskills WHERE id = :id"),
                    {"id": keyskill_id}).fetchone()
    if not ks:
        raise HTTPException(status_code=404, detail=f"Key skill ID {keyskill_id} not found")

    db.execute(text("""
        INSERT INTO career_keyskill_association (career_id, keyskill_id, weight_percentage)
        VALUES (:cid, :kid, :w)
        ON CONFLICT (career_id, keyskill_id) DO UPDATE SET weight_percentage = :w
    """), {"cid": career_id, "kid": keyskill_id, "w": weight})
    db.commit()

    return {"career_id": career_id, "career_title": career.title,
            "keyskill_id": keyskill_id, "keyskill_name": ks.name,
            "weight_percentage": weight, "created": True}


# ---------------------------------------------------------------------------
# Endpoint 5 — GET /v1/admin-portal/student-skills
# ---------------------------------------------------------------------------

@router.get("/student-skills")
def get_student_skills(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """
    Returns all 24 canonical student skills.
    engine_key (skills.name) is READ ONLY — never change it.
    student_skill_name is the display label — editable.
    """
    rows = db.execute(text("""
        SELECT
            sk.id,
            sk.name AS engine_key,
            sk.student_skill_name,
            COUNT(DISTINCT CASE WHEN css.weight > 0 THEN css.career_id END) AS careers_using,
            ROUND(COALESCE(AVG(CASE WHEN css.weight > 0 THEN css.weight END), 0)::numeric, 2)
                AS avg_career_weight,
            COUNT(DISTINCT asw.aq_code) AS aq_count,
            STRING_AGG(DISTINCT asw.aq_code, ', ' ORDER BY asw.aq_code) AS feeding_aqs
        FROM skills sk
        LEFT JOIN career_student_skill css ON css.student_skill = sk.name
        LEFT JOIN aq_student_skill_weight asw ON asw.student_skill = sk.student_skill_name
        GROUP BY sk.id, sk.name, sk.student_skill_name
        ORDER BY sk.name
    """)).fetchall()

    skills = [
        {
            "id":                 r.id,
            "engine_key":         r.engine_key,
            "student_skill_name": r.student_skill_name,
            "careers_using":      r.careers_using or 0,
            "avg_career_weight":  float(r.avg_career_weight or 0),
            "aq_count":           r.aq_count or 0,
            "feeding_aqs":        r.feeding_aqs or "None",
            "is_orphan":          (r.aq_count or 0) == 0,
        }
        for r in rows
    ]

    return {
        "skills":        skills,
        "total":         len(skills),
        "orphan_count":  sum(1 for s in skills if s["is_orphan"]),
        "active_count":  sum(1 for s in skills if not s["is_orphan"]),
    }


# ---------------------------------------------------------------------------
# Endpoint 6 — PATCH /v1/admin-portal/student-skills/{skill_id}
# ---------------------------------------------------------------------------

@router.patch("/student-skills/{skill_id}")
def update_student_skill_label(
    skill_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """Update student_skill_name only. skills.name is NEVER changed."""
    student_skill_name = (body.get("student_skill_name") or "").strip()
    if not student_skill_name:
        raise HTTPException(status_code=422, detail="student_skill_name is required")

    existing = db.execute(text(
        "SELECT id, name FROM skills WHERE id = :id"
    ), {"id": skill_id}).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail=f"Skill ID {skill_id} not found")

    db.execute(text(
        "UPDATE skills SET student_skill_name = :sn WHERE id = :id"
    ), {"sn": student_skill_name, "id": skill_id})
    db.commit()

    return {
        "id":                 skill_id,
        "engine_key":         existing.name,
        "student_skill_name": student_skill_name,
        "updated":            True,
        "note":               "engine_key (skills.name) was NOT changed — it is immutable",
    }


# ---------------------------------------------------------------------------
# Endpoint 7 — GET /v1/admin-portal/student-skills/{skill_id}/careers
# ---------------------------------------------------------------------------

@router.get("/student-skills/{skill_id}/careers")
def get_skill_careers(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """Returns all careers that use this student skill with their weights."""
    skill = db.execute(text(
        "SELECT name, student_skill_name FROM skills WHERE id = :id"
    ), {"id": skill_id}).fetchone()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    rows = db.execute(text("""
        SELECT c.id, c.title, cc.name AS cluster, css.weight, c.is_active
        FROM career_student_skill css
        JOIN careers c ON c.id = css.career_id
        LEFT JOIN career_clusters cc ON cc.id = c.cluster_id
        WHERE css.student_skill = :skill_name AND css.weight > 0
        ORDER BY css.weight DESC, c.title
    """), {"skill_name": skill.name}).fetchall()

    return {
        "skill_id":           skill_id,
        "engine_key":         skill.name,
        "student_skill_name": skill.student_skill_name,
        "careers": [
            {
                "id":        r.id,
                "title":     r.title,
                "cluster":   r.cluster,
                "weight":    float(r.weight),
                "is_active": r.is_active,
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ---------------------------------------------------------------------------
# Weight-approval spine — Stage 2
# Endpoints write ONLY to weight_change_requests.
# career_keyskill_association is read once (baseline snapshot) and never written.
# ---------------------------------------------------------------------------

def _wcr_to_dict(wcr: WeightChangeRequest) -> dict:
    """Serialise a WeightChangeRequest ORM row to a plain dict for JSON responses."""
    return {
        "id":                 wcr.id,
        "title":              wcr.title,
        "status":             wcr.status,
        "scope":              wcr.scope,
        "changes":            wcr.changes,
        "created_by":         wcr.created_by,
        "created_at":         wcr.created_at.isoformat() if wcr.created_at else None,
        "submitted_at":       wcr.submitted_at.isoformat() if wcr.submitted_at else None,
        "reviewed_by":        wcr.reviewed_by,
        "reviewed_at":        wcr.reviewed_at.isoformat() if wcr.reviewed_at else None,
        "review_level":       wcr.review_level,
        "decision_comment":   wcr.decision_comment,
        "promoted_at":        wcr.promoted_at.isoformat() if wcr.promoted_at else None,
        "vectors_recomputed": wcr.vectors_recomputed,
    }


# ---------------------------------------------------------------------------
# Endpoint W1 — Create draft weight-change proposal for one career
# POST /v1/admin-portal/careers/{career_id}/keyskill-weights/proposals
#
# Route ordering — no collision with existing routes:
#   GET /careers/{career_id}         matches a SINGLE path segment after /careers/
#   PATCH /careers/{career_id}/tier  sub-path already in use with no issues
#   This route adds a new sub-path /keyskill-weights/proposals under the same
#   career path prefix.  Different HTTP method (POST) and longer path ensure
#   FastAPI never confuses it with the GET /careers/{career_id} handler.
# ---------------------------------------------------------------------------

@router.post("/careers/{career_id}/keyskill-weights/proposals")
def create_weight_proposal(
    career_id: int,
    body: WCRProposalCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    # 1. Verify career exists
    career = validate_career_exists(career_id, db)
    if not career:
        raise HTTPException(status_code=404, detail=f"Career {career_id} not found")

    # 2. Convert Pydantic items to plain dicts for the service layer
    proposed = [
        {"keyskill_id": w.keyskill_id, "weight_percentage": w.weight_percentage}
        for w in body.proposed_weights
    ]

    # 3. Validate proposed weights (sum=100, min keyskills, concentration cap, FK check)
    errors = validate_proposed_weights(proposed, db)
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"ok": False, "errors": errors},
        )

    # 4. Snapshot current live weights as baseline (READ-ONLY on career_keyskill_association)
    baseline = snapshot_current_weights(career_id, db)

    # 5. Build the changes JSONB array (one entry per career for single-scope proposals)
    changes = [
        {
            "career_id":        career_id,
            "baseline_weights": baseline,
            "proposed_weights": proposed,
        }
    ]

    # 6. Persist the draft WeightChangeRequest
    wcr = WeightChangeRequest(
        title=body.title,
        status="draft",
        scope="single",
        changes=changes,
        created_by=current_user.id,
    )
    db.add(wcr)
    db.flush()  # populate wcr.id before the audit log references it

    # 7. Audit log — fires inside the same transaction; committed below
    log_audit(
        db,
        action="create",
        entity_type="weight_change_request",
        entity_id=wcr.id,
        entity_name=body.title or f"Career {career_id} weight proposal",
        user_id=current_user.id,
        user_email=current_user.email,
        details={
            "career_id":    career_id,
            "career_title": career["title"],
            "scope":        "single",
        },
    )

    db.commit()
    db.refresh(wcr)

    return _wcr_to_dict(wcr)


# ---------------------------------------------------------------------------
# Endpoint W2 — List weight-change proposals for one career
# GET /v1/admin-portal/careers/{career_id}/keyskill-weights/proposals
# ---------------------------------------------------------------------------

@router.get("/careers/{career_id}/keyskill-weights/proposals")
def list_career_weight_proposals(
    career_id: int,
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    career = validate_career_exists(career_id, db)
    if not career:
        raise HTTPException(status_code=404, detail=f"Career {career_id} not found")

    # JSONB containment filter: changes must include an object with this career_id.
    # Equivalent to: WHERE changes @> '[{"career_id": <id>}]'
    filter_json = json.dumps([{"career_id": career_id}])

    params: dict = {"filter": filter_json}
    status_clause = ""
    if status:
        status_clause = "AND status = :status"
        params["status"] = status

    rows = db.execute(
        text(f"""
            SELECT id, title, status, scope, changes,
                   created_by, created_at, submitted_at,
                   reviewed_by, reviewed_at, review_level,
                   decision_comment, promoted_at, vectors_recomputed
            FROM weight_change_requests
            WHERE changes @> CAST(:filter AS jsonb)
            {status_clause}
            ORDER BY created_at DESC
        """),
        params,
    ).mappings().all()

    items = [dict(r) for r in rows]
    # Serialise datetimes to ISO strings to match _wcr_to_dict style
    for item in items:
        for ts_field in ("created_at", "submitted_at", "reviewed_at", "promoted_at"):
            v = item.get(ts_field)
            if v is not None and hasattr(v, "isoformat"):
                item[ts_field] = v.isoformat()

    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Endpoint W3 — Get a single weight-change request by ID
# GET /v1/admin-portal/weight-change-requests/{request_id}
# ---------------------------------------------------------------------------

@router.get("/weight-change-requests/{request_id}")
def get_weight_change_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    wcr = db.query(WeightChangeRequest).filter(
        WeightChangeRequest.id == request_id
    ).first()
    if not wcr:
        raise HTTPException(
            status_code=404,
            detail=f"Weight change request {request_id} not found",
        )
    return _wcr_to_dict(wcr)


# ---------------------------------------------------------------------------
# Endpoint W4 — Submit a draft proposal for review (draft → pending_review)
# POST /v1/admin-portal/weight-change-requests/{request_id}/submit
# ---------------------------------------------------------------------------

@router.post("/weight-change-requests/{request_id}/submit")
def submit_weight_change_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    wcr = db.query(WeightChangeRequest).filter(
        WeightChangeRequest.id == request_id
    ).first()
    if not wcr:
        raise HTTPException(
            status_code=404,
            detail=f"Weight change request {request_id} not found",
        )

    # Enforce state machine: only draft → pending_review is allowed here
    if wcr.status != "draft":
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error_code": "INVALID_STATUS_TRANSITION",
                "message": (
                    f"Cannot submit a request with status '{wcr.status}'. "
                    "Only 'draft' requests may be submitted."
                ),
            },
        )

    wcr.status = "pending_review"
    wcr.submitted_at = datetime.now(timezone.utc)

    log_audit(
        db,
        action="update",
        entity_type="weight_change_request",
        entity_id=wcr.id,
        entity_name=wcr.title or f"Request {wcr.id}",
        user_id=current_user.id,
        user_email=current_user.email,
        details={"previous_status": "draft", "new_status": "pending_review"},
    )

    db.commit()
    db.refresh(wcr)

    return _wcr_to_dict(wcr)


# ---------------------------------------------------------------------------
# Weight-approval spine — Stage 3
# Review (approve/reject) and promote endpoints.
# Promote is the FIRST stage that writes to career_keyskill_association.
# ---------------------------------------------------------------------------

class _ReviewDecision(BaseModel):
    decision_comment: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoint W5 — List all weight-change requests (review queue feed)
# GET /v1/admin-portal/weight-change-requests
# ---------------------------------------------------------------------------

@router.get("/weight-change-requests")
def list_weight_change_requests(
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    params: dict = {}
    where_clause = ""
    if status:
        where_clause = "WHERE status = :status"
        params["status"] = status

    rows = db.execute(
        text(f"""
            SELECT id, title, status, scope, changes,
                   created_by, created_at, submitted_at,
                   reviewed_by, reviewed_at, review_level,
                   decision_comment, promoted_at, vectors_recomputed
            FROM weight_change_requests
            {where_clause}
            ORDER BY created_at DESC
        """),
        params,
    ).mappings().all()

    items = [dict(r) for r in rows]
    for item in items:
        for ts_field in ("created_at", "submitted_at", "reviewed_at", "promoted_at"):
            v = item.get(ts_field)
            if v is not None and hasattr(v, "isoformat"):
                item[ts_field] = v.isoformat()

    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Endpoint W6 — Approve a pending-review request (pending_review → approved)
# POST /v1/admin-portal/weight-change-requests/{request_id}/approve
# ---------------------------------------------------------------------------

@router.post("/weight-change-requests/{request_id}/approve")
def approve_weight_change_request(
    request_id: int,
    body: _ReviewDecision,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    wcr = db.query(WeightChangeRequest).filter(
        WeightChangeRequest.id == request_id
    ).first()
    if not wcr:
        raise HTTPException(
            status_code=404,
            detail=f"Weight change request {request_id} not found",
        )

    if wcr.status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail={
                "ok": False,
                "error_code": "INVALID_STATUS_TRANSITION",
                "message": (
                    f"Cannot approve a request with status '{wcr.status}'. "
                    "Only 'pending_review' requests may be approved."
                ),
            },
        )

    wcr.status = "approved"
    wcr.reviewed_by = current_user.id
    wcr.reviewed_at = datetime.now(timezone.utc)
    wcr.decision_comment = body.decision_comment

    log_audit(
        db,
        action="approve",
        entity_type="weight_change_request",
        entity_id=wcr.id,
        entity_name=wcr.title or f"Request {wcr.id}",
        user_id=current_user.id,
        user_email=current_user.email,
        details={"previous_status": "pending_review", "new_status": "approved"},
    )

    db.commit()
    db.refresh(wcr)

    return _wcr_to_dict(wcr)


# ---------------------------------------------------------------------------
# Endpoint W7 — Reject a pending-review request (pending_review → rejected)
# POST /v1/admin-portal/weight-change-requests/{request_id}/reject
# ---------------------------------------------------------------------------

@router.post("/weight-change-requests/{request_id}/reject")
def reject_weight_change_request(
    request_id: int,
    body: _ReviewDecision,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    wcr = db.query(WeightChangeRequest).filter(
        WeightChangeRequest.id == request_id
    ).first()
    if not wcr:
        raise HTTPException(
            status_code=404,
            detail=f"Weight change request {request_id} not found",
        )

    if wcr.status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail={
                "ok": False,
                "error_code": "INVALID_STATUS_TRANSITION",
                "message": (
                    f"Cannot reject a request with status '{wcr.status}'. "
                    "Only 'pending_review' requests may be rejected."
                ),
            },
        )

    wcr.status = "rejected"
    wcr.reviewed_by = current_user.id
    wcr.reviewed_at = datetime.now(timezone.utc)
    wcr.decision_comment = body.decision_comment

    log_audit(
        db,
        action="reject",
        entity_type="weight_change_request",
        entity_id=wcr.id,
        entity_name=wcr.title or f"Request {wcr.id}",
        user_id=current_user.id,
        user_email=current_user.email,
        details={"previous_status": "pending_review", "new_status": "rejected"},
    )

    db.commit()
    db.refresh(wcr)

    return _wcr_to_dict(wcr)


# ---------------------------------------------------------------------------
# Endpoint W8 — Promote an approved request to live weights
# POST /v1/admin-portal/weight-change-requests/{request_id}/promote
#
# This is the FIRST endpoint in the spine that writes to
# career_keyskill_association.  The write is committed BEFORE vector recompute
# so a recompute failure can never roll back the weight promotion.
# ---------------------------------------------------------------------------

_PROMOTE_UPSERT_SQL = text("""
    INSERT INTO career_keyskill_association (career_id, keyskill_id, weight_percentage)
    VALUES (:career_id, :keyskill_id, :weight_percentage)
    ON CONFLICT (career_id, keyskill_id)
    DO UPDATE SET weight_percentage = EXCLUDED.weight_percentage
""")

_PROMOTE_DELETE_SQL = text("""
    DELETE FROM career_keyskill_association
    WHERE career_id = :cid AND keyskill_id != ALL(:proposed_ids)
""")


@router.post("/weight-change-requests/{request_id}/promote")
def promote_weight_change_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    wcr = db.query(WeightChangeRequest).filter(
        WeightChangeRequest.id == request_id
    ).first()
    if not wcr:
        raise HTTPException(
            status_code=404,
            detail=f"Weight change request {request_id} not found",
        )

    # State guard: only approved → promoted
    if wcr.status != "approved":
        raise HTTPException(
            status_code=409,
            detail={
                "ok": False,
                "error_code": "INVALID_STATUS_TRANSITION",
                "message": (
                    f"Cannot promote a request with status '{wcr.status}'. "
                    "Only 'approved' requests may be promoted."
                ),
            },
        )

    changes = wcr.changes  # [{career_id, proposed_weights, baseline_weights}, ...]

    # PASS 1: Re-validate ALL career entries — any failure aborts with 422, zero writes.
    validation_errors: dict = {}
    for entry in changes:
        career_id = entry["career_id"]
        proposed = entry["proposed_weights"]
        errors = validate_proposed_weights(proposed, db)
        if errors:
            validation_errors[str(career_id)] = errors

    if validation_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "ok": False,
                "error_code": "REVALIDATION_FAILED",
                "message": (
                    "Proposed weights failed re-validation at promote time. "
                    "No changes written."
                ),
                "validation_errors": validation_errors,
            },
        )

    # PASS 2: SME-staleness warnings (non-blocking — collected, never abort).
    sme_warnings: list = []
    for entry in changes:
        career_id = entry["career_id"]
        proposed_ids_set = {item["keyskill_id"] for item in entry["proposed_weights"]}

        live_rows = db.execute(
            text(
                "SELECT DISTINCT keyskill_id FROM career_keyskill_association "
                "WHERE career_id = :cid"
            ),
            {"cid": career_id},
        ).fetchall()
        live_ids = {r[0] for r in live_rows}

        removed_ids = sorted(live_ids - proposed_ids_set)
        if removed_ids:
            sme_rows = db.execute(
                text(
                    "SELECT DISTINCT keyskill_id FROM sme_keyskill_ratings "
                    "WHERE career_id = :cid AND keyskill_id = ANY(:removed_ids)"
                ),
                {"cid": career_id, "removed_ids": removed_ids},
            ).fetchall()
            rated_removed = sorted(r[0] for r in sme_rows)
            if rated_removed:
                sme_warnings.append({
                    "career_id": career_id,
                    "removed_keyskill_ids_with_sme_ratings": rated_removed,
                })

    # THE WRITE — single transaction: upserts + deletes + WCR status + audit.
    promoted_career_ids: list = []
    for entry in changes:
        career_id = entry["career_id"]
        proposed = entry["proposed_weights"]
        proposed_ids = [item["keyskill_id"] for item in proposed]

        for item in proposed:
            db.execute(
                _PROMOTE_UPSERT_SQL,
                {
                    "career_id":         career_id,
                    "keyskill_id":       item["keyskill_id"],
                    "weight_percentage": item["weight_percentage"],
                },
            )

        # Full replace: remove live pairs not present in proposed.
        if proposed_ids:
            db.execute(
                _PROMOTE_DELETE_SQL,
                {"cid": career_id, "proposed_ids": proposed_ids},
            )

        promoted_career_ids.append(career_id)

    wcr.status = "promoted"
    wcr.promoted_at = datetime.now(timezone.utc)
    wcr.vectors_recomputed = False

    log_audit(
        db,
        action="promote",
        entity_type="weight_change_request",
        entity_id=wcr.id,
        entity_name=wcr.title or f"Request {wcr.id}",
        user_id=current_user.id,
        user_email=current_user.email,
        details={
            "career_ids":   promoted_career_ids,
            "sme_warnings": sme_warnings,
        },
    )

    # Weights are now DURABLE — recompute failure cannot roll this back.
    db.commit()

    # THEN: auto-capture pre-promote snapshot (after commit, non-fatal on failure).
    # Isolated try/except — must not affect the recompute block below.
    try:
        capture_promote_snapshot(db, wcr, created_by=current_user.id)
    except Exception as exc:
        logger.warning(
            "Snapshot capture failed after promote (request_id=%s): %s",
            request_id,
            exc,
        )

    # THEN: vector recompute (after commit, non-fatal on failure).
    vectors_recomputed = False
    try:
        recompute_all_vectors(db)   # issues its own db.commit() internally
        wcr.vectors_recomputed = True
        db.commit()
        vectors_recomputed = True
    except Exception as exc:
        logger.warning(
            "Vector recompute failed after promote (request_id=%s): %s. "
            "Weights are committed. Retry via POST /v1/admin/careers/recompute-vectors.",
            request_id,
            exc,
        )

    return {
        "ok":               True,
        "status":           "promoted",
        "request_id":       request_id,
        "careers_promoted": promoted_career_ids,
        "vectors_recomputed": vectors_recomputed,
        "sme_warnings":     sme_warnings,
        "recompute_note": (
            ""
            if vectors_recomputed
            else (
                "Vector recompute failed or is pending. "
                "Retry via POST /v1/admin/careers/recompute-vectors."
            )
        ),
    }


# ---------------------------------------------------------------------------
# Weight-snapshot spine — Stage 1
# Capture endpoints (manual). Restore is Stage 3.
# ---------------------------------------------------------------------------

class _SnapshotCreate(BaseModel):
    scope_type: str           # 'full' | 'career'
    career_id:  Optional[int] = None
    alias:      Optional[str] = None
    reason:     Optional[str] = None


@router.post("/weight-snapshots")
def create_weight_snapshot(
    body: _SnapshotCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """
    POST /v1/admin-portal/weight-snapshots

    Capture a manual named snapshot of career_keyskill_association.
    source is always 'manual' for this endpoint.

    scope_type='full'   — snapshots the entire CKA table.
    scope_type='career' — snapshots one career; career_id required.

    Returns: snapshot metadata + row count. Does NOT return the full JSONB
    payload (potentially large); retrieve it via GET /weight-snapshots/{id}.
    """
    if body.scope_type not in ("full", "career"):
        raise HTTPException(
            status_code=422,
            detail="scope_type must be 'full' or 'career'",
        )

    scope_ref: Optional[int] = None

    if body.scope_type == "career":
        if body.career_id is None:
            raise HTTPException(
                status_code=422,
                detail="career_id is required when scope_type='career'",
            )
        career = validate_career_exists(body.career_id, db)
        if not career:
            raise HTTPException(
                status_code=404,
                detail=f"Career {body.career_id} not found",
            )
        scope_ref      = body.career_id
        snapshot_rows  = read_career_weights(db, body.career_id)
    else:
        snapshot_rows  = read_full_table_weights(db)

    snap = capture_snapshot(
        db,
        scope_type    = body.scope_type,
        scope_ref     = scope_ref,
        source        = "manual",
        snapshot_rows = snapshot_rows,
        created_by    = current_user.id,
        alias         = body.alias,
        reason        = body.reason,
    )
    db.flush()  # populate snap.id before audit log

    log_audit(
        db,
        action      = "create",
        entity_type = "weight_snapshot",
        entity_id   = snap.id,
        entity_name = snap.name,
        user_id     = current_user.id,
        user_email  = current_user.email,
        details     = {
            "scope_type": body.scope_type,
            "scope_ref":  scope_ref,
            "row_count":  len(snapshot_rows),
        },
    )

    db.commit()
    db.refresh(snap)

    return {
        "id":         snap.id,
        "name":       snap.name,
        "alias":      snap.alias,
        "scope_type": snap.scope_type,
        "scope_ref":  snap.scope_ref,
        "source":     snap.source,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
        "row_count":  len(snapshot_rows),
    }


# ---------------------------------------------------------------------------
# Weight-snapshot spine — Stage 2
# Read-only: list, get-one, diff. Writes NOTHING.
# ---------------------------------------------------------------------------

@router.get("/weight-snapshots")
def list_weight_snapshots(
    scope_type: Optional[str] = Query(None, description="Filter by scope_type ('full'|'career')"),
    source:     Optional[str] = Query(None, description="Filter by source ('manual'|'auto_promote'|'pre_restore')"),
    career_id:  Optional[int] = Query(None, description="Filter by scope_ref (career_id)"),
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """
    GET /v1/admin-portal/weight-snapshots

    List snapshots newest first. Returns light metadata only — the full
    snapshot JSONB is NOT included (use GET /weight-snapshots/{id} for that).
    row_count is derived from the stored JSONB length without fetching the array.
    """
    params: dict = {}
    clauses: list[str] = []

    if scope_type:
        clauses.append("scope_type = :scope_type")
        params["scope_type"] = scope_type
    if source:
        clauses.append("source = :source")
        params["source"] = source
    if career_id is not None:
        clauses.append("scope_ref = :career_id")
        params["career_id"] = career_id

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = db.execute(
        text(f"""
            SELECT id, name, alias, scope_type, scope_ref, source, wcr_id,
                   created_by, created_at,
                   jsonb_array_length(snapshot) AS row_count
            FROM weight_snapshots
            {where}
            ORDER BY created_at DESC
        """),
        params,
    ).mappings().all()

    items = []
    for r in rows:
        item = dict(r)
        if item.get("created_at") is not None and hasattr(item["created_at"], "isoformat"):
            item["created_at"] = item["created_at"].isoformat()
        items.append(item)

    return {"items": items, "total": len(items)}


@router.get("/weight-snapshots/{snapshot_id}")
def get_weight_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """
    GET /v1/admin-portal/weight-snapshots/{snapshot_id}

    Full snapshot detail including the stored JSONB weight array.
    """
    from app.models import WeightSnapshot as _WS

    snap = db.query(_WS).filter(_WS.id == snapshot_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

    return {
        "id":         snap.id,
        "name":       snap.name,
        "alias":      snap.alias,
        "reason":     snap.reason,
        "scope_type": snap.scope_type,
        "scope_ref":  snap.scope_ref,
        "source":     snap.source,
        "wcr_id":     snap.wcr_id,
        "created_by": snap.created_by,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
        "snapshot":   snap.snapshot,
        "row_count":  len(snap.snapshot) if snap.snapshot else 0,
    }


@router.get("/weight-snapshots/{snapshot_id}/diff")
def diff_weight_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin_or_counsellor),
):
    """
    GET /v1/admin-portal/weight-snapshots/{snapshot_id}/diff

    Compare this snapshot against CURRENT live career_keyskill_association.

    Diff direction — restore semantics (B22.3 must read this the same way):
      change='removed'   → keyskill in snapshot, missing from live;
                           restoring would ADD it back to live.
      change='added'     → keyskill in live, missing from snapshot;
                           restoring would REMOVE it from live.
      change='changed'   → weights differ; restoring would UPDATE live.
      change='unchanged' → weights agree; restore leaves it untouched.

    For scope='career' snapshots, only that career's live weights are fetched.
    For scope='full' snapshots, the full CKA table is fetched.
    Writes nothing to any table.
    """
    from app.models import WeightSnapshot as _WS

    snap = db.query(_WS).filter(_WS.id == snapshot_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

    snapshot_rows: list = snap.snapshot or []

    if snap.scope_type == "career" and snap.scope_ref is not None:
        live_rows = read_career_weights(db, snap.scope_ref)
    else:
        live_rows = read_full_table_weights(db)

    diff = compute_diff(snapshot_rows, live_rows)

    return {
        "snapshot_id":   snap.id,
        "snapshot_name": snap.name,
        "scope_type":    snap.scope_type,
        "scope_ref":     snap.scope_ref,
        **diff,
    }
