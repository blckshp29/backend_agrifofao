from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import pandas as pd

# Renamed 'Field' to 'FarmField' to avoid conflict with pydantic.Field
from ..models import Field as FarmField, ScheduledTask, WeatherData 
from ..schemas import ScheduledTaskCreate, WeatherForecastRequest
from ..weather.service import WeatherService
from ..decision_tree.engine import DecisionTreeEngine

class SchedulingService:
    def __init__(self):
        self.weather_service = WeatherService()
        self.decision_tree = DecisionTreeEngine()

    def generate_rice_rc222_schedule(
        self,
        db: Session,
        field: FarmField,
        user_id: int,
        land_prep_start_date: Optional[datetime] = None
    ) -> List[ScheduledTask]:
        """Generate full RC 222 rice schedule based on land preparation start date."""
        if field.crop_type.value != "rice":
            raise Exception("RC 222 schedule is only for rice fields.")

        start_date = land_prep_start_date or field.land_prep_start_date or field.planting_date or datetime.now()

        # Land preparation (0-21 days)
        land_prep_tasks = [
            ("irrigation", "Irrigation", 0, False, None),
            ("land_preparation", "Plowing", 6, True, None),
            ("land_preparation", "Harrowing", 14, True, None),
            ("land_preparation", "Levelling", 21, True, None),
        ]

        # Planting to harvesting (0-110 days) after land preparation
        planting_start = start_date + timedelta(days=21)
        planting_tasks = [
            ("planting", "Transplanting", 0, True, None),
            ("fertilization", "First Fertilizer (Basal)", 10, True, "10-14 days after transplanting"),
            ("fertilization", "Second Fertilizer (Top Dressing)", 30, True, "30-45 days after transplanting"),
            ("fertilization", "Third Fertilizer", 55, True, "55-65 days after transplanting"),
            ("pest_control", "Pest and Weed Control", 67, True, "67-80 days after transplanting"),
            ("irrigation", "Terminal Drainage", 90, False, "90-95 days after transplanting"),
            ("harvesting", "Harvesting", 105, True, "105-110 days after transplanting"),
        ]

        scheduled_tasks: List[ScheduledTask] = []

        def add_task(base_date: datetime, task_tuple):
            op_type, name, offset_days, requires_dry, window = task_tuple
            scheduled_date = base_date + timedelta(days=offset_days)
            description = f"RC 222 schedule: {name}"
            if window:
                description += f" (window: {window})"

            estimated_cost = self.decision_tree._estimate_operation_cost(
                op_type, field.area_hectares
            )

            task_data = ScheduledTaskCreate(
                task_type=op_type,
                task_name=f"{name} - {field.name}",
                description=description,
                scheduled_date=scheduled_date,
                original_scheduled_date=scheduled_date,
                estimated_cost=estimated_cost,
                requires_dry_weather=requires_dry,
                priority=self._calculate_priority(op_type),
                field_id=field.id
            )
            task = self.create_scheduled_task(db, task_data, user_id)
            scheduled_tasks.append(task)

        for t in land_prep_tasks:
            add_task(start_date, t)
        for t in planting_tasks:
            add_task(planting_start, t)

        # Update expected harvest date if not set
        if not field.expected_harvest_date:
            field.expected_harvest_date = planting_start + timedelta(days=110)
            db.commit()

        return scheduled_tasks

    def check_and_reschedule_task(
        self,
        db: Session,
        task: ScheduledTask,
        latitude: float,
        longitude: float
    ) -> ScheduledTask:
        """Check weather for a task and reschedule if unsuitable."""
        weather_request = WeatherForecastRequest(
            latitude=latitude,
            longitude=longitude,
            days=7
        )
        weather_data = self.weather_service.get_weather_forecast(db, weather_request)

        suitability = self.weather_service.check_weather_suitability(
            weather_data, task.scheduled_date, requires_dry_weather=task.requires_dry_weather
        )

        task.weather_check_date = datetime.utcnow()
        task.weather_status = "suitable" if suitability["is_suitable"] else "unsuitable"

        if not suitability["is_suitable"]:
            window_start = task.scheduled_date
            window_end = task.scheduled_date + timedelta(days=7)
            optimal_windows = self.weather_service.get_optimal_weather_window(
                weather_data, window_start, window_end, requires_dry_weather=task.requires_dry_weather
            )
            if optimal_windows:
                best = optimal_windows[0]
                if not task.original_scheduled_date:
                    task.original_scheduled_date = task.scheduled_date
                task.scheduled_date = best["date"]
                task.status = "rescheduled"
                task.rescheduled_reason = "Weather forecast unsuitable"

        db.commit()
        db.refresh(task)
        return task

    def check_tasks_for_date(
        self,
        db: Session,
        user_id: int,
        target_date: datetime
    ) -> List[ScheduledTask]:
        """Run day-before checks for tasks scheduled on target_date."""
        start = datetime(target_date.year, target_date.month, target_date.day)
        end = start + timedelta(days=1)

        tasks = db.query(ScheduledTask).filter(
            ScheduledTask.user_id == user_id,
            ScheduledTask.scheduled_date >= start,
            ScheduledTask.scheduled_date < end,
            ScheduledTask.status == "pending"
        ).all()

        updated_tasks = []
        for task in tasks:
            field = db.query(FarmField).filter(FarmField.id == task.field_id).first()
            if not field:
                continue
            updated = self.check_and_reschedule_task(
                db,
                task,
                latitude=field.location_lat or 13.0,
                longitude=field.location_lon or 123.0
            )
            updated_tasks.append(updated)

        return updated_tasks
    
    def create_scheduled_task(self, db: Session, task_data: ScheduledTaskCreate, user_id: int) -> ScheduledTask:
        """Create a new scheduled task"""
        # In Pydantic V2, use .model_dump() instead of .dict()
        task = ScheduledTask(
            **task_data.model_dump(),
            user_id=user_id
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        
        return task
    
    def generate_optimized_schedule(self, db: Session, field_id: int, user_id: int, 
                                    operations: List[str] = None) -> List[ScheduledTask]:
        """Generate optimized schedule for field operations"""
        # Using the renamed FarmField model here
        field = db.query(FarmField).filter(FarmField.id == field_id).first()
        
        if not field:
            raise Exception(f"Field with id {field_id} not found")
        
        if not operations:
            operations = ["land_preparation", "planting", "fertilization", 
                          "irrigation", "pest_control", "harvesting"]
        else:
            allowed = {"land_preparation", "planting", "fertilization", "irrigation", "pest_control", "harvesting"}
            normalized = []
            for op in operations:
                if not isinstance(op, str):
                    continue
                op_norm = op.strip().lower()
                if op_norm in allowed:
                    normalized.append(op_norm)
            if not normalized:
                raise Exception("Invalid operations list. Allowed: land_preparation, planting, fertilization, irrigation, pest_control, harvesting")
            operations = normalized
        
        scheduled_tasks = []
        current_date = field.planting_date if field.planting_date else datetime.now()
        
        crop_params = self.decision_tree.crop_parameters.get(
            field.crop_type, 
            self.decision_tree.crop_parameters["corn"]
        )
        
        # Get weather forecast
        weather_request = WeatherForecastRequest(
            latitude=field.location_lat or 13.0,
            longitude=field.location_lon or 123.0,
            days=14
        )
        
        weather_data = self.weather_service.get_weather_forecast(db, weather_request)
        
        for operation in operations:
            days_to_add = crop_params["growth_stages"].get(operation, 7)
            proposed_date = current_date + timedelta(days=days_to_add)
            
            weather_suitability = self.weather_service.check_weather_suitability(
                weather_data, proposed_date, requires_dry_weather=True
            )
            
            if not weather_suitability["is_suitable"]:
                start_window = proposed_date - timedelta(days=7)
                end_window = proposed_date + timedelta(days=7)
                
                optimal_windows = self.weather_service.get_optimal_weather_window(
                    weather_data, start_window, end_window, requires_dry_weather=True
                )
                
                if optimal_windows:
                    optimal_window = next(
                        (w for w in optimal_windows if w["is_suitable"]), 
                        optimal_windows[0]
                    )
                    optimal_date = optimal_window["date"]
                else:
                    optimal_date = proposed_date
            else:
                optimal_date = proposed_date
            
            estimated_cost = self.decision_tree._estimate_operation_cost(
                operation, field.area_hectares
            )
            
            task_data = ScheduledTaskCreate(
                task_type=operation,
                task_name=f"{operation.replace('_', ' ').title()} - {field.name}",
                description=f"Automatically scheduled {operation} for {field.crop_type}",
                scheduled_date=optimal_date,
                estimated_cost=estimated_cost,
                requires_dry_weather=True,
                priority=self._calculate_priority(operation),
                field_id=field_id
            )
            
            task = self.create_scheduled_task(db, task_data, user_id)
            task.decision_tree_recommendation = True
            db.commit()
            
            scheduled_tasks.append(task)
            current_date = optimal_date
        
        return scheduled_tasks
    
    def _calculate_priority(self, operation: str) -> int:
        """Calculate priority level for operation"""
        priorities = {
            "land_preparation": 1,
            "planting": 2,
            "fertilization": 3,
            "irrigation": 4,
            "pest_control": 3,
            "harvesting": 1
        }
        return priorities.get(operation, 3)

    # ... (Rest of the methods remain the same, just ensure they use 'FarmField' or 'field')
