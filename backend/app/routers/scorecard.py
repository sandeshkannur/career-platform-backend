# backend/app/routers/scorecard.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import text
import re

from app import deps, models, schemas
from app.auth.auth import (
    get_current_active_user,
    require_admin,
    require_admin_or_counsellor,
)


from app.services.scoring import (
    compute_career_scores,
    compute_cluster_scores,
    get_student_keyskill_scores,
)
from app.services.explanations import build_full_explanation
from app.services.tier_mapping import tier_to_score
from app.services.evidence import compute_assessment_evidence


router = APIRouter(
    prefix="/analytics/scorecard",
    tags=["Scorecard"],
)
def _compute_scorecard_payload(student_id: int, db: Session) -> dict:
    
    """
    PR15: Compute RAW scorecard payload (includes numeric fields).
    This must preserve current output shape for admin/counsellor use.
    """
    # --- Compute scores ---
    sk_normalized = get_student_keyskill_scores(db, student_id)
    sk_numeric = {ks_id: round(val * 100, 2) for ks_id, val in (sk_normalized or {}).items()}

    career_scores = compute_career_scores(db, student_id)
    cluster_scores = compute_cluster_scores(db, career_scores)

    # --- Evidence (PR5) + PR6 explainability blocks ---
    latest_assessment_id = db.execute(
        text("""
            SELECT a.id
            FROM students s
            JOIN assessments a
              ON a.user_id = s.user_id
            JOIN assessment_responses ar
              ON ar.assessment_id = a.id
            WHERE s.id = :student_id
              AND s.user_id IS NOT NULL
            ORDER BY a.id DESC
            LIMIT 1
        """),
        {"student_id": student_id},
    ).scalar()

    evidence = None
    if latest_assessment_id is not None:
        evidence = compute_assessment_evidence(db, int(latest_assessment_id))

    pr6_blocks = build_pr6_explainability_blocks(evidence)

    # --- Explanation objects (clusters/careers) ---
    explanation_data = build_full_explanation(db, student_id)

    # --- Keyskill output (full numeric) ---
    keyskills_db = db.query(models.KeySkill).all()
    keyskills_out = []
    for ks in keyskills_db:
        if not sk_normalized or ks.id not in sk_normalized:
            continue

        raw_score = sk_numeric.get(ks.id, 0.0)
        norm = round(sk_normalized.get(ks.id, 0.0), 3)
        tier = reverse_tier(raw_score)

        keyskills_out.append(
            {
                "keyskill_id": ks.id,
                "name": ks.name,
                "score": raw_score,
                "normalized": norm,
                "tier": tier,
                "cluster_id": ks.cluster_id,
                "cluster_name": ks.cluster.name if ks.cluster else None,
            }
        )

    return {
        "student_id": student_id,
        "clusters": explanation_data.get("clusters", []),
        "careers": explanation_data.get("careers", []),
        "keyskills": keyskills_out,
        "cluster_scores": cluster_scores,
        "career_scores": career_scores,
        "evidence": evidence,
        "top_facets": pr6_blocks["top_facets"],
        "top_aqs": pr6_blocks["top_aqs"],
        "facet_evidence_blocks": pr6_blocks["facet_evidence_blocks"],
        "message": None if sk_normalized else "No key skills mapped for this student.",
    }
def _assert_student_owns_student_id(db: Session, current_user: models.User, student_id: int) -> None:
    """
    PR15: Ownership enforcement.
    A student may only access their own student_id via students.user_id linkage.
    """
    student_row = (
        db.query(models.Student)
        .filter(models.Student.user_id == current_user.id)
        .first()
    )

    if not student_row or student_row.id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation forbidden",
        )

def _sanitize_scorecard_payload(payload: dict) -> dict:
    """
    PR15: Remove numeric fields for student-safe scorecard view.
    Must NOT leak scores/weights/counts.
    """
    out = dict(payload)

    def _strip_numbers(text_value: str | None) -> str | None:
        """
        PR15: students must not see numbers anywhere (including inside explanation text).
        Removes patterns like '35.0%', '(58.33%)', '72.0', etc.
        """
        if not text_value:
            return text_value

        # Remove percentage patterns like 35.0% or 58% or 58.33%
        cleaned = re.sub(r"\d+(\.\d+)?\s*%", "", text_value)

        # Remove standalone numbers (e.g., 72.0, 41.67) that might remain
        cleaned = re.sub(r"\b\d+(\.\d+)?\b", "", cleaned)
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        # Tidy extra spaces created by removals
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

        return cleaned

    # Remove top-level numeric aggregates
    out.pop("cluster_scores", None)
    out.pop("career_scores", None)

    # Keyskills: remove numeric fields
    keyskills = out.get("keyskills") or []
    sanitized_keyskills = []
    for ks in keyskills:
        if not isinstance(ks, dict):
            continue
        sanitized_keyskills.append(
            {
                "keyskill_id": ks.get("keyskill_id"),
                "name": ks.get("name"),
                "tier": ks.get("tier"),
                "cluster_id": ks.get("cluster_id"),
                "cluster_name": ks.get("cluster_name"),
            }
        )
    out["keyskills"] = sanitized_keyskills

    # Clusters: remove numeric fields (score, band_breakdown) and keep only safe fields
    clusters = out.get("clusters") or []
    sanitized_clusters = []
    for c in clusters:
        if not isinstance(c, dict):
            # If explanation objects come through, fallback to string-safe conversion
            continue

        sanitized_clusters.append(
            {
                "cluster_id": c.get("cluster_id"),
                "cluster_name": c.get("cluster_name"),
                "top_keyskills": c.get("top_keyskills") or [],
                "explanation": _strip_numbers(c.get("explanation")),
            }
        )
    out["clusters"] = sanitized_clusters

    # Careers: remove numeric fields (score) and keep only safe fields
    careers = out.get("careers") or []
    sanitized_careers = []
    for cr in careers:
        if not isinstance(cr, dict):
            continue

        sanitized_careers.append(
            {
                "career_id": cr.get("career_id"),
                "career_name": cr.get("career_name"),
                "top_keyskills": cr.get("top_keyskills") or [],
                "explanation": _strip_numbers(cr.get("explanation")),
            }
        )
    out["careers"] = sanitized_careers

    # Evidence: remove any count-like fields defensively
    evidence = out.get("evidence")
    if isinstance(evidence, dict):
        for item in (evidence.get("facet_evidence") or []):
            if isinstance(item, dict):
                item.pop("evidence_count", None)
        for item in (evidence.get("aq_evidence_summary") or []):
            if isinstance(item, dict):
                item.pop("evidence_count", None)
    out["evidence"] = evidence

    # PR6 blocks: strip numeric vars if present
    for block_key in ["top_facets", "top_aqs", "facet_evidence_blocks"]:
        blocks = out.get(block_key) or []
        for b in blocks:
            if isinstance(b, dict) and isinstance(b.get("vars"), dict):
                b["vars"].pop("score", None)
                b["vars"].pop("weight", None)

    return out

def reverse_tier(score: float) -> str:
    """
    Convert numeric 0–100 score back into your tier labels.
    """
    if score >= 90:
        return "Very High"
    if score >= 75:
        return "High"
    if score >= 55:
        return "Medium"
    if score >= 35:
        return "Low"
    return "Very Low"

def build_pr6_explainability_blocks(evidence: dict | None) -> dict:
    """
    PR6: Build student-safe explainability blocks (no numeric fields)
    from PR5 evidence (which includes counts). We treat evidence as dict
    because compute_assessment_evidence returns a dict.
    """
    if not evidence:
        return {
            "top_facets": [],
            "top_aqs": [],
            "facet_evidence_blocks": [],
        }

    facet_evidence = evidence.get("facet_evidence") or []
    aq_evidence_summary = evidence.get("aq_evidence_summary") or []

    # 1) Top facets: reuse PR5 facet_evidence ordering (already meaningful)
    top_facets = []
    for item in facet_evidence[:3]:
        top_facets.append(
            schemas.ScorecardFacetExplainBlock(
                facet_code=item.get("facet_code"),
                facet_name_en=item.get("facet_name_en"),
                aq_code=item.get("aq_code"),
                aq_name_en=item.get("aq_name_en"),
                question_codes=item.get("question_codes") or [],
                explanation_key=f"facet.{item.get('facet_code')}.summary",
            )
        )

    # 2) Top AQs: reuse PR5 aq_evidence_summary ordering
    top_aqs = []
    for aq_item in aq_evidence_summary[:3]:
        top_aqs.append(
            schemas.ScorecardAQExplainBlock(
                aq_code=aq_item.get("aq_code"),
                aq_name_en=aq_item.get("aq_name_en"),
                facet_codes=aq_item.get("facet_codes") or [],
                question_codes=aq_item.get("question_codes") or [],
                explanation_key=f"aq.{aq_item.get('aq_code')}.summary",
            )
        )

    # 3) Facet evidence blocks (traceability only)
    facet_evidence_blocks = []
    for item in facet_evidence[:3]:
        facet_evidence_blocks.append(
            schemas.ScorecardFacetEvidenceBlock(
                facet_code=item.get("facet_code"),
                evidence_question_codes=item.get("question_codes") or [],
            )
        )

    return {
        "top_facets": top_facets,
        "top_aqs": top_aqs,
        "facet_evidence_blocks": facet_evidence_blocks,
    }
@router.get("/admin/{student_id}", dependencies=[Depends(require_admin_or_counsellor)])
def get_scorecard_admin(
    student_id: int,
    db: Session = Depends(deps.get_db),
):
    """
    PR15: Admin/editor full scorecard view (numeric fields allowed).
    """
    return _compute_scorecard_payload(student_id=student_id, db=db)

@router.get("/{student_id}")
def get_scorecard(
    student_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    # PR15 governance: students see a student-safe payload and must own the student_id
    if current_user.role == "student":
        _assert_student_owns_student_id(db, current_user, student_id)
        raw_payload = _compute_scorecard_payload(student_id=student_id, db=db)
        return _sanitize_scorecard_payload(raw_payload)

    # PR5: Evidence computed-on-read from the latest assessment that has responses.
    # Authoritative linkage: students.user_id -> assessments.user_id -> assessment_responses.assessment_id
    latest_assessment_id = db.execute(
        text("""
            SELECT a.id
            FROM students s
            JOIN assessments a
              ON a.user_id = s.user_id
            JOIN assessment_responses ar
              ON ar.assessment_id = a.id
            WHERE s.id = :student_id
              AND s.user_id IS NOT NULL
            ORDER BY a.id DESC
            LIMIT 1
        """),
        {"student_id": student_id},
    ).scalar()

    evidence = None
    if latest_assessment_id is not None:
        evidence = compute_assessment_evidence(db, int(latest_assessment_id))
    blocks = build_pr6_explainability_blocks(evidence)

    # keyskill numeric scores (0–1.0), normalized
    sk_normalized = get_student_keyskill_scores(db, student_id)

    if not sk_normalized:
        return schemas.ScorecardResponse(
            student_id=student_id,
            clusters=[],
            careers=[],
            keyskills=[],
            cluster_scores={},
            career_scores={},
            evidence=evidence,
            top_facets=blocks["top_facets"],
            top_aqs=blocks["top_aqs"],
            facet_evidence_blocks=blocks["facet_evidence_blocks"],
            message="No key skills mapped for this student."
        )

    # Convert normalized → numeric (0–100)
    sk_numeric = {ks_id: round(val * 100, 2) for ks_id, val in sk_normalized.items()}

    # Career + Cluster scoring
    career_scores = compute_career_scores(db, student_id)
    cluster_scores = compute_cluster_scores(db, career_scores)

    # Explanations (clusters + careers)
    explanation_data = build_full_explanation(db, student_id)

    # Prepare keyskill breakdown
    keyskills_db = db.query(models.KeySkill).all()
    ks_output = []

    for ks in keyskills_db:
        if ks.id not in sk_normalized:
            continue

        raw_score = sk_numeric[ks.id]
        norm = round(sk_normalized[ks.id], 3)
        tier = reverse_tier(raw_score)

        ks_output.append(schemas.KeySkillScore(
            keyskill_id=ks.id,
            name=ks.name,
            score=raw_score,
            normalized=norm,
            tier=tier,
            cluster_id=ks.cluster_id,
            cluster_name=ks.cluster.name if ks.cluster else None
        ))

    # Build final response
    return schemas.ScorecardResponse(
        student_id=student_id,
        clusters=explanation_data["clusters"],
        careers=explanation_data["careers"],
        keyskills=ks_output,
        cluster_scores=cluster_scores,
        career_scores=career_scores,
        evidence=evidence,
        top_facets=blocks["top_facets"],
        top_aqs=blocks["top_aqs"],
        facet_evidence_blocks=blocks["facet_evidence_blocks"],
        message=None,
    )

