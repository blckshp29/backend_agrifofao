from pydantic import BaseModel, Field as PyField, ConfigDict # Rename Field here
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from pydantic import field_validator
from enum import Enum
# Import your models normally
from .models import User, ScheduledTask

class CropTypeEnum(str, Enum):
    coconut = "coconut"
    corn = "corn"
    rice = "rice"
    vegetables = "vegetables"

class SexEnum(str, Enum):
    M = "M"
    F = "F"

class SyncStatusEnum(str, Enum):
    pending = "pending"
    synced = "synced"
    conflict = "conflict"
    deleted = "deleted"

class ProjectStatusEnum(str, Enum):
    planned = "planned"
    active = "active"
    completed = "completed"
    archived = "archived"

class TransactionTypeEnum(str, Enum):
    income = "income"
    expense = "expense"

class OperationTypeEnum(str, Enum):
    land_preparation = "land_preparation"
    planting = "planting"
    fertilization = "fertilization"
    irrigation = "irrigation"
    pest_control = "pest_control"
    harvesting = "harvesting"

class TaskStatusEnum(str, Enum):
    pending = "pending"
    completed = "completed"
    cancelled = "cancelled"
    rescheduled = "rescheduled"

class OtpChannelEnum(str, Enum):
    email = "email"
    sms = "sms"

class SyncMeta(BaseModel):
    client_id: Optional[str] = None
    sync_status: Optional[SyncStatusEnum] = SyncStatusEnum.pending
    last_synced_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    is_deleted: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)

# --- User Schemas ---
class UserBase(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    farm_name: Optional[str] = None
    client_id: Optional[str] = None
    sex: Optional[SexEnum] = None
    location: Optional[str] = None
    province: Optional[str] = None
    city_municipality: Optional[str] = None
    barangay: Optional[str] = None
    mobile_number: Optional[str] = None
    birthdate: Optional[date] = None

    @field_validator("sex", mode="before")
    @classmethod
    def normalize_sex(cls, v):
        if v is None or isinstance(v, SexEnum):
            return v
        if isinstance(v, str):
            val = v.strip().lower()
            if val in {"m", "male"}:
                return SexEnum.M
            if val in {"f", "female"}:
                return SexEnum.F
        return v

    @field_validator("birthdate", mode="before")
    @classmethod
    def parse_birthdate(cls, v):
        if v is None or isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return datetime.strptime(v, "%d/%m/%Y").date()
            except ValueError:
                raise ValueError("birthdate must be in dd/mm/yyyy format")
        return v

class UserCreate(UserBase):
    password: str
    otp_code: Optional[str] = None

class UserLogin(BaseModel):
    identifier: str
    password: str

class User(UserBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    email_verified: bool = False
    phone_verified: bool = False
    last_login_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    sync_status: Optional[SyncStatusEnum] = SyncStatusEnum.pending
    
    model_config = ConfigDict(from_attributes=True)

# --- OTP Schemas ---
class OtpRequest(BaseModel):
    channel: OtpChannelEnum
    destination: str  # email or mobile number

class OtpVerify(BaseModel):
    channel: OtpChannelEnum
    destination: str
    code: str

class OtpResponse(BaseModel):
    success: bool
    message: str

# --- Farm Schemas ---
class FarmBase(BaseModel):
    name: str
    area_hectares: Optional[float] = None
    soil_type: Optional[str] = None
    client_id: Optional[str] = None
    location: Optional[str] = None
    province: Optional[str] = None
    city_municipality: Optional[str] = None
    barangay: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None

class FarmCreate(FarmBase):
    pass

class Farm(FarmBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    sync_status: Optional[SyncStatusEnum] = SyncStatusEnum.pending
    
    model_config = ConfigDict(from_attributes=True)

# --- Field Schemas ---
class FieldBase(BaseModel):
    name: str
    area_hectares: float
    crop_type: CropTypeEnum
    crop_variety: Optional[str] = None
    client_id: Optional[str] = None
    planting_date: Optional[datetime] = None
    land_prep_start_date: Optional[datetime] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None

class FieldCreate(FieldBase):
    farm_id: int

class Field(FieldBase):
    id: int
    farm_id: int
    current_stage: str
    expected_harvest_date: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    sync_status: Optional[SyncStatusEnum] = SyncStatusEnum.pending
    
    model_config = ConfigDict(from_attributes=True)

# --- Inventory Schemas ---
class InventoryBase(BaseModel):
    item_name: str
    category: str
    quantity: float
    unit: str
    unit_cost: float
    client_id: Optional[str] = None

class InventoryCreate(InventoryBase):
    farm_id: int

class Inventory(InventoryBase):
    id: int
    farm_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    sync_status: Optional[SyncStatusEnum] = SyncStatusEnum.pending
    
    model_config = ConfigDict(from_attributes=True)

# --- Crop Project Schemas ---
class CropProjectBase(BaseModel):
    name: str
    crop_type: CropTypeEnum
    crop_variety: Optional[str] = None
    budget_total: float = 0
    currency: str = "PHP"
    client_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    notes: Optional[str] = None
    farm_id: Optional[int] = None
    field_id: Optional[int] = None

class CropProjectCreate(CropProjectBase):
    pass

class CropProjectUpdate(BaseModel):
    name: Optional[str] = None
    crop_type: Optional[CropTypeEnum] = None
    crop_variety: Optional[str] = None
    budget_total: Optional[float] = None
    budget_remaining: Optional[float] = None
    income_total: Optional[float] = None
    expense_total: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[ProjectStatusEnum] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    notes: Optional[str] = None
    farm_id: Optional[int] = None
    field_id: Optional[int] = None

class CropProject(CropProjectBase):
    id: int
    owner_id: int
    budget_remaining: float = 0
    income_total: float = 0
    expense_total: float = 0
    status: ProjectStatusEnum = ProjectStatusEnum.planned
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    sync_status: Optional[SyncStatusEnum] = SyncStatusEnum.pending

    model_config = ConfigDict(from_attributes=True)

# --- Financial Record Schemas ---
class FinancialRecordBase(BaseModel):
    transaction_type: TransactionTypeEnum
    category: str
    amount: float
    currency: str = "PHP"
    description: Optional[str] = None
    client_id: Optional[str] = None
    field_id: Optional[int] = None
    project_id: Optional[int] = None
    is_over_budget: Optional[bool] = False
    over_budget_approved: Optional[bool] = False
    budget_snapshot: Optional[float] = None

class FinancialRecordCreate(FinancialRecordBase):
    pass

class FinancialRecord(FinancialRecordBase):
    id: int
    owner_id: int
    date: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    sync_status: Optional[SyncStatusEnum] = SyncStatusEnum.pending
    
    model_config = ConfigDict(from_attributes=True)

# --- Scheduled Task Schemas ---
class ScheduledTaskBase(BaseModel):    
    task_type: OperationTypeEnum
    task_name: str
    description: Optional[str] = None
    scheduled_date: datetime
    client_id: Optional[str] = None
    original_scheduled_date: Optional[datetime] = None
    rescheduled_reason: Optional[str] = None
    estimated_cost: float
    requires_dry_weather: bool = True
    requires_network: bool = False
    priority: int = PyField(default=1, ge=1, le=5) 
    status: Optional[TaskStatusEnum] = None  # Crucial for changing "pending" to "completed"
    actual_cost: Optional[float] = None
    weather_check_date: Optional[datetime] = None
    weather_status: Optional[str] = None
    completed_at: Optional[datetime] = None
    confirmed_by_user: Optional[bool] = False
    field_id: int
    project_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class ScheduledTaskCreate(ScheduledTaskBase):
    pass # Removed field_id here because it's already in the Base

class ScheduledTask(ScheduledTaskBase):
    id: int
    user_id: int
    status: TaskStatusEnum
    actual_cost: Optional[float] = None
    decision_tree_recommendation: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    sync_status: Optional[SyncStatusEnum] = SyncStatusEnum.pending
    
    model_config = ConfigDict(from_attributes=True)

    # --- Add this to app/schemas.py ---

class ScheduledTaskUpdate(BaseModel):
    task_type: Optional[str] = None
    task_name: Optional[str] = None
    description: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    original_scheduled_date: Optional[datetime] = None
    rescheduled_reason: Optional[str] = None
    estimated_cost: Optional[float] = None
    requires_dry_weather: Optional[bool] = None
    requires_network: Optional[bool] = None
    priority: Optional[int] = None
    status: Optional[TaskStatusEnum] = None
    actual_cost: Optional[float] = None
    weather_check_date: Optional[datetime] = None
    weather_status: Optional[str] = None
    completed_at: Optional[datetime] = None
    confirmed_by_user: Optional[bool] = None
    field_id: Optional[int] = None
    project_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

# --- Weather Data Schemas ---
class WeatherDataBase(BaseModel):
    location_lat: float
    location_lon: float
    date: datetime

class WeatherForecastRequest(BaseModel):
    # Ensure there is a COLON (:) and an EQUALS (=)
    latitude: float = PyField(..., ge=-90, le=90)
    longitude: float = PyField(..., ge=-180, le=180)
    days: int = PyField(default=7, ge=1, le=14) # Open-Meteo free tier limit

class WeatherForecastResponse(BaseModel):
    latitude: float
    longitude: float
    hourly: List[Dict[str, Any]]
    daily: List[Dict[str, Any]]
    retrieved_at: datetime

# --- Decision Tree Schemas ---
class DecisionTreeRequest(BaseModel):
    field_id: int
    operation_type: OperationTypeEnum
    budget_constraint: Optional[float] = None

class DecisionTreeResponse(BaseModel):
    recommended_date: datetime
    confidence_score: float
    estimated_cost: float
    weather_risk: str
    net_financial_return: Optional[float] = None
    recommendation_reason: str

# --- Optimization Request/Response ---
class OptimizationRequest(BaseModel):
    field_id: int
    operation_type: OperationTypeEnum
    current_budget: float

class OptimizationResponse(BaseModel):
    optimal_date: datetime
    predicted_yield_value: float
    total_projected_cost: float
    net_financial_return: float
    weather_conditions: Dict[str, Any]
    budget_constraint_satisfied: bool
    recommendation: str

# --- Rice Schedule Schemas ---
class RiceScheduleRequest(BaseModel):
    land_prep_start_date: Optional[datetime] = None
    crop_variety: Optional[str] = None

# --- Partial Budgeting Schemas ---
class PartialBudgetingInput(BaseModel):
    added_returns: float = 0
    reduced_costs: float = 0
    added_costs: float = 0
    reduced_returns: float = 0

class PartialBudgetingResponse(BaseModel):
    net_benefit: float
    is_profitable: bool
    recommendation: str

# --- Insights Schemas ---
class FinanceBarItem(BaseModel):
    label: str
    percent: float
    value: float

class InsightSummary(BaseModel):
    budget_total: float
    expenses_total: float
    income_total: float
    net_profit: float
    is_over_budget: bool
    budget_bar: FinanceBarItem
    expenses_bar: FinanceBarItem
    income_bar: FinanceBarItem

class InsightComparison(BaseModel):
    previous_label: str
    current_label: str
    previous_expenses_percent: float
    current_expenses_percent: float
    previous_netprofit_percent: float
    current_netprofit_percent: float

# --- Sync Schemas ---
class SyncEntityEnum(str, Enum):
    farm = "farm"
    field = "field"
    inventory = "inventory"
    project = "project"
    financial_record = "financial_record"
    scheduled_task = "scheduled_task"

class SyncPushItem(BaseModel):
    entity: SyncEntityEnum
    data: Dict[str, Any]
    updated_at: Optional[datetime] = None
    is_deleted: Optional[bool] = False

class SyncPushRequest(BaseModel):
    client_id: str
    items: List[SyncPushItem]

class SyncConflictItem(BaseModel):
    entity: SyncEntityEnum
    server_id: int
    client_id: Optional[str]
    reason: str

class SyncPushResponse(BaseModel):
    accepted: int
    conflicts: List[SyncConflictItem]

class SyncPullResponse(BaseModel):
    items: List[SyncPushItem]

# --- Token and Authentication ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
