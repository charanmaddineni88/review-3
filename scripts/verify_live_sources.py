"""Hit the REAL upstream servers using your .env and report PASS/FAIL: python scripts/verify_live_sources.py"""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fireguard.config import settings
from fireguard.environment import NWSProvider, OpenMeteoProvider
from fireguard.live_data import fetch_air_quality, fetch_elevation, fetch_firms

async def main() -> int:
    lat, lon = settings.latitude, settings.longitude
    if lat is None or lon is None:
        print("FAIL  set FIREGUARD_LATITUDE / FIREGUARD_LONGITUDE"); return 1
    bad = 0
    def show(name, ok, detail, required=True):
        nonlocal bad
        print(f"{'PASS' if ok else ('FAIL' if required else 'SKIP')}  {name:<20} {detail}"); bad += (not ok) and required
    w = await OpenMeteoProvider(settings.weather_api_url, settings.environment_timeout_seconds, settings.environment_max_age_seconds).current(lat, lon)
    show("Open-Meteo weather", w["status"] in {"LIVE", "RECENT"}, f"{w['status']} T={w['temperature']}C wind={w['wind_speed']}km/h obs={w['timestamp']}")
    n = await NWSProvider(settings.environment_timeout_seconds, settings.nws_user_agent).current(lat, lon)
    show("NWS (U.S. only)", n["status"] in {"LIVE", "RECENT"}, f"{n['status']} {n.get('message', '')}", required=settings.environment_provider.lower().startswith("nws"))
    a = await fetch_air_quality(lat, lon); show("Air quality", a["air_quality_status"] == "LIVE", f"PM2.5={a['pm25']}", required=False)
    e = await fetch_elevation(lat, lon); show("Elevation", e["terrain_status"] == "LIVE", f"{e['elevation_m']} m", required=False)
    f = await fetch_firms(lat, lon, use_cache=False)
    show("NASA FIRMS", f["satellite_status"] in {"LIVE", "PARTIAL"}, f"{f['satellite_status']} {f.get('satellite_message') or ''} detections={f.get('total_detections')}")
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?service=WMS&version=1.3.0&request=GetCapabilities")
        show("NASA GIBS imagery", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as ex:
        show("NASA GIBS imagery", False, ex.__class__.__name__)
    print("\nAll required sources live." if not bad else f"\n{bad} required source(s) failing."); return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
