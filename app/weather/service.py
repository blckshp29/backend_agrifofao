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
        self.base_url = getattr(config, "OPENWEATHER_BASE_URL", "https://api.openweathermap.org/data/2.5")
        self.api_key = getattr(config, "OPENWEATHER_API_KEY", "")
    
    def get_weather_forecast(self, db: Session, request: WeatherForecastRequest) -> Dict[str, Any]:
        """Fetch weather forecast from OpenWeatherMap API with Automatic DB Saving"""
        try:
            url = f"{self.base_url}/forecast"
            params = {
                "lat": request.latitude,
                "lon": request.longitude,
                "units": "metric",
                "appid": self.api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
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
        """Process raw OpenWeatherMap data into structured format"""
        processed_data = {
            "latitude": data.get("city", {}).get("coord", {}).get("lat"),
            "longitude": data.get("city", {}).get("coord", {}).get("lon"),
            "hourly": [],
            "hourly_data": [],
            "daily": [],
            "daily_data": [],
            "retrieved_at": datetime.utcnow().isoformat()
        }

        lst = data.get("list", [])
        daily_map: Dict[str, Dict[str, Any]] = {}

        for entry in lst:
            dt = datetime.utcfromtimestamp(entry.get("dt"))
            date_key = dt.strftime("%Y-%m-%d")
            main = entry.get("main", {})
            rain = entry.get("rain", {}).get("3h", 0.0)
            snow = entry.get("snow", {}).get("3h", 0.0)
            wind = entry.get("wind", {})
            weather_items = entry.get("weather", [])
            weather_main = weather_items[0].get("main") if weather_items else None
            weather_code = weather_items[0].get("id") if weather_items else None

            hourly_entry = {
                "time": dt.isoformat(),
                "temperature_2m": main.get("temp"),
                "relative_humidity_2m": main.get("humidity"),
                "precipitation": rain,
                "rain": rain,
                "snowfall": snow,
                "wind_speed_10m": wind.get("speed"),
                "weather_main": weather_main,
                "weather_code": weather_code,
                "soil_moisture_0_1cm": None
            }
            processed_data["hourly"].append(hourly_entry)
            processed_data["hourly_data"].append(hourly_entry)

            day = daily_map.setdefault(date_key, {
                "date": date_key,
                "temperature_2m_max": None,
                "temperature_2m_min": None,
                "precipitation_sum": 0.0,
                "wind_speed_max": 0.0,
                "weather_main": weather_main,
                "weather_code": weather_code
            })
            temp = main.get("temp")
            if temp is not None:
                day["temperature_2m_max"] = temp if day["temperature_2m_max"] is None else max(day["temperature_2m_max"], temp)
                day["temperature_2m_min"] = temp if day["temperature_2m_min"] is None else min(day["temperature_2m_min"], temp)
            day["precipitation_sum"] += rain
            wind_speed = wind.get("speed", 0.0) or 0.0
            day["wind_speed_max"] = max(day["wind_speed_max"], wind_speed)

        processed_data["daily"] = list(daily_map.values())
        processed_data["daily_data"] = processed_data["daily"]

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
                wind_speed_10m=entry.get("wind_speed_10m"),
                weather_main=entry.get("weather_main"),
                soil_moisture_0_1cm=entry.get("soil_moisture_0_1cm"),
                soil_moisture_1_3cm=entry.get("soil_moisture_1_3cm"),
                soil_moisture_3_9cm=entry.get("soil_moisture_3_9cm"),
                soil_moisture_9_27cm=entry.get("soil_moisture_9_27cm"),
                soil_moisture_27_81cm=entry.get("soil_moisture_27_81cm"),
                weather_code=entry.get("weather_code"),
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
            "daily": [],
            "daily_data": [],
            "retrieved_at": records[0].date.isoformat(),
            "is_offline_data": True
        }

        daily_map: Dict[str, Dict[str, Any]] = {}

        for r in records:
            date_key = r.date.strftime("%Y-%m-%d")
            hourly_entry = {
                "time": r.date.isoformat(),
                "temperature_2m": r.temperature_2m,
                "precipitation": r.precipitation,
                "rain": r.rain,
                "snowfall": r.snowfall,
                "relative_humidity_2m": r.relative_humidity_2m,
                "soil_moisture_0_1cm": r.soil_moisture_0_1cm,
                "soil_moisture_1_3cm": r.soil_moisture_1_3cm,
                "soil_moisture_3_9cm": r.soil_moisture_3_9cm,
                "soil_moisture_9_27cm": r.soil_moisture_9_27cm,
                "soil_moisture_27_81cm": r.soil_moisture_27_81cm,
                "weather_main": r.weather_main,
                "weather_code": r.weather_code,
                "wind_speed_10m": r.wind_speed_10m,
            }
            fallback_data["hourly"].append(hourly_entry)
            fallback_data["hourly_data"].append(hourly_entry)

            day = daily_map.setdefault(date_key, {
                "date": date_key,
                "temperature_2m_max": None,
                "temperature_2m_min": None,
                "precipitation_sum": 0.0,
                "wind_speed_max": 0.0,
                "weather_main": r.weather_main,
                "weather_code": r.weather_code,
            })

            temp = r.temperature_2m
            if temp is not None:
                day["temperature_2m_max"] = temp if day["temperature_2m_max"] is None else max(day["temperature_2m_max"], temp)
                day["temperature_2m_min"] = temp if day["temperature_2m_min"] is None else min(day["temperature_2m_min"], temp)

            precipitation = r.precipitation or 0.0
            day["precipitation_sum"] += precipitation
            wind_speed = r.wind_speed_10m or 0.0
            day["wind_speed_max"] = max(day["wind_speed_max"], wind_speed)

        fallback_data["hourly"].sort(key=lambda entry: entry["time"])
        fallback_data["hourly_data"] = fallback_data["hourly"]
        fallback_data["daily"] = [daily_map[key] for key in sorted(daily_map.keys())]
        fallback_data["daily_data"] = fallback_data["daily"]

        return fallback_data

    def check_weather_suitability(self, weather_data: Dict, date: datetime, requires_dry_weather: bool = False) -> Dict[str, Any]:
        """Check if weather conditions are suitable for farming operation"""
        # Find weather entry for specific date
        target_date = date.strftime("%Y-%m-%d")
        
        suitability = {
            "is_suitable": True,
            "reasons": [],
            "risks": [],
            "recommended_delay_days": 0
        }
        
        for daily_entry in weather_data.get("daily", []):
            if daily_entry.get("date") == target_date:
                # Check precipitation
                precipitation = daily_entry.get("precipitation_sum", 0)
                wind_speed = daily_entry.get("wind_speed_max", 0) or 0
                
                if requires_dry_weather and precipitation > 0:
                    suitability["is_suitable"] = False
                    suitability["reasons"].append(f"Rain expected ({precipitation} mm)")
                    suitability["risks"].append("Chemical runoff risk")
                    suitability["recommended_delay_days"] = max(suitability["recommended_delay_days"], 1)

                # Decision-tree veto behavior for severe weather
                if precipitation >= 10:
                    suitability["is_suitable"] = False
                    suitability["reasons"].append("Heavy rain forecast")
                    suitability["risks"].append("Input loss and nutrient washout risk")
                    suitability["recommended_delay_days"] = max(suitability["recommended_delay_days"], 2)
                if wind_speed >= 25:
                    suitability["is_suitable"] = False
                    suitability["reasons"].append("High wind forecast")
                    suitability["risks"].append("Spray drift risk")
                    suitability["recommended_delay_days"] = max(suitability["recommended_delay_days"], 2)
                
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
