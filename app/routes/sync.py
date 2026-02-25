from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..database import get_db
from ..models import Farm, Field, Inventory, CropProject, FinancialRecord, ScheduledTask, User
from ..schemas import SyncPushRequest, SyncPushResponse, SyncPullResponse, SyncConflictItem, SyncPushItem, SyncEntityEnum
from .auth import get_current_user

router = APIRouter()

ENTITY_MAP = {
    "farm": Farm,
    "field": Field,
    "inventory": Inventory,
    "project": CropProject,
    "financial_record": FinancialRecord,
    "scheduled_task": ScheduledTask,
}

def _resolve_owner_filter(model, user_id: int):
    if hasattr(model, "owner_id"):
        return {"owner_id": user_id}
    if hasattr(model, "user_id"):
        return {"user_id": user_id}
    return {}

def _get_existing(db: Session, model, user_id: int, data: Dict[str, Any]):
    if "id" in data and data["id"]:
        return db.query(model).filter(
            model.id == data["id"], **_resolve_owner_filter(model, user_id)
        ).first()
    if "client_id" in data and data["client_id"]:
        return db.query(model).filter(
            model.client_id == data["client_id"], **_resolve_owner_filter(model, user_id)
        ).first()
    return None

def _apply_data(target, data: Dict[str, Any]):
    for key, value in data.items():
        if hasattr(target, key):
            setattr(target, key, value)

@router.post("/sync/push", response_model=SyncPushResponse)
def sync_push(
    payload: SyncPushRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    accepted = 0
    conflicts: List[SyncConflictItem] = []

    for item in payload.items:
        entity = item.entity.value
        model = ENTITY_MAP.get(entity)
        if not model:
            continue

        data = dict(item.data)
        data["client_id"] = data.get("client_id") or payload.client_id

        existing = _get_existing(db, model, current_user.id, data)
        incoming_updated_at = item.updated_at or datetime.utcnow()

        if existing:
            server_updated_at = getattr(existing, "updated_at", None) or getattr(existing, "created_at", None)
            if server_updated_at and incoming_updated_at < server_updated_at:
                existing.sync_status = "conflict"
                db.commit()
                conflicts.append(SyncConflictItem(
                    entity=item.entity,
                    server_id=existing.id,
                    client_id=getattr(existing, "client_id", None),
                    reason="incoming_older_than_server"
                ))
                continue

            if item.is_deleted:
                existing.is_deleted = True
                existing.deleted_at = incoming_updated_at
                existing.sync_status = "synced"
            else:
                _apply_data(existing, data)
                existing.sync_status = "synced"
                existing.updated_at = incoming_updated_at
            accepted += 1
        else:
            data["updated_at"] = incoming_updated_at
            data["sync_status"] = "synced"
            if item.is_deleted:
                data["is_deleted"] = True
                data["deleted_at"] = incoming_updated_at

            owner_fields = _resolve_owner_filter(model, current_user.id)
            data.update(owner_fields)
            new_obj = model(**data)
            db.add(new_obj)
            accepted += 1

    db.commit()
    return {"accepted": accepted, "conflicts": conflicts}

@router.get("/sync/pull", response_model=SyncPullResponse)
def sync_pull(
    since: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    items: List[SyncPushItem] = []
    for entity, model in ENTITY_MAP.items():
        query = db.query(model).filter(**_resolve_owner_filter(model, current_user.id))
        if since:
            if hasattr(model, "updated_at"):
                query = query.filter(model.updated_at >= since)
            else:
                query = query.filter(model.created_at >= since)
        records = query.all()
        for r in records:
            data = r.__dict__.copy()
            data.pop("_sa_instance_state", None)
            items.append(SyncPushItem(
                entity=SyncEntityEnum(entity),
                data=data,
                updated_at=getattr(r, "updated_at", None) or getattr(r, "created_at", None),
                is_deleted=getattr(r, "is_deleted", False)
            ))

    return {"items": items}
