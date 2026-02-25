import importlib
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import config

# 1. Define the Base here. 
# Your models.py should import this Base from here.
Base = declarative_base() 

# 2. Create SQLite database engine
engine = create_engine(
    config.DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in config.DATABASE_URL else {}
)

# 3. Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Dependency
def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 5. Create tables
def init_db():
    # 1. Force the import of ALL models here
    from .models import (
        User,
        Farm,
        Field,
        Inventory,
        FinancialRecord,
        ScheduledTask,
        WeatherData,
        WeatherCache,
        DecisionTreeModel,
        CropProject,
        OtpCode,
    )
    from .database import engine, Base
    
    # 2. This command only creates tables that DON'T exist yet
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Done!")

    # Verification check
    import sqlalchemy
    inspector = sqlalchemy.inspect(engine)
    print(f"Tables currently in DB: {inspector.get_table_names()}")
