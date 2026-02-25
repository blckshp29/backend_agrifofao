from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

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
    
    db_field = Field(**field.model_dump(), owner_id=current_user.id)
    db.add(db_field)
    db.commit()
    db.refresh(db_field)
    return db_field

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
