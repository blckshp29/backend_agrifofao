import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Farm, User
from .auth import get_current_user
from config import config

router = APIRouter()

async def _forward_geocode_location(
    farm_id: int,
    province: str,
    city: str,
    barangay: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    farm = db.query(Farm).filter(
        Farm.id == farm_id,
        Farm.user_id == current_user.id
    ).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    query = ", ".join([p for p in [barangay, city, province] if p])
    params = {
        "q": query,
        "limit": 1,
        "appid": config.OPENWEATHER_API_KEY
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{config.OPENWEATHER_GEO_BASE_URL}/direct", params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Forward geocoding failed: {str(e)}")

    if not data:
        raise HTTPException(status_code=404, detail="No location found for address")

    place = data[0]
    lat = place.get("lat")
    lon = place.get("lon")

    farm.location_lat = lat
    farm.location_lon = lon
    farm.province = province
    farm.city_municipality = city
    farm.barangay = barangay
    db.commit()
    db.refresh(farm)

    return {
        "latitude": lat,
        "longitude": lon,
        "province": province,
        "city": city,
        "barangay": barangay,
        "raw": place
    }

@router.post("/location/forward")
async def forward_geocode_location_post(
    farm_id: int,
    province: str,
    city: str,
    barangay: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await _forward_geocode_location(farm_id, province, city, barangay, db, current_user)

@router.get("/location/forward")
async def forward_geocode_location_get(
    farm_id: int,
    province: str,
    city: str,
    barangay: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await _forward_geocode_location(farm_id, province, city, barangay, db, current_user)
@router.post("/location/reverse")
async def reverse_geocode_location(
    farm_id: int,
    lat: float,
    lon: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    farm = db.query(Farm).filter(
        Farm.id == farm_id,
        Farm.user_id == current_user.id
    ).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    params = {
        "lat": lat,
        "lon": lon,
        "limit": 1,
        "appid": config.OPENWEATHER_API_KEY
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{config.OPENWEATHER_GEO_BASE_URL}/reverse", params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Reverse geocoding failed: {str(e)}")

    if not data:
        raise HTTPException(status_code=404, detail="No location found for coordinates")

    place = data[0]
    city = place.get("name")
    province = place.get("state")

    farm.location_lat = lat
    farm.location_lon = lon
    farm.city_municipality = city
    farm.province = province
    db.commit()
    db.refresh(farm)

    address = ", ".join([p for p in [city, province] if p])
    return {
        "farm_id": farm_id,
        "city_municipality": city,
        "province": province,
        "address": address
    }
