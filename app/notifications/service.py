import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..models import FCMDeviceToken, Notification, UserPreference


INVALID_TOKEN_MARKERS = (
    "registration-token-not-registered",
    "invalid-registration-token",
    "unregistered",
)


def _is_invalid_token_error(exc: Exception) -> bool:
    code = getattr(exc, "code", "")
    if isinstance(code, str):
        code_lower = code.lower()
        if any(marker in code_lower for marker in INVALID_TOKEN_MARKERS):
            return True

    message = str(exc).lower()
    return any(marker in message for marker in INVALID_TOKEN_MARKERS)


def create_in_app_notification(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    notification_type: str = "system",
    data: Optional[Dict[str, Any]] = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        title=title,
        message=body,
        type=notification_type,
        data=json.dumps(data) if data else None,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def send_push_to_user(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
    topic: Optional[str] = None,
    notification_type: str = "system",
    store_in_app: bool = True,
    notification_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    stored_notification_id = None
    if store_in_app:
        stored_notification = create_in_app_notification(
            db=db,
            user_id=user_id,
            title=title,
            body=body,
            notification_type=notification_type,
            data=notification_data,
        )
        stored_notification_id = stored_notification.id

    preferences = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    push_enabled = preferences.push_notifications if preferences else True

    if not push_enabled:
        return {
            "success_count": 0,
            "failure_count": 0,
            "invalidated_count": 0,
            "stored_notification_id": stored_notification_id,
            "push_enabled": False,
            "push_attempted": False,
            "message": "Push notifications are disabled for this user.",
        }

    try:
        from firebase_admin import messaging
    except Exception as exc:
        return {
            "success_count": 0,
            "failure_count": 0,
            "invalidated_count": 0,
            "stored_notification_id": stored_notification_id,
            "push_enabled": True,
            "push_attempted": False,
            "message": f"Firebase messaging unavailable: {exc}",
        }

    tokens = (
        db.query(FCMDeviceToken)
        .filter(FCMDeviceToken.user_id == user_id, FCMDeviceToken.is_active.is_(True))
        .all()
    )

    success_count = 0
    failure_count = 0
    invalidated_count = 0

    # Optional topic send
    if topic:
        topic_message = messaging.Message(
            topic=topic,
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
        )
        try:
            messaging.send(topic_message)
            success_count += 1
        except Exception:
            failure_count += 1

    if not tokens:
        return {
            "success_count": success_count,
            "failure_count": failure_count,
            "invalidated_count": invalidated_count,
            "stored_notification_id": stored_notification_id,
            "push_enabled": True,
            "push_attempted": bool(topic),
            "message": "Notification stored. No active device tokens found.",
        }

    token_values = [row.token for row in tokens]
    multicast = messaging.MulticastMessage(
        tokens=token_values,
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
    )

    try:
        batch_response = messaging.send_each_for_multicast(multicast)
    except Exception as exc:
        return {
            "success_count": success_count,
            "failure_count": failure_count + len(token_values),
            "invalidated_count": invalidated_count,
            "stored_notification_id": stored_notification_id,
            "push_enabled": True,
            "push_attempted": True,
            "message": f"Push send failed: {exc}",
        }

    success_count += batch_response.success_count
    failure_count += batch_response.failure_count

    for index, response in enumerate(batch_response.responses):
        if response.success:
            continue
        if response.exception and _is_invalid_token_error(response.exception):
            tokens[index].is_active = False
            invalidated_count += 1

    if invalidated_count:
        db.commit()

    return {
        "success_count": success_count,
        "failure_count": failure_count,
        "invalidated_count": invalidated_count,
        "stored_notification_id": stored_notification_id,
        "push_enabled": True,
        "push_attempted": True,
        "message": "Notification processed.",
    }
