from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FCMDeviceToken, User
from ..notifications.service import send_push_to_user
from ..schemas import FCMToken, FCMTokenUpsert, PushNotificationRequest
from .auth import get_current_user

router = APIRouter()


def _upsert_device_token(db: Session, current_user: User, payload: FCMTokenUpsert) -> FCMDeviceToken:
    existing = (
        db.query(FCMDeviceToken)
        .filter(FCMDeviceToken.user_id == current_user.id, FCMDeviceToken.token == payload.token)
        .first()
    )
    if existing:
        existing.device_type = payload.device_type or "web"
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    db_token = FCMDeviceToken(
        user_id=current_user.id,
        token=payload.token,
        device_type=payload.device_type or "web",
        is_active=True,
    )
    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token


@router.post("/notifications/device-token", response_model=FCMToken, status_code=status.HTTP_201_CREATED)
def save_device_token(
    payload: FCMTokenUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _upsert_device_token(db, current_user, payload)


@router.post("/notifications/fcm-token", response_model=FCMToken, status_code=status.HTTP_201_CREATED)
def save_fcm_token(
    payload: FCMTokenUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _upsert_device_token(db, current_user, payload)


@router.patch("/users/me/fcm-token", response_model=FCMToken)
def patch_my_fcm_token(
    payload: FCMTokenUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _upsert_device_token(db, current_user, payload)


@router.post("/notifications/test")
def send_test_notification(
    payload: PushNotificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = send_push_to_user(
        db=db,
        user_id=current_user.id,
        title=payload.title,
        body=payload.body,
        data=payload.data,
        topic=payload.topic,
        notification_type="test",
    )
    return {
        "success": result.get("success_count", 0) > 0 or result.get("stored_notification_id") is not None,
        **result,
    }
