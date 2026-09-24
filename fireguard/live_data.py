"""Live, real-data sources: NASA FIRMS (satellite hotspots), Open-Meteo air quality and elevation.

Nothing in this module ever fabricates a value. When a source cannot be reached, is not configured,
or rejects the request, the result carries an explicit status and an empty payload.
"""
from __future__ import annotations

import csv
import io
import logging
import time
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any

import httpx

from fireguard.config import settings

log = logging.getLogger(__name__)

FIRMS_AREA_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_MAX_DAYS = 5          # documented range: 1..5
FIRMS_MAX_RETURNED = 500    # cap what is pushed to the dashboard
FIRMS_STALE_AFTER_S = 3 * 3600  # keep last good FIRMS data (flagged STALE) for at most 3 h if a refresh fails

_firms_cache: dict[str, Any] = {}


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class FirmsError(Exception):
    """Raised when FIRMS answers with something that is not a CSV of detections."""


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(a))


def firms_bbox(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """(west, south, east, north) box around a point. Clamped to valid ranges (no antimeridian wrap)."""
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(cos(radians(lat)), 0.01))
    return (max(-180.0, lon - dlon), max(-90.0, lat - dlat), min(180.0, lon + dlon), min(90.0, lat + dlat))


def _observed_at(acq_date: str | None, acq_time: str | None) -> str | None:
    """FIRMS acq_date is YYYY-MM-DD and acq_time is HHMM, both UTC."""
    try:
        hhmm = str(acq_time or "").zfill(4)
        return datetime.strptime(f"{acq_date} {hhmm}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def parse_firms_csv(text: str, source: str, lat: float | None = None, lon: float | None = None) -> list[dict[str, Any]]:
    """Parse a FIRMS area CSV. Raises FirmsError if the body is not a detections CSV
    (FIRMS reports bad keys and quota problems as plain text, sometimes with HTTP 200)."""
    body = (text or "").strip()
    if not body:
        raise FirmsError("empty response from FIRMS")
    first = body.splitlines()[0].lower()
    if "latitude" not in first or "longitude" not in first:
        raise FirmsError(body[:160])
    now = datetime.now(timezone.utc)
    fires: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(body)):
        try:
            la, lo = float(row["latitude"]), float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        observed = _observed_at(row.get("acq_date"), row.get("acq_time"))
        age_min = round((now - datetime.fromisoformat(observed)).total_seconds() / 60, 1) if observed else None
        fires.append({
            "event_id": f"firms-{source}-{row.get('acq_date')}-{row.get('acq_time')}-{la:.4f}-{lo:.4f}",
            "latitude": la, "longitude": lo,
            "confidence": row.get("confidence"),
            "frp": row.get("frp"),
            "brightness": row.get("bright_ti4") or row.get("brightness"),
            "daynight": row.get("daynight"),
            "satellite": row.get("satellite"),
            "instrument": row.get("instrument"),
            "acq_date": row.get("acq_date"), "acq_time": row.get("acq_time"),
            "observed_at": observed, "age_minutes": age_min,
            "distance_km": round(haversine_km(lat, lon, la, lo), 1) if lat is not None and lon is not None else None,
            "firms_source": source,
            "source": "NASA_FIRMS", "status": "SATELLITE_OBSERVATION",
        })
    return fires


def _firms_sources() -> list[str]:
    return [s.strip() for s in settings.firms_source.split(",") if s.strip()]


def _classify_firms_error(message: str) -> str:
    m = message.lower()
    if "invalid" in m and "key" in m:
        return "INVALID_KEY"
    if "exceed" in m or "limit" in m or "too many" in m:
        return "RATE_LIMITED"
    return "UNAVAILABLE"


async def fetch_firms(lat: float | None = None, lon: float | None = None, client: httpx.AsyncClient | None = None, use_cache: bool = True) -> dict[str, Any]:
    if not settings.firms_map_key:
        return {"fires": [], "satellite_status": "CONFIG_REQUIRED", "satellite_source": "NASA_FIRMS",
                "satellite_message": "Set FIREGUARD_FIRMS_MAP_KEY (free key: https://firms.modaps.eosdis.nasa.gov/api/area/).",
                "satellite_timestamp": ts()}

    if lat is not None and lon is not None:
        area = ",".join(f"{v:.4f}" for v in firms_bbox(lat, lon, settings.firms_radius_km))
        scope = {"bbox": area, "radius_km": settings.firms_radius_km}
    else:
        area = settings.firms_region
        scope = {"bbox": area, "radius_km": None}
    days = min(max(int(settings.firms_days), 1), FIRMS_MAX_DAYS)
    sources = _firms_sources()
    cache_key = f"{area}|{days}|{','.join(sources)}"

    cached = _firms_cache.get("value") if _firms_cache.get("key") == cache_key else None
    if use_cache and cached and time.monotonic() - _firms_cache["at"] < max(30, settings.firms_poll_seconds):
        return cached

    own = client is None
    client = client or httpx.AsyncClient(timeout=settings.environment_timeout_seconds)
    per_source: dict[str, dict[str, Any]] = {}
    merged: dict[str, dict[str, Any]] = {}
    try:
        for src in sources:
            url = f"{FIRMS_AREA_URL}/{settings.firms_map_key}/{src}/{area}/{days}"
            try:
                r = await client.get(url)
                text = r.text
                if r.status_code >= 400 and "latitude" not in text[:200].lower():
                    raise FirmsError(text.strip()[:160] or f"HTTP {r.status_code}")
                found = parse_firms_csv(text, src, lat, lon)
                per_source[src] = {"status": "LIVE", "count": len(found)}
                for f in found:
                    merged[f["event_id"]] = f
            except FirmsError as e:
                # never log the URL: it contains the MAP_KEY
                per_source[src] = {"status": _classify_firms_error(str(e)), "message": str(e)[:160]}
            except Exception as e:  # network/timeout/etc.
                per_source[src] = {"status": "UNAVAILABLE", "message": e.__class__.__name__}
    finally:
        if own:
            await client.aclose()

    ok = [s for s, v in per_source.items() if v["status"] == "LIVE"]
    fires = sorted(merged.values(), key=lambda f: (f["distance_km"] if f["distance_km"] is not None else 0, f.get("age_minutes") or 0))
    total = len(fires)
    fires = fires[:FIRMS_MAX_RETURNED]

    if ok:
        status = "LIVE" if len(ok) == len(sources) else "PARTIAL"
        result = {"fires": fires, "satellite_status": status, "satellite_source": "NASA_FIRMS", "satellite_timestamp": ts(),
                  "satellite_message": None if status == "LIVE" else "Some FIRMS sources failed; see per_source.",
                  "sources": sources, "per_source": per_source, "total_detections": total, "days": days, **scope}
        _firms_cache.update(key=cache_key, at=time.monotonic(), value=result)
        return result

    # Every source failed. Prefer real-but-older data (clearly flagged) over erasing what we know.
    worst = next(iter(per_source.values()), {"status": "UNAVAILABLE", "message": "no sources configured"})
    status = worst["status"]
    log.warning("FIRMS unavailable: %s", {k: v["status"] for k, v in per_source.items()})
    if cached and time.monotonic() - _firms_cache["at"] < FIRMS_STALE_AFTER_S and status != "INVALID_KEY":
        return {**cached, "satellite_status": "STALE", "satellite_message": f"Refresh failed ({status}); showing last successful FIRMS data.", "per_source": per_source}
    return {"fires": [], "satellite_status": status, "satellite_source": "NASA_FIRMS", "satellite_timestamp": ts(),
            "satellite_message": worst.get("message"), "sources": sources, "per_source": per_source, **scope}


async def fetch_air_quality(lat: float, lon: float):
    try:
        async with httpx.AsyncClient(timeout=settings.environment_timeout_seconds) as c:
            r = await c.get(settings.air_quality_api_url, params={"latitude": lat, "longitude": lon, "current": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide", "timezone": "UTC"}); r.raise_for_status(); cur = r.json().get("current", {})
        return {"pm25": cur.get("pm2_5"), "pm10": cur.get("pm10"), "air_quality_status": "LIVE", "air_quality_source": "OPEN_METEO_AIR_QUALITY", "air_quality_timestamp": cur.get("time") or ts()}
    except Exception as e:
        log.warning("air quality failed: %s", e.__class__.__name__); return {"pm25": None, "pm10": None, "air_quality_status": "UNAVAILABLE", "air_quality_source": "OPEN_METEO_AIR_QUALITY", "air_quality_timestamp": ts()}


async def fetch_elevation(lat: float, lon: float):
    try:
        async with httpx.AsyncClient(timeout=settings.environment_timeout_seconds) as c:
            r = await c.get(settings.elevation_api_url, params={"latitude": lat, "longitude": lon}); r.raise_for_status(); e = r.json().get("elevation", [])
        return {"elevation_m": e[0] if e else None, "terrain_status": "LIVE" if e else "UNAVAILABLE", "terrain_source": "OPEN_METEO_ELEVATION", "terrain_timestamp": ts()}
    except Exception as e:
        log.warning("elevation failed: %s", e.__class__.__name__); return {"elevation_m": None, "terrain_status": "UNAVAILABLE", "terrain_source": "OPEN_METEO_ELEVATION", "terrain_timestamp": ts()}


async def collect_live_sources(lat, lon, include_satellite: bool = True):
    result: dict[str, Any] = {"timestamp": ts()}
    if include_satellite:
        result["satellite"] = await fetch_firms(lat, lon)
    if lat is not None and lon is not None:
        result["air_quality"] = await fetch_air_quality(lat, lon); result["terrain"] = await fetch_elevation(lat, lon)
    return result
