# app/routers/admin_portal.py
# Admin portal read + update endpoints
# All routes require admin or counsellor role
# READ-HEAVY — minimal writes (update tier/active status only)

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.deps import get_db
from app.auth.auth import require_admin_or_counsellor

router = APIRouter()


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
