from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta

from .. import models, schemas
from ..database import get_db
from ..models import Farm, Field, User
from ..schemas import FarmCreate, Farm as FarmSchema, FieldCreate, Field as FieldSchema
from .auth import get_current_user

router = APIRouter()

@router.post("/farms", response_model=FarmSchema)
def create_farm(
    farm: FarmCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_farm = Farm(**farm.model_dump(), user_id=current_user.id)
    db.add(db_farm)
    db.commit()
    db.refresh(db_farm)
    return db_farm

@router.get("/farms", response_model=List[FarmSchema])
def get_farms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    farms = db.query(Farm).filter(Farm.user_id == current_user.id).all()
    return farms

@router.get("/farms/{farm_id}", response_model=FarmSchema)
def get_farm(
    farm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    farm = db.query(Farm).filter(
        Farm.id == farm_id,
        Farm.user_id == current_user.id
    ).first()
    
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    return farm

@router.post("/fields", response_model=FieldSchema)
def create_field(
    field: FieldCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check if farm belongs to user
    farm = db.query(Farm).filter(
        Farm.id == field.farm_id,
        Farm.user_id == current_user.id
    ).first()
    
    if not farm:        
        raise HTTPException(status_code=404, detail="Farm not found")
    
    payload = field.model_dump()

    # Idempotency guard: if the same field submission is sent twice, return existing.
    if payload.get("client_id"):
        existing_by_client_id = db.query(Field).filter(
            Field.owner_id == current_user.id,
            Field.client_id == payload["client_id"],
            Field.is_deleted == False
        ).first()
        if existing_by_client_id:
            return existing_by_client_id

    duplicate_window_start = datetime.utcnow() - timedelta(seconds=15)
    existing_recent = db.query(Field).filter(
        Field.owner_id == current_user.id,
        Field.farm_id == payload["farm_id"],
        Field.name == payload["name"],
        Field.crop_type == payload["crop_type"],
        Field.crop_variety == payload.get("crop_variety"),
        Field.area_hectares == payload["area_hectares"],
        Field.is_deleted == False,
        Field.created_at >= duplicate_window_start
    ).first()
    if existing_recent:
        return existing_recent

    db_field = Field(**payload, owner_id=current_user.id)
    db.add(db_field)
    db.commit()
    db.refresh(db_field)
    return db_field


@router.get("/fields", response_model=List[FieldSchema])
def get_fields(
    farm_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Field).filter(
        Field.owner_id == current_user.id,
        Field.is_deleted == False
    )

    if farm_id is not None:
        query = query.filter(Field.farm_id == farm_id)

    return query.order_by(Field.created_at.desc()).all()


@router.get("/fields/{field_id}", response_model=FieldSchema)
def get_field(
    field_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.owner_id == current_user.id,
        Field.is_deleted == False
    ).first()

    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    return field


@router.get("/farms/{farm_id}/fields", response_model=List[FieldSchema])
def get_farm_fields(
    farm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check if farm belongs to user
    farm = db.query(Farm).filter(
        Farm.id == farm_id,
        Farm.user_id == current_user.id
    ).first()
    
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    
    fields = db.query(Field).filter(Field.farm_id == farm_id).all()
    return fields

@router.put("/farms/{farm_id}", response_model=schemas.Farm)
def update_farm(farm_id: int, updated_farm: schemas.FarmCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    query = db.query(models.Farm).filter(models.Farm.id == farm_id, models.Farm.user_id == current_user.id)
    if not query.first():
        raise HTTPException(status_code=404, detail="Farm not found")
    query.update(updated_farm.model_dump(), synchronize_session=False)
    db.commit()
    return query.first()

@router.delete("/farms/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_farm(farm_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    query = db.query(models.Farm).filter(models.Farm.id == farm_id, models.Farm.user_id == current_user.id)
    if not query.first():
        raise HTTPException(status_code=404, detail="Farm not found")
    query.delete(synchronize_session=False)
    db.commit()

@router.delete("/fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_field(
    field_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.Field).filter(
        models.Field.id == field_id,
        models.Field.owner_id == current_user.id
    )
    if not query.first():
        raise HTTPException(status_code=404, detail="Field not found")
    query.delete(synchronize_session=False)
    db.commit()
