from app.database import Base
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Enum, Text, Date, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import enum


class CropType(str, enum.Enum):
    COCONUT = "coconut"
    CORN = "corn"
    RICE = "rice"

class SexType(str, enum.Enum):
    MALE = "M"
    FEMALE = "F"

class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    SYNCED = "synced"
    CONFLICT = "conflict"
    DELETED = "deleted"

class ProjectStatus(str, enum.Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class OperationType(str, enum.Enum):
    LAND_PREPARATION = "land_preparation"
    PLANTING = "planting"
    FERTILIZATION = "fertilization"
    IRRIGATION = "irrigation"
    PEST_CONTROL = "pest_control"
    HARVESTING = "harvesting"
 
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    farm_name = Column(String)
    client_id = Column(String, index=True)
    sex = Column(Enum(SexType))
    location = Column(String)
    province = Column(String)
    city_municipality = Column(String)
    barangay = Column(String)
    mobile_number = Column(String, index=True)
    birthdate = Column(Date)
    location_lat = Column(Float)
    location_lon = Column(Float)
    email_verified = Column(Boolean, default=False)
    phone_verified = Column(Boolean, default=False)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)
    sync_status = Column(Enum(SyncStatus), default=SyncStatus.PENDING)
    deleted_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False)
    
    # Relationships
    farms = relationship("Farm", back_populates="owner")
    projects = relationship("CropProject", back_populates="owner")
    
    # FIX: foreign_keys must be INSIDE the relationship function
    financial_records = relationship(
        "FinancialRecord", 
        back_populates="owner",
        foreign_keys="FinancialRecord.owner_id"
    )
    
    # FIX: Corrected the typo "SchficeduledTask" to "ScheduledTask"
    scheduled_tasks = relationship("ScheduledTask", back_populates="user")

class Farm(Base):
    __tablename__ = "farms"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    area_hectares = Column(Float)
    soil_type = Column(String)
    client_id = Column(String, index=True)
    location = Column(String)
    province = Column(String)
    city_municipality = Column(String)
    barangay = Column(String)
    location_lat = Column(Float)
    location_lon = Column(Float)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)
    sync_status = Column(Enum(SyncStatus), default=SyncStatus.PENDING)
    deleted_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False)
    
    # Relationships
    owner = relationship("User", back_populates="farms")
    fields = relationship("Field", back_populates="farm")
    inventory = relationship("Inventory", back_populates="farm") 
    projects = relationship("CropProject", back_populates="farm")

class Field(Base):
    __tablename__ = "fields"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    area_hectares = Column(Float)
    crop_type = Column(Enum(CropType))
    crop_variety = Column(String)
    client_id = Column(String, index=True)
    planting_date = Column(DateTime)
    land_prep_start_date = Column(DateTime)
    expected_harvest_date = Column(DateTime)
    current_stage = Column(String, default="land_preparation")
    location_lat = Column(Float)
    location_lon = Column(Float)
    farm_id = Column(Integer, ForeignKey("farms.id"))
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)
    sync_status = Column(Enum(SyncStatus), default=SyncStatus.PENDING)
    deleted_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False)
    
    # Relationships
    farm = relationship("Farm", back_populates="fields")
    scheduled_tasks = relationship("ScheduledTask", back_populates="field")
    projects = relationship("CropProject", back_populates="field")

class Inventory(Base):
    __tablename__ = "inventory"
    
    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String, nullable=False)
    category = Column(String)  # seeds, fertilizer, equipment, etc.
    quantity = Column(Float)
    unit = Column(String)  # kg, liters, pieces, etc.
    unit_cost = Column(Float)
    client_id = Column(String, index=True)
    farm_id = Column(Integer, ForeignKey("farms.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)
    sync_status = Column(Enum(SyncStatus), default=SyncStatus.PENDING)
    deleted_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False)
    
    # Relationships
    farm = relationship("Farm", back_populates="inventory")

class CropProject(Base):
    __tablename__ = "crop_projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    crop_type = Column(Enum(CropType), nullable=False)
    crop_variety = Column(String)
    client_id = Column(String, index=True)
    budget_total = Column(Float, default=0)
    budget_remaining = Column(Float, default=0)
    income_total = Column(Float, default=0)
    expense_total = Column(Float, default=0)
    currency = Column(String, default="PHP")
    status = Column(Enum(ProjectStatus), default=ProjectStatus.PLANNED)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    notes = Column(Text)
    farm_id = Column(Integer, ForeignKey("farms.id"))
    field_id = Column(Integer, ForeignKey("fields.id"))
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)
    sync_status = Column(Enum(SyncStatus), default=SyncStatus.PENDING)
    deleted_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False)

    owner = relationship("User", back_populates="projects")
    farm = relationship("Farm", back_populates="projects")
    field = relationship("Field", back_populates="projects")
    financial_records = relationship("FinancialRecord", back_populates="project")
    scheduled_tasks = relationship("ScheduledTask", back_populates="project")

class FinancialRecord(Base):
    __tablename__ = "financial_records"
    
    id = Column(Integer, primary_key=True, index=True)
    transaction_type = Column(String, nullable=False)  # income or expense
    category = Column(String)  # labor, fertilizer, seeds, harvest_sale, etc.
    amount = Column(Float, nullable=False)
    currency = Column(String, default="PHP")
    description = Column(Text)
    client_id = Column(String, index=True)
    is_history = Column(Boolean, default=False)
    date = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    field_id = Column(Integer, ForeignKey("fields.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("crop_projects.id"), nullable=True)
    is_over_budget = Column(Boolean, default=False)
    over_budget_approved = Column(Boolean, default=False)
    budget_snapshot = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)
    sync_status = Column(Enum(SyncStatus), default=SyncStatus.PENDING)
    deleted_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey("users.id"))

    
    # Relationships
    owner = relationship("User", back_populates="financial_records",
                          foreign_keys=[owner_id])
    field = relationship("Field")
    project = relationship("CropProject", back_populates="financial_records")

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(Enum(OperationType), nullable=False)
    task_name = Column(String, nullable=False)
    description = Column(Text)
    scheduled_date = Column(DateTime, nullable=False)
    client_id = Column(String, index=True)
    original_scheduled_date = Column(DateTime)
    rescheduled_reason = Column(String)
    estimated_cost = Column(Float)
    actual_cost = Column(Float, nullable=True)
    status = Column(String, default="pending")  # pending, completed, cancelled, rescheduled
    requires_dry_weather = Column(Boolean, default=False)
    requires_network = Column(Boolean, default=False)
    priority = Column(Integer, default=1)  # 1-5 scale
    user_id = Column(Integer, ForeignKey("users.id"))
    field_id = Column(Integer, ForeignKey("fields.id"))
    project_id = Column(Integer, ForeignKey("crop_projects.id"))
    decision_tree_recommendation = Column(Boolean, default=False)
    weather_check_date = Column(DateTime)
    weather_status = Column(String)
    tomorrow_check_at = Column(DateTime)
    tomorrow_notification_sent_at = Column(DateTime)
    tomorrow_notification_type = Column(String)
    cycle_number = Column(Integer, nullable=True)  # 1=land prep, 2=planting-to-harvest
    cycle_day = Column(Integer, nullable=True)     # day offset within the cycle
    completed_at = Column(DateTime)
    confirmed_by_user = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime)
    sync_status = Column(Enum(SyncStatus), default=SyncStatus.PENDING)
    deleted_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False)
    
    # Relationships
    user = relationship("User", back_populates="scheduled_tasks")
    field = relationship("Field", back_populates="scheduled_tasks")
    project = relationship("CropProject", back_populates="scheduled_tasks")

class WeatherData(Base):
    __tablename__ = "weather_data"
    
    id = Column(Integer, primary_key=True, index=True)
    location_lat = Column(Float, nullable=False)
    location_lon = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)
    temperature_2m = Column(Float)
    relative_humidity_2m = Column(Float)
    precipitation = Column(Float)
    rain = Column(Float)
    snowfall = Column(Float)
    wind_speed_10m = Column(Float)
    weather_main = Column(String)
    soil_moisture_0_1cm = Column(Float)
    soil_moisture_1_3cm = Column(Float)
    soil_moisture_3_9cm = Column(Float)
    soil_moisture_9_27cm = Column(Float)
    soil_moisture_27_81cm = Column(Float)
    weather_code = Column(Integer)
    retrieved_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class WeatherCache(Base):
    __tablename__ = "weather_cache"
    id = Column(Integer, primary_key=True)
    farm_id = Column(Integer, ForeignKey("farms.id"))
    json_data = Column(String)  # We save the API result here as text
    updated_at = Column(DateTime, default=datetime.utcnow)

class DecisionTreeModel(Base):
    __tablename__ = "decision_tree_models"
    
    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String, nullable=False)
    crop_type = Column(Enum(CropType), nullable=False)
    accuracy = Column(Float)
    parameters = Column(Text)  # JSON string of model parameters
    feature_importance = Column(Text)  # JSON string
    trained_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class OtpCode(Base):
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String, nullable=False)  # email or sms
    destination = Column(String, nullable=False)  # email or phone
    code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    email_notifications = Column(Boolean, default=True)
    sms_notifications = Column(Boolean, default=False)
    push_notifications = Column(Boolean, default=False)
    marketing_notifications = Column(Boolean, default=False)
    language = Column(String, default="en")
    timezone = Column(String, default="Asia/Manila")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String, default="system")
    data = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    read_at = Column(DateTime, nullable=True)


class FCMDeviceToken(Base):
    __tablename__ = "fcm_device_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "token", name="uq_fcm_user_token"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String, nullable=False)
    device_type = Column(String, default="web")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
