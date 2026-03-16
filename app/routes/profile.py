import json
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification as NotificationModel
from ..models import User, UserPreference
from ..schemas import (
    Notification,
    NotificationCreate,
    PasswordChangeRequest,
    User as UserSchema,
    UserPreference as UserPreferenceSchema,
    UserPreferenceUpdate,
    UserUpdate,
)
from .auth import get_current_user, get_password_hash, verify_password

router = APIRouter()


def _get_or_create_preferences(db: Session, user_id: int) -> UserPreference:
    prefs = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if prefs:
        return prefs

    prefs = UserPreference(user_id=user_id)
    db.add(prefs)
    db.commit()
    db.refresh(prefs)
    return prefs


@router.patch("/users/me", response_model=UserSchema)
def update_my_profile(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)

    if "mobile_number" in data and data["mobile_number"]:
        mobile_owner = (
            db.query(User)
            .filter(User.mobile_number == data["mobile_number"], User.id != current_user.id)
            .first()
        )
        if mobile_owner:
            raise HTTPException(status_code=400, detail="Mobile number already registered")

    for key, value in data.items():
        setattr(current_user, key, value)

    db.commit()
    db.refresh(current_user)
    return current_user


@router.patch("/users/me/password")
def change_my_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different")

    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    return {"success": True, "message": "Password updated successfully"}


@router.get("/users/me/settings", response_model=UserPreferenceSchema)
def get_my_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_or_create_preferences(db, current_user.id)


@router.patch("/users/me/settings", response_model=UserPreferenceSchema)
def update_my_settings(
    payload: UserPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prefs = _get_or_create_preferences(db, current_user.id)
    data = payload.model_dump(exclude_unset=True)

    for key, value in data.items():
        setattr(prefs, key, value)

    db.commit()
    db.refresh(prefs)
    return prefs


@router.get("/notifications", response_model=List[Notification])
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(NotificationModel).filter(NotificationModel.user_id == current_user.id)
    if unread_only:
        query = query.filter(NotificationModel.is_read.is_(False))

    return (
        query.order_by(NotificationModel.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.post("/notifications", response_model=Notification, status_code=status.HTTP_201_CREATED)
def create_notification(
    payload: NotificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = NotificationModel(
        user_id=current_user.id,
        title=payload.title,
        message=payload.message,
        type=payload.type,
        data=json.dumps(payload.data) if payload.data else None,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


@router.patch("/notifications/{notification_id}/read", response_model=Notification)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(NotificationModel)
        .filter(
            NotificationModel.id == notification_id,
            NotificationModel.user_id == current_user.id,
        )
        .first()
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.commit()
    db.refresh(notification)
    return notification


@router.patch("/notifications/read-all", status_code=status.HTTP_200_OK)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(NotificationModel).filter(
        NotificationModel.user_id == current_user.id,
        NotificationModel.is_read.is_(False),
    )
    updated_count = query.update(
        {"is_read": True, "read_at": datetime.utcnow()},
        synchronize_session=False,
    )
    db.commit()
    return {"success": True, "updated": updated_count}
