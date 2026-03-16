from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta

from .. import models, schemas
from ..database import get_db
from ..models import ScheduledTask, Field, User, FinancialRecord
from ..schemas import ScheduledTaskCreate, ScheduledTask as ScheduledTaskSchema, RiceScheduleRequest
from ..scheduling.service import SchedulingService
from ..decision_tree.engine import DecisionTreeEngine
from ..schemas import DecisionTreeRequest, DecisionTreeResponse, OptimizationRequest, OptimizationResponse
from ..notifications.service import send_push_to_user
from .auth import get_current_user


router = APIRouter()
scheduling_service = SchedulingService()
decision_tree = DecisionTreeEngine()


class TaskDelayRequest(schemas.BaseModel):
    delay_days: int = 1


class TaskMoveRequest(schemas.BaseModel):
    new_date: datetime

@router.post("/scheduling/service", response_model=ScheduledTaskSchema)
def create_scheduled_task(
    task: ScheduledTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify field belongs to user
    field = db.query(Field).filter(
        Field.id == task.field_id,
        Field.owner_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    
    return scheduling_service.create_scheduled_task(db, task, current_user.id)

@router.get("/scheduling/tasks", response_model=List[ScheduledTaskSchema])
def get_scheduled_tasks(
    status: str = None,
    field_id: int = None,
    start_date: datetime = None,
    end_date: datetime = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(ScheduledTask).filter(ScheduledTask.user_id == current_user.id)
    
    if status:
        query = query.filter(ScheduledTask.status == status)
    if field_id:
        query = query.filter(ScheduledTask.field_id == field_id)
    if start_date:
        query = query.filter(ScheduledTask.scheduled_date >= start_date)
    if end_date:
        query = query.filter(ScheduledTask.scheduled_date <= end_date)
    
    tasks = query.order_by(ScheduledTask.scheduled_date).all()
    return tasks

@router.post("/scheduling/generate-optimized/{field_id}")
def generate_optimized_schedule(
    field_id: int,
    operations: List[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify field belongs to user
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.owner_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    
    tasks = scheduling_service.generate_optimized_schedule(
        db, field_id, current_user.id, operations
    )
    
    return {
        "message": f"Generated {len(tasks)} optimized tasks",
        "tasks": tasks,
        "field_id": field_id
    }

@router.post("/scheduling/decision-tree/recommend", response_model=DecisionTreeResponse)
def get_decision_tree_recommendation(
    request: DecisionTreeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify field belongs to user
    field = db.query(Field).filter(
        Field.id == request.field_id,
        Field.owner_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    
    # Get weather data
    from ..weather.service import WeatherService
    weather_service = WeatherService()
    
    from ..schemas import WeatherForecastRequest
    weather_request = WeatherForecastRequest(
        latitude=field.location_lat or 13.0,
        longitude=field.location_lon or 123.0,
        days=5
    )
    
    weather_data = weather_service.get_weather_forecast(db, weather_request)
    
    # Get current budget from financial records
    financial_records = db.query(FinancialRecord).filter(
        FinancialRecord.owner_id == current_user.id,
        FinancialRecord.field_id == request.field_id
    ).all()
    
    total_expenses = sum(r.amount for r in financial_records if r.transaction_type == "expense")
    # Simplified budget calculation
    current_budget = 100000 - total_expenses  # Example starting budget
    
    return decision_tree.predict_optimal_date(
        db, request, weather_data, current_budget
    )

@router.post("/scheduling/decision-tree/train/{crop_type}")
def train_decision_tree(
    crop_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        from ..schemas import CropTypeEnum
        crop_enum = CropTypeEnum(crop_type)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid crop_type")

    result = decision_tree.train_model_for_crop(db, crop_enum, current_user.id)
    return {"message": "Training completed", "result": result}

@router.post("/scheduling/rice/{field_id}")
@router.post("/scheduling/rice/rc222/{field_id}")
def generate_rice_variety_schedule(
    field_id: int,
    payload: RiceScheduleRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    payload = payload or RiceScheduleRequest()
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.owner_id == current_user.id
    ).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    if field.crop_type.value != "rice":
        raise HTTPException(status_code=400, detail="Rice schedule is only for rice fields")

    if payload.crop_variety:
        field.crop_variety = payload.crop_variety
        db.commit()

    try:
        tasks = scheduling_service.generate_rice_variety_schedule(
            db=db,
            field=field,
            user_id=current_user.id,
            land_prep_start_date=payload.land_prep_start_date
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    selected_variety = field.crop_variety or "NSIC Rc222"
    return {
        "message": f"Generated {len(tasks)} rice tasks for {selected_variety}",
        "field_id": field_id,
        "crop_variety": selected_variety,
        "tasks": tasks
    }

@router.post("/scheduling/tasks/{task_id}/check-weather", response_model=ScheduledTaskSchema)
def check_task_weather(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = db.query(ScheduledTask).filter(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == current_user.id
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    field = db.query(Field).filter(
        Field.id == task.field_id,
        Field.owner_id == current_user.id
    ).first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    original_date = task.scheduled_date
    updated_task = scheduling_service.check_and_reschedule_task(
        db,
        task,
        latitude=field.location_lat or 13.0,
        longitude=field.location_lon or 123.0
    )
    if updated_task.status == "rescheduled":
        send_push_to_user(
            db=db,
            user_id=current_user.id,
            title="Task Rescheduled Due to Weather",
            body=f"{updated_task.task_name} moved to {updated_task.scheduled_date.strftime('%Y-%m-%d %H:%M')}",
            data={
                "event": "task_rescheduled",
                "task_id": str(updated_task.id),
                "old_date": original_date.isoformat(),
                "new_date": updated_task.scheduled_date.isoformat(),
            },
            notification_type="task_rescheduled",
        )
    return updated_task

@router.post("/scheduling/tasks/check-tomorrow")
def check_tomorrow_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return {
        "success": True,
        "items": scheduling_service.process_tomorrow_task_notifications(db, current_user.id),
    }


@router.post("/scheduling/tasks/{task_id}/delay", response_model=ScheduledTaskSchema)
def delay_task_from_notification(
    task_id: int,
    payload: TaskDelayRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = db.query(ScheduledTask).filter(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == current_user.id
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        return scheduling_service.delay_task(db, task, payload.delay_days)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/scheduling/tasks/{task_id}/move", response_model=ScheduledTaskSchema)
def move_task_from_notification(
    task_id: int,
    payload: TaskMoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = db.query(ScheduledTask).filter(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == current_user.id
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        return scheduling_service.move_task(db, task, payload.new_date)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/scheduling/optimize", response_model=OptimizationResponse)
def optimize_schedule(
    request: OptimizationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify field belongs to user
    field = db.query(Field).filter(
        Field.id == request.field_id,
        Field.owner_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    
    # Get decision tree recommendation
    dt_request = DecisionTreeRequest(
        field_id=request.field_id,
        operation_type=request.operation_type,
        budget_constraint=request.current_budget
    )
    
    # Get weather data
    from ..weather.service import WeatherService
    weather_service = WeatherService()
    
    from ..schemas import WeatherForecastRequest
    weather_request = WeatherForecastRequest(
        latitude=field.location_lat or 13.0,
        longitude=field.location_lon or 123.0,
        days=5
    )
    
    weather_data = weather_service.get_weather_forecast(db, weather_request)
    
    dt_response = decision_tree.predict_optimal_date(
        db, dt_request, weather_data, request.current_budget
    )
    
    # Calculate predicted yield value
    predicted_yield_value = decision_tree._predict_yield(
        field.crop_type, request.operation_type.value,
        dt_response.confidence_score * 100, field.area_hectares
    )
    
    # Calculate Net Financial Return
    nfr = decision_tree.calculate_net_financial_return(
        predicted_yield_value, dt_response.estimated_cost
    )
    
    # Check budget constraint
    budget_constraint_satisfied = dt_response.estimated_cost <= request.current_budget
    
    return OptimizationResponse(
        optimal_date=dt_response.recommended_date,
        predicted_yield_value=predicted_yield_value,
        total_projected_cost=dt_response.estimated_cost,
        net_financial_return=nfr,
        weather_conditions={
            "risk_level": dt_response.weather_risk,
            "confidence": dt_response.confidence_score
        },
        budget_constraint_satisfied=budget_constraint_satisfied,
        recommendation=dt_response.recommendation_reason
    )

@router.get("/scheduling/farm-cycle/{field_id}")
def get_farm_cycle_timeline(
    field_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify field belongs to user
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.owner_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    
    return scheduling_service.calculate_farm_cycle_timeline(db, field_id, current_user.id)

@router.get("/scheduling/farm-cycle/grouped/{field_id}")
def get_farm_cycle_timeline_grouped(
    field_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    field = db.query(Field).filter(
        Field.id == field_id,
        Field.owner_id == current_user.id
    ).first()

    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    return scheduling_service.calculate_farm_cycle_timeline(db, field_id, current_user.id)

@router.patch("/scheduling/tasks/{task_id}", response_model=schemas.ScheduledTask)
def update_task(
    task_id: int, 
    task_update: schemas.ScheduledTaskUpdate, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    # 1. Search for the task by ID and verify the user owns it
    task_query = db.query(models.ScheduledTask).filter(
        models.ScheduledTask.id == task_id,
        models.ScheduledTask.user_id == current_user.id
    )
    
    db_task = task_query.first()

    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 2. Convert the input to a dictionary and REMOVE any fields the user didn't send
    # This prevents overwriting existing data with None
    update_data = task_update.model_dump(exclude_unset=True)

    # 3. Execute the update
    task_query.update(update_data, synchronize_session=False)
    db.commit()

    return task_query.first()
