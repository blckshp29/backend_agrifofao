import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    # 1. Database
    DATABASE_URL = os.getenv(
        "DATABASE_URL", 
        f"sqlite:///{os.path.join(BASE_DIR, 'agricultural_operations.db')}"
    )
    
    # 2. OpenWeatherMap Settings
    OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"
    OPENWEATHER_GEO_BASE_URL = "https://api.openweathermap.org/geo/1.0"
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
    
    # These match the columns in your WeatherData model
    WEATHER_PARAMS = [
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "rain",
        "soil_moisture_0_1cm",
        "soil_moisture_1_3cm",
        "soil_moisture_3_9cm"
    ]
    
    # 3. Security (Essential for Prototype 2)
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 Day
    
    # 4. API Settings
    API_V1_PREFIX = "/api/v1"

config = Config()
