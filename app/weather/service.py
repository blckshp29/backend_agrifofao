import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
import json

from config import config
from ..models import WeatherData
from ..schemas import WeatherForecastRequest, WeatherForecastResponse

class WeatherService:
    def __init__(self):
        # Fallback to public URL if config is missing it
        self.base_url = getattr(config, "OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1")
    
    def get_weather_forecast(self, db: Session, request: WeatherForecastRequest) -> Dict[str, Any]:
        """Fetch weather forecast from Open-Meteo API with Automatic DB Saving"""
        try:
            url = f"{self.base_url}/forecast"
            
            # Using specific hourly params for farming
            params = {
                "latitude": request.latitude,
                "longitude": request.longitude,
                "hourly": "temperature_2m,relative_humidity_2m,precipitation,rain,soil_moisture_0_1cm",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                "forecast_days": request.days,
                "timezone": "auto"
            }
            
            response = requests.get(url, params=params, timeout=10, verify=False)
            response.raise_for_status()
            data = response.json()
            
            # Process the data
            forecast = self._process_weather_data(data, request)
            
            # --- NEW: AUTO-SAVE FOR OFFLINE USE ---
            # This ensures Prototype 1's "Offline logic" actually has data to read
            self.save_weather_data(db, forecast, request.latitude, request.longitude)
            
            return forecast
            
        except Exception as e:
            # --- NEW: ROBUST ERROR HANDLING ---
            # If the internet is down, immediately try to get cached data
            print(f"Online fetch failed: {e}. Attempting offline fallback...")
            cached_data = self.get_last_saved_weather(db, request.latitude, request.longitude)
            if cached_data:
                return cached_data
            raise Exception(f"Weather data unavailable online and offline: {str(e)}")
    
    def _process_weather_data(self, data: Dict, request: WeatherForecastRequest) -> Dict[str, Any]:
        """Process raw weather data into structured format"""
        processed_data = {
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "hourly": [],
            "hourly_data": [],
            "daily": [],
            "daily_data": [],
            "retrieved_at": datetime.utcnow().isoformat()
        }
        
        # Process hourly data
        hourly = data.get("hourly", {})
        time_list = hourly.get("time", [])
        
        if time_list:
            for i in range(len(time_list)):
                hourly_entry = {"time": time_list[i]}
                for param in config.WEATHER_PARAMS:
                    if param in hourly:
                        hourly_entry[param] = hourly[param][i] if i < len(hourly[param]) else None
                processed_data["hourly"].append(hourly_entry)
                processed_data["hourly_data"].append(hourly_entry)
        
        # Process daily data
        daily = data.get("daily", {})
        daily_time_list = daily.get("time", [])
        
        if daily_time_list:
            for i in range(len(daily_time_list)):
                daily_entry = {"date": daily_time_list[i]}
                for key in daily.keys():
                    if key != "time":
                        daily_entry[key] = daily[key][i] if i < len(daily[key]) else None
                processed_data["daily"].append(daily_entry)
                processed_data["daily_data"].append(daily_entry)
        
        return processed_data
    
    def save_weather_data(self, db: Session, weather_data: Dict, location_lat: float, location_lon: float):
        """Save weather data to database"""
        hourly_data = weather_data.get("hourly", [])
        
        for entry in hourly_data:
            weather_record = WeatherData(
                location_lat=location_lat,
                location_lon=location_lon,
                date=datetime.fromisoformat(entry["time"]),
                temperature_2m=entry.get("temperature_2m"),
                relative_humidity_2m=entry.get("relative_humidity_2m"),
                precipitation=entry.get("precipitation"),
                rain=entry.get("rain"),
                snowfall=entry.get("snowfall"),
                soil_moisture_0_1cm=entry.get("soil_moisture_0_1cm"),
                soil_moisture_1_3cm=entry.get("soil_moisture_1_3cm"),
                soil_moisture_3_9cm=entry.get("soil_moisture_3_9cm"),
                soil_moisture_9_27cm=entry.get("soil_moisture_9_27cm"),
                soil_moisture_27_81cm=entry.get("soil_moisture_27_81cm")
            )
            db.add(weather_record)
        
        db.commit()
    def get_last_saved_weather(self, db: Session, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent saved weather data for offline fallback"""
        from sqlalchemy import desc
        
        # Get the latest 24 hourly records for this location
        records = db.query(WeatherData).filter(
            WeatherData.location_lat == lat,
            WeatherData.location_lon == lon
        ).order_by(desc(WeatherData.date)).limit(24).all()

        if not records:
            return None

        # Reconstruct a structure that matches what your other methods expect
        # This is the "bridge" that makes the rest of your service think it's online
        fallback_data = {
            "latitude": lat,
            "longitude": lon,
            "hourly": [],
            "hourly_data": [],
            "daily": [], # You could reconstruct daily from hourly if needed
            "daily_data": [],
            "retrieved_at": records[0].date.isoformat(),
            "is_offline_data": True
        }

        for r in records:
            hourly_entry = {
                "time": r.date.isoformat(),
                "temperature_2m": r.temperature_2m,
                "precipitation": r.precipitation,
                # ... add other fields you need ...
            }
            fallback_data["hourly"].append(hourly_entry)
            fallback_data["hourly_data"].append(hourly_entry)
            
        return fallback_data

    def check_weather_suitability(self, weather_data: Dict, date: datetime, requires_dry_weather: bool = False) -> Dict[str, Any]:
        """Check if weather conditions are suitable for farming operation"""
        # Find weather entry for specific date
        target_date = date.strftime("%Y-%m-%d")
        
        suitability = {
            "is_suitable": True,
            "reasons": [],
            "risks": []
        }
        
        for daily_entry in weather_data.get("daily", []):
            if daily_entry.get("date") == target_date:
                # Check precipitation
                precipitation = daily_entry.get("precipitation_sum", 0)
                
                if requires_dry_weather and precipitation > 0:
                    suitability["is_suitable"] = False
                    suitability["reasons"].append(f"Rain expected ({precipitation} mm)")
                    suitability["risks"].append("Chemical runoff risk")
                
                # Check temperature range
                temp_max = daily_entry.get("temperature_2m_max")
                temp_min = daily_entry.get("temperature_2m_min")
                
                if temp_max and temp_max > 35:  # Too hot
                    suitability["risks"].append("High temperature stress")
                if temp_min and temp_min < 10:  # Too cold
                    suitability["risks"].append("Low temperature stress")
                
                break
        
        return suitability
    
    def get_optimal_weather_window(self, weather_data: Dict, start_date: datetime, 
                                   end_date: datetime, requires_dry_weather: bool = False) -> List[Dict]:
        """Find optimal weather windows within date range"""
        optimal_windows = []
        
        for daily_entry in weather_data.get("daily", []):
            entry_date = datetime.fromisoformat(daily_entry["date"])
            
            if start_date <= entry_date <= end_date:
                precipitation = daily_entry.get("precipitation_sum", 0)
                temp_max = daily_entry.get("temperature_2m_max")
                temp_min = daily_entry.get("temperature_2m_min")
                
                # Calculate weather score (higher is better)
                weather_score = 100
                
                if requires_dry_weather:
                    if precipitation > 0:
                        weather_score -= precipitation * 20  # Penalize rain
                else:
                    if precipitation > 10:  # Too much rain even if not requiring dry weather
                        weather_score -= 30
                
                # Temperature optimization
                if temp_max and 20 <= temp_max <= 30:  # Ideal range
                    weather_score += 10
                elif temp_max and (temp_max < 15 or temp_max > 35):
                    weather_score -= 20
                
                optimal_windows.append({
                    "date": entry_date,
                    "weather_score": max(0, weather_score),
                    "precipitation": precipitation,
                    "temperature_max": temp_max,
                    "temperature_min": temp_min,
                    "is_suitable": weather_score >= 70  # Threshold
                })
        
        # Sort by weather score descending
        optimal_windows.sort(key=lambda x: x["weather_score"], reverse=True)
        
        return optimal_windows
    
    def predict_suitability(self, temp: float, rain: float, wind_speed: float, humidity: int):
        """
        Decision Tree Algorithm Implementation
        Returns a dictionary with 'score' (0-3) and 'advice'.
        """
        # --- LEVEL 1: ROOT NODES (The Vetoes) ---
        if rain > 0.5:
            return {"level": 0, "status": "UNSUITABLE", "advice": "Rain detected. Risk of washout."}
        
        if wind_speed > 25:
            return {"level": 0, "status": "UNSUITABLE", "advice": "High wind. Risk of spray drift."}

        # --- LEVEL 2: ENVIRONMENTAL STRESS ---
        if temp > 35 or temp < 5:
            return {"level": 1, "status": "RISKY", "advice": "Extreme temperature. Crop stress likely."}

        # --- LEVEL 3: THE OPTIMAL BRANCH ---
        # 18°C to 28°C is generally the metabolic sweet spot for crops
        if 18 <= temp <= 28:
            if 40 <= humidity <= 70 and wind_speed < 12:
                return {"level": 3, "status": "OPTIMAL", "advice": "Ideal conditions for maximum efficacy."}
            
            return {"level": 2, "status": "GOOD", "advice": "Safe conditions, though not perfectly ideal."}

        # --- LEVEL 4: DEFAULT (SAFE BUT NOT PERFECT) ---
        return {"level": 1, "status": "MARGINAL", "advice": "Conditions are safe but efficacy may be reduced."}
