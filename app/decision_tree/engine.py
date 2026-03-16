import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeRegressor, DecisionTreeClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, accuracy_score
from datetime import datetime, timedelta
import json
from typing import Dict, List, Any, Optional, Tuple
import joblib
from sqlalchemy.orm import Session

from config import config
from ..models import Field, ScheduledTask, FinancialRecord, WeatherData, DecisionTreeModel
from ..schemas import DecisionTreeRequest, DecisionTreeResponse, CropTypeEnum
from ..weather.service import WeatherService

class DecisionTreeEngine:
    def __init__(self):
        self.models = {}
        self.crop_parameters = {
            CropTypeEnum.coconut: {
                "growth_stages": {
                    "land_preparation": 7,
                    "planting": 1,
                    "fertilization": 30,
                    "irrigation": 7,
                    "pest_control": 15,
                    "harvesting": 180
                },
                "optimal_temp_range": (25, 32),
                "optimal_rainfall": 1500,
                "fertilizer_frequency": 90  # days
            },
            CropTypeEnum.corn: {
                "growth_stages": {
                    "land_preparation": 7,
                    "planting": 1,
                    "fertilization": 21,
                    "irrigation": 3,
                    "pest_control": 14,
                    "harvesting": 90
                },
                "optimal_temp_range": (20, 30),
                "optimal_rainfall": 500,
                "fertilizer_frequency": 30
            },
            CropTypeEnum.rice: {
                "growth_stages": {
                    "land_preparation": 14,
                    "planting": 1,
                    "fertilization": 25,
                    "irrigation": 1,
                    "pest_control": 20,
                    "harvesting": 120
                },
                "optimal_temp_range": (20, 35),
                "optimal_rainfall": 1000,
                "fertilizer_frequency": 35
            }
        }
        self.rc222_schedule = {
            "land_preparation": [
                {"name": "Irrigation", "min_offset": 0, "max_offset": 0, "requires_dry": False},
                {"name": "Plowing", "min_offset": 6, "max_offset": 6, "requires_dry": True},
                {"name": "Harrowing", "min_offset": 14, "max_offset": 14, "requires_dry": True},
                {"name": "Levelling", "min_offset": 21, "max_offset": 21, "requires_dry": True},
            ],
            "planting_to_harvest": [
                {"name": "Transplanting", "min_offset": 0, "max_offset": 0, "requires_dry": True},
                {"name": "First Fertilizer (Basal)", "min_offset": 10, "max_offset": 14, "requires_dry": True},
                {"name": "Second Fertilizer (Top Dressing)", "min_offset": 30, "max_offset": 45, "requires_dry": True},
                {"name": "Third Fertilizer", "min_offset": 55, "max_offset": 65, "requires_dry": True},
                {"name": "Pest and Weed Control", "min_offset": 67, "max_offset": 80, "requires_dry": True},
                {"name": "Terminal Drainage", "min_offset": 90, "max_offset": 95, "requires_dry": False},
                {"name": "Harvesting", "min_offset": 107, "max_offset": 111, "requires_dry": True},
            ],
        }
    
    def train_model_for_crop(self, db: Session, crop_type: CropTypeEnum, user_id: int):
        """Train decision tree model for specific crop type"""
        # Collect training data
        training_data = self._collect_training_data(db, crop_type, user_id)
        
        if len(training_data) < 10:
            raise Exception(f"Insufficient training data for {crop_type}. Need at least 10 records.")
        
        # Prepare features and target
        df = pd.DataFrame(training_data)
        
        # Feature columns (adjust based on your data)
        feature_cols = [
            'days_since_planting', 'temperature', 'humidity', 
            'soil_moisture', 'budget_utilization', 'previous_yield'
        ]
        
        # Ensure all features exist
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0
        
        X = df[feature_cols]
        
        # Target: success_score (1 for successful operations, 0 for unsuccessful)
        if 'success_score' not in df.columns:
            df['success_score'] = 1  # Default
        
        y = df['success_score']
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Train model
        model = DecisionTreeRegressor(
            max_depth=config.DECISION_TREE_MAX_DEPTH,
            min_samples_split=config.DECISION_TREE_MIN_SAMPLES_SPLIT,
            random_state=42
        )
        
        model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test)
        mse = mean_squared_error(y_test, y_pred)
        accuracy = model.score(X_test, y_test)
        
        # Get feature importance
        feature_importance = dict(zip(feature_cols, model.feature_importances_))
        
        # Save model to database
        dt_model = DecisionTreeModel(
            model_name=f"{crop_type.value}_model",
            crop_type=crop_type,
            accuracy=accuracy,
            parameters=json.dumps(model.get_params()),
            feature_importance=json.dumps(feature_importance)
        )
        
        db.add(dt_model)
        db.commit()
        
        # Also save to file for persistence
        model_filename = f"models/{crop_type.value}_decision_tree.joblib"
        joblib.dump(model, model_filename)
        
        # Cache model
        self.models[crop_type.value] = {
            "model": model,
            "accuracy": accuracy,
            "feature_importance": feature_importance
        }
        
        return {
            "accuracy": accuracy,
            "mse": mse,
            "feature_importance": feature_importance,
            "training_samples": len(training_data)
        }
    
    def _collect_training_data(self, db: Session, crop_type: CropTypeEnum, user_id: int) -> List[Dict]:
        """Collect historical data for training"""
        training_data = []
        
        # Get fields with specific crop type
        fields = db.query(Field).filter(
            Field.crop_type == crop_type,
            Field.owner_id == user_id
        ).all()
        
        for field in fields:
            # Get scheduled tasks for this field
            tasks = db.query(ScheduledTask).filter(
                ScheduledTask.field_id == field.id,
                ScheduledTask.status == "completed"
            ).all()
            
            for task in tasks:
                # Get weather data for task date
                weather = db.query(WeatherData).filter(
                    WeatherData.location_lat == field.location_lat,
                    WeatherData.location_lon == field.location_lon,
                    WeatherData.date >= task.scheduled_date - timedelta(days=1),
                    WeatherData.date <= task.scheduled_date + timedelta(days=1)
                ).first()
                
                # Get financial records for this task
                financial = db.query(FinancialRecord).filter(
                    FinancialRecord.field_id == field.id,
                    FinancialRecord.date >= task.scheduled_date - timedelta(days=7),
                    FinancialRecord.date <= task.scheduled_date + timedelta(days=7)
                ).all()
                
                # Calculate features
                data_point = {
                    "field_id": field.id,
                    "task_type": task.task_type,
                    "days_since_planting": (task.scheduled_date - field.planting_date).days if field.planting_date else 0,
                    "temperature": weather.temperature_2m if weather else 25,
                    "humidity": weather.relative_humidity_2m if weather else 60,
                    "soil_moisture": weather.soil_moisture_0_1cm if weather else 30,
                    "budget_utilization": task.actual_cost if task.actual_cost else task.estimated_cost,
                    "previous_yield": 0,  # This would come from harvest records
                    "success_score": 1 if task.status == "completed" else 0
                }
                
                training_data.append(data_point)
        
        return training_data

    def get_rc222_tasks(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.rc222_schedule
    
    def predict_optimal_date(
        self,
        db: Session,
        request: DecisionTreeRequest,
        weather_data: Dict,
        current_budget: float,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
        requires_dry_weather: bool = True
    ) -> DecisionTreeResponse:
        """Predict optimal date for farming operation"""
        field = db.query(Field).filter(Field.id == request.field_id).first()
        
        if not field:
            raise Exception(f"Field with id {request.field_id} not found")
        
        crop_type = field.crop_type
        crop_params = self.crop_parameters.get(crop_type, self.crop_parameters[CropTypeEnum.corn])
        
        # Get weather windows
        weather_service = WeatherService()
        
        # Define date range for prediction
        start_date = window_start or datetime.now()
        end_date = window_end or (start_date + timedelta(days=30))  # Default lookahead

        optimal_windows = weather_service.get_optimal_weather_window(
            weather_data, start_date, end_date, 
            requires_dry_weather=requires_dry_weather
        )
        
        if not optimal_windows:
            # Fallback: choose date with least precipitation
            optimal_windows = weather_service.get_optimal_weather_window(
                weather_data, start_date, end_date, 
                requires_dry_weather=False
            )
        
        if not optimal_windows:
            raise Exception("No suitable weather windows found in the next 30 days")
        
        # Apply budget constraint
        suitable_windows = []
        for window in optimal_windows:
            # Estimate cost for operation
            estimated_cost = self._estimate_operation_cost(
                request.operation_type, field.area_hectares
            )
            
            if request.budget_constraint and estimated_cost > request.budget_constraint:
                continue  # Skip if over budget
            
            window["estimated_cost"] = estimated_cost
            window["budget_ok"] = True
            
            # Calculate net financial return (simplified)
            predicted_yield = self._predict_yield(
                crop_type, request.operation_type, 
                window["weather_score"], field.area_hectares
            )
            
            window["predicted_yield_value"] = predicted_yield
            window["net_financial_return"] = predicted_yield - estimated_cost
            
            suitable_windows.append(window)
        
        if not suitable_windows:
            # Relax budget constraint if no windows found
            for window in optimal_windows:
                estimated_cost = self._estimate_operation_cost(
                    request.operation_type, field.area_hectares
                )
                
                window["estimated_cost"] = estimated_cost
                window["budget_ok"] = estimated_cost <= request.budget_constraint if request.budget_constraint else True
                
                suitable_windows.append(window)
        
        # Sort by net financial return, then by weather score
        suitable_windows.sort(key=lambda x: (
            x.get("net_financial_return", 0) if x.get("net_financial_return") is not None else 0,
            x.get("weather_score", 0)
        ), reverse=True)
        
        best_window = suitable_windows[0]
        
        # Determine weather risk level
        weather_risk = "low"
        if best_window["precipitation"] > 5:
            weather_risk = "medium"
        if best_window["precipitation"] > 10:
            weather_risk = "high"
        
        # Generate recommendation reason
        reasons = []
        if best_window.get("weather_score", 0) >= 80:
            reasons.append("Excellent weather conditions")
        elif best_window.get("weather_score", 0) >= 60:
            reasons.append("Good weather conditions")
        else:
            reasons.append("Acceptable weather conditions")
        
        if best_window.get("budget_ok", False):
            reasons.append("Within budget constraints")
        else:
            reasons.append(f"Estimated cost: {best_window['estimated_cost']:.2f} PHP")
        
        return DecisionTreeResponse(
            recommended_date=best_window["date"],
            confidence_score=min(0.95, best_window.get("weather_score", 0) / 100),
            estimated_cost=best_window.get("estimated_cost", 0),
            weather_risk=weather_risk,
            net_financial_return=best_window.get("net_financial_return"),
            recommendation_reason="; ".join(reasons)
        )
    
    def _estimate_operation_cost(self, operation_type: str, area_hectares: float) -> float:
        """Estimate cost for farming operation"""
        cost_estimates = {
            "land_preparation": 5000 * area_hectares,
            "planting": 3000 * area_hectares,
            "fertilization": 2000 * area_hectares,
            "irrigation": 1000 * area_hectares,
            "pest_control": 1500 * area_hectares,
            "harvesting": 4000 * area_hectares
        }
        
        return cost_estimates.get(operation_type, 1000 * area_hectares)
    
    def _predict_yield(self, crop_type: CropTypeEnum, operation_type: str, 
                      weather_score: float, area_hectares: float) -> float:
        """Predict yield value for operation"""
        # Base yield per hectare (in PHP)
        base_yields = {
            CropTypeEnum.coconut: 50000,
            CropTypeEnum.corn: 30000,
            CropTypeEnum.rice: 40000
        }
        
        base_yield = base_yields.get(crop_type, 20000)
        
        # Operation impact factors 
        impact_factors = {
            "land_preparation": 0.1,
            "planting": 0.15,
            "fertilization": 0.25,
            "irrigation": 0.2,
            "pest_control": 0.15,
            "harvesting": 0.15
        }
        
        impact = impact_factors.get(operation_type, 0.1)
        
        # Weather adjustment (0.5 to 1.5 multiplier based on weather score)
        weather_multiplier = 0.5 + (weather_score / 100)
        
        predicted_value = base_yield * area_hectares * impact * weather_multiplier
        
        return predicted_value
    
    def calculate_net_financial_return(self, predicted_yield: float, total_cost: float) -> float:
        """Calculate Net Financial Return as per thesis formula"""
        return predicted_yield - total_cost
