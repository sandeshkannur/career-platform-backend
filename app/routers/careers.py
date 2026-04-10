# backend/app/routers/careers.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError
from typing import List

from app import models, schemas, deps
from app.auth.auth import get_current_user


def _enrich_career(career: models.Career) -> dict:
    """Flatten EN career_content fields into a Career response dict."""
    en = next((c for c in career.content if c.lang == "en"), None)
    return {
        "id": career.id,
        "title": career.title,
        "career_code": career.career_code,
        "description": (en.description if en and en.description else career.description),
        "cluster_id": career.cluster_id,
        "keyskills": [{"id": ks.id, "name": ks.name} for ks in career.keyskills],
        # salary / market — live on careers table
        "salary_entry_inr": career.salary_entry_inr,
        "salary_mid_inr": career.salary_mid_inr,
        "salary_peak_inr": career.salary_peak_inr,
        "automation_risk": career.automation_risk,
        "future_outlook": career.future_outlook,
        "recommended_stream": career.recommended_stream,
        # rich content — career_content EN row (None if missing)
        "indian_job_title": en.indian_job_title if en else None,
        "prestige_title": en.prestige_title if en else None,
        "pathway_step1": en.pathway_step1 if en else None,
        "pathway_step2": en.pathway_step2 if en else None,
        "pathway_step3": en.pathway_step3 if en else None,
        "pathway_accessible": en.pathway_accessible if en else None,
        "pathway_premium": en.pathway_premium if en else None,
        "pathway_earn_learn": en.pathway_earn_learn if en else None,
    }

router = APIRouter(
    prefix="/careers",
    tags=["Careers"],
    dependencies=[Depends(get_current_user)],
)

# ➕ Create a new career entry
@router.post(
    "",
    response_model=schemas.Career,
    status_code=status.HTTP_201_CREATED,
)
def create_career(
    career: schemas.CareerCreate,
    db: Session = Depends(deps.get_db),
):
    # Ensure the referenced cluster exists
    cluster = db.query(models.CareerCluster).get(career.cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CareerCluster with provided cluster_id does not exist",
        )
    # Prevent duplicates by title within same cluster
    if db.query(models.Career).filter_by(title=career.title, cluster_id=career.cluster_id).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Career with this title already exists in the cluster",
        )
    db_career = models.Career(
        title=career.title,
        description=career.description,
        cluster_id=career.cluster_id,
    )
    db.add(db_career)
    try:
        db.commit()
        db.refresh(db_career)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create career due to database integrity error",
        )
    return db_career

# 📋 Get all careers (public)
@router.get("", response_model=List[schemas.Career])
def list_careers(db: Session = Depends(deps.get_db)):
    careers = (
        db.query(models.Career)
        .options(
            selectinload(models.Career.content),
            selectinload(models.Career.keyskills),
        )
        .all()
    )
    return [_enrich_career(c) for c in careers]

# 🔍 Get a career by ID (public)
@router.get("/{career_id}", response_model=schemas.Career)
def get_career(
    career_id: int,
    db: Session = Depends(deps.get_db),
):
    career = (
        db.query(models.Career)
        .options(
            selectinload(models.Career.content),
            selectinload(models.Career.keyskills),
        )
        .filter(models.Career.id == career_id)
        .first()
    )
    if not career:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Career not found",
        )
    return _enrich_career(career)

# 🔄 Update a career
@router.put(
    "/{career_id}",
    response_model=schemas.Career,
)
def update_career(
    career_id: int,
    career_data: schemas.CareerCreate,
    db: Session = Depends(deps.get_db),
):
    career = db.get(models.Career, career_id)
    if not career:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Career not found",
        )
    # Ensure the referenced cluster exists
    cluster = db.query(models.CareerCluster).get(career_data.cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CareerCluster with provided cluster_id does not exist",
        )
    # Prevent duplicate titles in cluster
    existing = (
        db.query(models.Career)
        .filter(models.Career.title == career_data.title)
        .filter(models.Career.cluster_id == career_data.cluster_id)
        .filter(models.Career.id != career_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Another career with this title already exists in the cluster",
        )
    career.title = career_data.title
    career.description = career_data.description
    career.cluster_id = career_data.cluster_id
    try:
        db.commit()
        db.refresh(career)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update career due to database integrity error",
        )
    return career

# 🗑️ Delete a career
@router.delete(
    "/{career_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_career(
    career_id: int,
    db: Session = Depends(deps.get_db),
):
    career = db.get(models.Career, career_id)
    if not career:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Career not found",
        )
    db.delete(career)
    db.commit()
    return



