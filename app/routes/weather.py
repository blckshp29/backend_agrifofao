from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import httpx

from ..database import get_db
from ..models import User
from ..weather.service import WeatherService
from ..schemas import WeatherForecastRequest, WeatherForecastResponse
from .auth import get_current_user
from config import config

router = APIRouter()
weather_service = WeatherService()

@router.post("/weather/forecast", response_model=WeatherForecastResponse)
async def get_weather_forecast(
    request: WeatherForecastRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetches real data from Open-Meteo and automatically saves it to DB"""
    try:
        # The service now handles fetching AND saving internally
        forecast = weather_service.get_weather_forecast(db, request)
        return forecast
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/weather/suitability")
async def get_farm_weather(lat: float, lon: float):
    """Quick real-time check for current conditions"""
    async with httpx.AsyncClient() as client:
        try:
            params = {
                "lat": lat,
                "lon": lon,
                "units": "metric",
                "appid": config.OPENWEATHER_API_KEY
            }
            response = await client.get(f"{config.OPENWEATHER_BASE_URL}/weather", params=params)
            response.raise_for_status()
            return response.json()
        except Exception:
            raise HTTPException(status_code=503, detail="Weather service unreachable")

@router.get("/optimal-windows")
def get_optimal_windows(
    farm_id: int, 
    requires_dry_weather: bool = False,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 1. Find the farm to get its Lat/Lon
    from app.models import Farm
    farm = db.query(Farm).filter(Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    # 2. Try to get weather (Service handles the Offline Fallback automatically now)
    try:
        # Create a mock request object for your service
        from app.schemas import WeatherForecastRequest
        weather_request = WeatherForecastRequest(
            latitude=farm.location_lat,
            longitude=farm.location_lon,
            days=5
        )
        
        # This calls your method that has the try/except internet fallback
        weather_data = weather_service.get_weather_forecast(db, weather_request)
        
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Weather service unavailable: {str(e)}")

    # 3. Run the Decision Tree
    start_date = datetime.now()
    end_date = start_date + timedelta(days=7)
    
    # This processes the data (Live or Offline) through your logic
    results = weather_service.get_optimal_weather_window(
        weather_data, start_date, end_date, requires_dry_weather
    )
    
    return results
