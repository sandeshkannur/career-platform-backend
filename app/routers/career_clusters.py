from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List

from app import models, schemas, deps
from app.auth.auth import get_current_user

router = APIRouter(tags=["Career Clusters"])

# ➕ Create a new career cluster
@router.post(
    "",
    response_model=schemas.CareerCluster,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user)],
)
def create_career_cluster(
    cluster: schemas.CareerClusterCreate,
    db: Session = Depends(deps.get_db),
):
    if db.query(models.CareerCluster).filter_by(name=cluster.name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cluster already exists",
        )
    db_cluster = models.CareerCluster(
        name=cluster.name,
        description=cluster.description,
    )
    db.add(db_cluster)
    try:
        db.commit()
        db.refresh(db_cluster)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create career cluster due to integrity error",
        )
    return db_cluster

# 📋 PUBLIC: Get all career clusters
@router.get("", response_model=List[schemas.CareerCluster])
def list_career_clusters(db: Session = Depends(deps.get_db)):
    return db.query(models.CareerCluster).all()

# 🔍 PUBLIC: Get a specific cluster by ID
@router.get("/{cluster_id}", response_model=schemas.CareerCluster)
def get_career_cluster(
    cluster_id: int,
    db: Session = Depends(deps.get_db),
):
    cluster = db.query(models.CareerCluster).get(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cluster not found",
        )
    return cluster

# 🔄 Update a career cluster
@router.put(
    "/{cluster_id}",
    response_model=schemas.CareerCluster,
    dependencies=[Depends(get_current_user)],
)
def update_career_cluster(
    cluster_id: int,
    cluster_data: schemas.CareerClusterCreate,
    db: Session = Depends(deps.get_db),
):
    cluster = db.query(models.CareerCluster).get(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cluster not found",
        )
    # Check for name conflict
    existing = (
        db.query(models.CareerCluster)
        .filter(models.CareerCluster.name == cluster_data.name)
        .filter(models.CareerCluster.id != cluster_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Another cluster with this name already exists",
        )
    cluster.name = cluster_data.name
    cluster.description = cluster_data.description
    try:
        db.commit()
        db.refresh(cluster)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update career cluster due to integrity error",
        )
    return cluster

# 🗑️ Delete a cluster
@router.delete(
    "/{cluster_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_user)],
)
def delete_career_cluster(
    cluster_id: int,
    db: Session = Depends(deps.get_db),
):
    cluster = db.query(models.CareerCluster).get(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cluster not found",
        )
    db.delete(cluster)
    db.commit()
    return
