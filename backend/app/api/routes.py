from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import config
from app.prediction import service
from app.prediction.service import InputError
from app.sources import gbif, open_meteo
from app.species import SPECIES

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health():
    return {"status": "ok", "today": service.today_pl().isoformat(), "gbif": gbif.status()}


@router.get("/species")
async def species():
    return {
        "species": [{"id": c.id, "name_pl": c.name_pl, "name_short": c.name_short,
                     "latin": c.latin} for c in SPECIES.values()],
        "today": service.today_pl().isoformat(),
        "forecast_days": config.FORECAST_DAYS,
    }


@router.get("/predictions/bbox")
async def predictions_bbox(
    west: float = Query(..., ge=-180, le=180), south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180), north: float = Query(..., ge=-90, le=90),
    zoom: float = Query(10, ge=0, le=24), species: str = "all", date: str | None = None,
):
    try:
        return await service.predict_bbox(west, south, east, north, zoom, species, date)
    except InputError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/prediction")
async def prediction(
    lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
    species: str = "all", date: str | None = None,
):
    try:
        return await service.predict_point(lat, lon, species, date)
    except InputError as e:
        raise HTTPException(422, str(e)) from e


class WeatherUpload(BaseModel):
    points: list[tuple[float, float]]
    data: Any


@router.post("/weather")
async def upload_weather(body: WeatherUpload):
    """Browser fallback: Open-Meteo data fetched by the client when the server is rate limited."""
    try:
        stored = open_meteo.ingest(body.points, body.data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"stored": stored}


if config.DEBUG:
    @router.get("/debug/features")
    async def debug_features(lat: float, lon: float, date: str | None = None):
        from app.sources import bdl, open_meteo
        from app.prediction import grid
        target, _ = service.resolve_date(date)
        forest = (await bdl.query_points([(lat, lon)]))[0]
        wp = grid.snap_weather(lat, lon, grid.LADDER[0])
        weather, errors = await open_meteo.fetch_weather([wp])
        wf = service._features_for(weather.get(wp), target) or {}
        wf = {k: v for k, v in wf.items() if not isinstance(v, list)}
        return {"forest": forest.__dict__ if forest else None, "weather_point": wp,
                "weather_features": wf, "errors": errors}
