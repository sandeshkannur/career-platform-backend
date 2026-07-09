# app/routers/interest_inventory.py
"""
Interest Inventory — Layer 2 of MapYourCareer scoring.

10 forced-choice activity questions → cluster interest signals →
+15% reranking boost applied to matching careers at recommendation time.

Endpoints:
  POST /v1/interest/{student_id}   — submit or update answers
  GET  /v1/interest/{student_id}   — retrieve latest answers + boosts
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator
from typing import Dict, Optional
from datetime import datetime

from app import models
from app.deps import get_db
from app.auth.auth import get_current_active_user
from app.services.counsellor_access import shadow_check_counsellor_access

router = APIRouter(tags=['Interest Inventory'])


# ─── Cluster map — hidden from students, used only server-side ───────────────
# Each question key maps to cluster names that receive a boost
INTEREST_CLUSTER_MAP: Dict[str, list] = {
    # Q1 — Science Exhibition
    'q1_a': ['Manufacturing', 'Architecture', 'STEM'],
    'q1_b': ['Arts & A/V', 'Marketing'],
    'q1_c': ['STEM', 'Education', 'Info Tech'],
    # Q2 — Colony volunteer
    'q2_a': ['Education', 'Human Serv'],
    'q2_b': ['Government', 'Law/Safety'],
    'q2_c': ['Health Sci', 'Human Serv'],
    # Q3 — School club
    'q3_a': ['Info Tech', 'STEM'],
    'q3_b': ['Arts & A/V', 'Marketing'],
    'q3_c': ['Government', 'Law/Safety', 'Business'],
    # Q4 — Free Saturday
    'q4_a': ['Business', 'Agriculture', 'Hospitality'],
    'q4_b': ['Agriculture', 'Architecture', 'Manufacturing'],
    'q4_c': ['Arts & A/V', 'Education', 'Marketing'],
    # Q5 — Career visit
    'q5_a': ['Health Sci', 'Human Serv'],
    'q5_b': ['Government', 'Law/Safety'],
    'q5_c': ['Info Tech', 'STEM', 'Manufacturing'],
    # Q6 — Friend support
    'q6_a': ['Human Serv', 'Health Sci', 'Education'],
    'q6_b': ['STEM', 'Info Tech'],
    'q6_c': ['Hospitality', 'Marketing', 'Arts & A/V'],
    # Q7 — New subject
    'q7_a': ['Agriculture', 'STEM'],
    'q7_b': ['Business', 'Finance', 'Marketing'],
    'q7_c': ['Health Sci', 'STEM'],
    # Q8 — School problem
    'q8_a': ['Manufacturing', 'Architecture', 'STEM', 'Info Tech'],
    'q8_b': ['Government', 'Law/Safety', 'Education'],
    'q8_c': ['Business', 'Human Serv', 'Government'],
    # Q9 — Family visit
    'q9_a': ['Manufacturing', 'Business', 'Transport'],
    'q9_b': ['Education', 'Government', 'Agriculture'],
    'q9_c': ['Hospitality', 'Marketing', 'Arts & A/V'],
    # Q10 — Class 10 project
    'q10_a': ['Info Tech', 'STEM', 'Business'],
    'q10_b': ['Government', 'Law/Safety', 'Education'],
    'q10_c': ['Marketing', 'Arts & A/V', 'Human Serv'],
}

VALID_QUESTIONS = {f'q{i}' for i in range(1, 11)}
VALID_OPTIONS   = {'a', 'b', 'c'}
BOOST_PER_CLUSTER_HIT = 0.15   # 15% boost per question that maps to a cluster
MAX_BOOST_PER_CLUSTER = 0.45   # cap at 45% total boost per cluster (3 hits)
INVENTORY_VERSION = 'v1'


def _compute_cluster_boosts(answers: Dict[str, str]) -> Dict[str, float]:
    """
    Given answers like {"q1": "a", "q2": "c", ...},
    compute how much boost each cluster receives.

    A cluster receiving 1 hit  → +0.15 boost
    A cluster receiving 2 hits → +0.30 boost
    A cluster receiving 3 hits → +0.45 boost (capped)
    """
    hit_counts: Dict[str, int] = {}

    for q_key, option in answers.items():
        map_key = f'{q_key}_{option}'   # e.g. 'q1_a'
        clusters = INTEREST_CLUSTER_MAP.get(map_key, [])
        for cluster in clusters:
            hit_counts[cluster] = hit_counts.get(cluster, 0) + 1

    boosts = {
        cluster: min(count * BOOST_PER_CLUSTER_HIT, MAX_BOOST_PER_CLUSTER)
        for cluster, count in hit_counts.items()
        if count > 0
    }
    return boosts


# ─── Schemas ──────────────────────────────────────────────────────────────────

class InterestSubmitRequest(BaseModel):
    answers: Dict[str, str] = Field(
        ...,
        description='Map of question_id → option. e.g. {"q1": "a", "q3": "b"}',
        example={'q1': 'a', 'q2': 'c', 'q3': 'b', 'q4': 'a', 'q5': 'c',
                 'q6': 'a', 'q7': 'b', 'q8': 'a', 'q9': 'c', 'q10': 'b'},
    )
    lang: str = Field('en', description='Language used: en or kn')

    @validator('answers')
    def validate_answers(cls, v):
        if not v:
            raise ValueError('answers cannot be empty')
        for q, opt in v.items():
            if q not in VALID_QUESTIONS:
                raise ValueError(f'Invalid question key: {q}. Must be q1-q10.')
            if opt not in VALID_OPTIONS:
                raise ValueError(f'Invalid option for {q}: {opt}. Must be a, b, or c.')
        return v

    @validator('lang')
    def validate_lang(cls, v):
        if v not in ('en', 'kn'):
            return 'en'
        return v


class InterestResponse(BaseModel):
    student_id: int
    inventory_version: str
    answers: Dict[str, str]
    cluster_boosts: Optional[Dict[str, float]]
    lang: str
    submitted_at: datetime
    updated_at: datetime
    questions_answered: int
    top_clusters: list

    class Config:
        from_attributes = True


# ─── Helper: ownership check ──────────────────────────────────────────────────

def _assert_student_access(
    student_id: int,
    current_user: models.User,
    db: Session,
) -> models.Student:
    """Students can only access their own data. Admins/counsellors can access all."""
    if current_user.role in ('admin', 'counsellor'):
        student = db.query(models.Student).filter(
            models.Student.id == student_id
        ).first()
        if not student:
            raise HTTPException(status_code=404, detail='Student not found')
        return student

    # Student role — must own this student_id
    student = db.query(models.Student).filter(
        models.Student.user_id == current_user.id,
        models.Student.id == student_id,
    ).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You can only access your own interest inventory',
        )
    return student


# ─── POST /v1/interest/{student_id} ──────────────────────────────────────────

@router.post(
    '/interest/{student_id}',
    response_model=InterestResponse,
    summary='Submit interest inventory answers',
    description=(
        'Submit or update the 10 interest inventory answers for a student. '
        'Cluster boosts are computed server-side and stored. '
        'On retake, the existing record is updated (upsert). '
        'The cluster mapping is never exposed in the response.'
    ),
)
def submit_interest_inventory(
    student_id: int,
    payload: InterestSubmitRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    student = _assert_student_access(student_id, current_user, db)

    # Compute cluster boosts server-side — never trust client
    cluster_boosts = _compute_cluster_boosts(payload.answers)

    # Upsert: update if exists, create if not
    existing = db.query(models.InterestInventoryResponse).filter(
        models.InterestInventoryResponse.student_id == student_id,
        models.InterestInventoryResponse.inventory_version == INVENTORY_VERSION,
    ).first()

    now = datetime.utcnow()

    if existing:
        existing.answers        = payload.answers
        existing.cluster_boosts = cluster_boosts
        existing.lang           = payload.lang
        existing.updated_at     = now
        record = existing
    else:
        record = models.InterestInventoryResponse(
            student_id        = student_id,
            inventory_version = INVENTORY_VERSION,
            answers           = payload.answers,
            cluster_boosts    = cluster_boosts,
            lang              = payload.lang,
            submitted_at      = now,
            updated_at        = now,
        )
        db.add(record)

    db.commit()
    db.refresh(record)

    # Top clusters — sorted by boost descending, top 3
    top_clusters = sorted(
        cluster_boosts.keys(),
        key=lambda c: cluster_boosts[c],
        reverse=True,
    )[:3]

    return InterestResponse(
        student_id         = record.student_id,
        inventory_version  = record.inventory_version,
        answers            = record.answers,
        cluster_boosts     = record.cluster_boosts,
        lang               = record.lang,
        submitted_at       = record.submitted_at,
        updated_at         = record.updated_at,
        questions_answered = len(record.answers),
        top_clusters       = top_clusters,
    )


# ─── GET /v1/interest/{student_id} ───────────────────────────────────────────

@router.get(
    '/interest/{student_id}',
    response_model=InterestResponse,
    summary='Get student interest inventory',
    description=(
        'Retrieve the latest interest inventory submission for a student. '
        'Returns 404 if the student has not completed the interest inventory yet. '
        'Students can only access their own data. Admins and counsellors can access all.'
    ),
)
def get_interest_inventory(
    student_id: int,
    version: str = Query(INVENTORY_VERSION, description='Inventory version: v1'),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _assert_student_access(student_id, current_user, db)

    # Phase-1 counsellor assignment shadow check: log-only, never blocks.
    shadow_check_counsellor_access(
        db, current_user, student_id, "GET /v1/interest/{student_id}"
    )

    record = db.query(models.InterestInventoryResponse).filter(
        models.InterestInventoryResponse.student_id == student_id,
        models.InterestInventoryResponse.inventory_version == version,
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'No interest inventory found for student {student_id} (version {version})',
        )

    cluster_boosts = record.cluster_boosts or {}
    top_clusters = sorted(
        cluster_boosts.keys(),
        key=lambda c: cluster_boosts[c],
        reverse=True,
    )[:3]

    return InterestResponse(
        student_id         = record.student_id,
        inventory_version  = record.inventory_version,
        answers            = record.answers,
        cluster_boosts     = cluster_boosts,
        lang               = record.lang,
        submitted_at       = record.submitted_at,
        updated_at         = record.updated_at,
        questions_answered = len(record.answers),
        top_clusters       = top_clusters,
    )


# ─── GET /v1/interest/{student_id}/boosts (admin/counsellor only) ─────────────

@router.get(
    '/interest/{student_id}/boosts',
    summary='Get cluster boosts only (admin/counsellor)',
    description=(
        'Returns ONLY the cluster boost values for use by the recommendation engine. '
        'Restricted to admin and counsellor roles. '
        'Returns empty dict if student has not completed interest inventory.'
    ),
)
def get_interest_boosts(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    if current_user.role not in ('admin', 'counsellor'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only admins and counsellors can access raw boost data',
        )

    record = db.query(models.InterestInventoryResponse).filter(
        models.InterestInventoryResponse.student_id == student_id,
        models.InterestInventoryResponse.inventory_version == INVENTORY_VERSION,
    ).first()

    return {
        'student_id':     student_id,
        'has_inventory':  record is not None,
        'cluster_boosts': record.cluster_boosts if record else {},
        'top_clusters':   sorted(
            (record.cluster_boosts or {}).keys(),
            key=lambda c: (record.cluster_boosts or {}).get(c, 0),
            reverse=True,
        )[:5] if record else [],
    }
