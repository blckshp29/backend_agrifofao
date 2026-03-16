import app.models
import asyncio
import logging
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta  # Added datetime here
from typing import List
from contextlib import asynccontextmanager # Added for lifespan
from . import models  # 1. This "registers" the models with Base

from .database import get_db, init_db, Base, engine, SessionLocal
from .firebase import initialize_firebase
from .models import User
from .schemas import UserCreate, User as UserSchema, Token, UserLogin
from .routes import auth, farm, financial, scheduling, weather, sync, location, profile, notifications
from .scheduling.service import SchedulingService


logger = logging.getLogger(__name__)
tomorrow_notification_service = SchedulingService()


async def tomorrow_notification_loop():
    while True:
        db = SessionLocal()
        try:
            results = tomorrow_notification_service.process_tomorrow_task_notifications_for_all_users(db)
            sent_count = sum(len(items) for items in results.values())
            if sent_count:
                logger.info("Tomorrow notification scan processed %s task notifications.", sent_count)
        except Exception as exc:
            logger.warning("Tomorrow notification scan failed: %s", exc)
        finally:
            db.close()

        await asyncio.sleep(60 * 60 * 6)

# 1. Trigger the database initialization
# This creates the .db file and the tables if they don't exist yet

Base.metadata.create_all(bind=engine)
# 2. Initialize the FastAPI app
app = FastAPI(title="FOFAO Backend API")

# --- DATABASE INITIALIZATION ---
# Using lifespan is the modern way to handle startup/shutdown tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs when the app starts
    background_task = None
    try:
        initialize_firebase()
    except Exception as exc:
        logger.warning("Firebase initialization skipped: %s", exc)
    print("Initializing database tables...")
    init_db()
    background_task = asyncio.create_task(tomorrow_notification_loop())
    yield
    # This runs when the app shuts down
    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass
    print("Shutting down...")

# Create FastAPI app with lifespan
app = FastAPI(
    title="Agricultural Operations Financial Optimization System",
    description="Decision Tree-based Financial Optimization System for Agricultural Operations",
    version="1.0.0",
    lifespan=lifespan # Connect the lifespan here
)

# --- MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://zaiden-trollopy-unmanually.ngrok-free.dev",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTERS ---
app.include_router(auth.router, prefix="/api/v1", tags=["authentication"])
app.include_router(farm.router, prefix="/api/v1", tags=["farms"])
app.include_router(financial.router, prefix="/api/v1", tags=["financial"])
app.include_router(scheduling.router, prefix="/api/v1", tags=["scheduling"])
app.include_router(weather.router, prefix="/api/v1", tags=["weather"])
app.include_router(sync.router, prefix="/api/v1", tags=["sync"])
app.include_router(location.router, prefix="/api/v1", tags=["location"])
app.include_router(profile.router, prefix="/api/v1", tags=["profile"])
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])

# --- ENDPOINTS ---

@app.get("/")
def read_root():
    return {
        "message": "Agricultural Operations Financial Optimization System",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/api/v1/health")
def health_check():
    # Fixed: now using the imported datetime
    return {
        "status": "healthy", 
        "timestamp": datetime.utcnow()
    }
