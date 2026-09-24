from __future__ import annotations
import asyncio
import io
import time
from collections import deque
from contextlib import asynccontextmanager,suppress
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from fastapi import FastAPI,File,HTTPException,UploadFile,WebSocket,WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fireguard.config import settings
from fireguard.environment import DemoProvider,NWSProvider,OpenMeteoProvider,UnavailableProvider
from fireguard.live_data import collect_live_sources
from fireguard.runtime import FireguardRuntime
from utils.device import configure_precision,detect_device,get_gpu_info,get_gpu_memory,get_gpu_utilization

def _build_environment_provider():
    if settings.demo_mode: return DemoProvider()
    choice=settings.environment_provider.lower()
    if choice in {"nws","nws_gov","noaa","government","gov"}: return NWSProvider(settings.environment_timeout_seconds,settings.nws_user_agent,settings.environment_max_age_seconds)
    if choice in {"open_meteo","open-meteo","weather","live"}: return OpenMeteoProvider(settings.weather_api_url,settings.environment_timeout_seconds,settings.environment_max_age_seconds)
    return UnavailableProvider()
environment_provider=_build_environment_provider()
runtime=FireguardRuntime(model_path=settings.model_weights,device=settings.device or detect_device())
environment_history:deque[dict[str,Any]]=deque(maxlen=288)
risk_history:deque[dict[str,Any]]=deque(maxlen=288)
fires:dict[str,dict[str,Any]]={}
alerts:dict[str,dict[str,Any]]={}
live_state:dict[str,Any]={"timestamp":None,"satellite":{"fires":[],"satellite_status":"NOT_STARTED"}}
connections:list[WebSocket]=[]

def now(): return datetime.now(timezone.utc).isoformat()
async def broadcast(payload):
    stale=[]
    for ws in connections:
        try: await ws.send_json(payload)
        except Exception: stale.append(ws)
    for ws in stale:
        if ws in connections: connections.remove(ws)

async def collect_once():
    lat,lon=settings.latitude,settings.longitude
    try:
        env=await environment_provider.current(lat,lon)
        live=await collect_live_sources(lat,lon)
        env.update(live.get("air_quality",{}))
        env["terrain"]=live.get("terrain",{})
        environment_history.append(env)
        live_state.clear(); live_state.update(live)
        satellite_fires=live.get("satellite",{}).get("fires",[])
        live_state["timestamp"]=now()
        await broadcast({"type":"live_update","timestamp":live_state["timestamp"],"environment":env,"satellite":live.get("satellite",{}),"terrain":live.get("terrain",{})})
    except Exception as exc:
        live_state["error"]=exc.__class__.__name__
        await broadcast({"type":"live_error","timestamp":now(),"error":exc.__class__.__name__})

async def poller():
    while True:
        await collect_once()
        await asyncio.sleep(max(15,settings.live_poll_seconds))

@asynccontextmanager
async def lifespan(app:FastAPI):
    task=asyncio.create_task(poller())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError): await task

app=FastAPI(title="EcoSpread-YOLO",version="1.1.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

@app.get("/api/health")
async def health(): return {"status":"healthy","demo_mode":settings.demo_mode,"environment_provider":environment_provider.name,"model_status":runtime.get_status()["status"],"live_poll_seconds":settings.live_poll_seconds,"timestamp":now()}
@app.get("/api/system/gpu")
async def system_gpu():
    device=detect_device(); return {"device":device,"precision":configure_precision(device),"gpu_info":get_gpu_info(),"gpu_memory":get_gpu_memory(),"gpu_utilization":get_gpu_utilization(),"status":"AVAILABLE" if device.startswith("cuda") else "CPU_MODE"}
@app.get("/api/model/status")
async def model_status(): return runtime.get_status()

@app.post("/api/detection/image")
async def detection_image(file:UploadFile=File(...),camera_id:str|None=None):
    if not settings.model_weights: raise HTTPException(503,"Model weights are not configured. Detection is unavailable.")
    if not file.filename: raise HTTPException(400,"A filename is required.")
    if Path(file.filename).suffix.lower() not in {".jpg",".jpeg",".png",".webp",".bmp"}: raise HTTPException(400,"Unsupported image type.")
    try:
        from PIL import Image
        from ultralytics import YOLO
        image=Image.open(io.BytesIO(await file.read())).convert("RGB"); start=time.perf_counter()
        model=YOLO(settings.model_weights)
        results=model.predict(source=image,device=settings.device or detect_device(),conf=settings.confidence_threshold,verbose=False)
        latency=round((time.perf_counter()-start)*1000,2)
    except ImportError as exc: raise HTTPException(503,f"ML dependencies unavailable: {exc}") from exc
    except Exception as exc: raise HTTPException(500,f"Inference failed: {exc.__class__.__name__}") from exc
    detections=[]
    for result in results:
        names=getattr(result,"names",{}) or {}; boxes=getattr(result,"boxes",None)
        if boxes is None: continue
        for i,box in enumerate(boxes):
            cls=int(box.cls.item()); conf=float(box.conf.item()); xyxy=[float(x) for x in box.xyxy[0].tolist()]
            area=max(0,xyxy[2]-xyxy[0])*max(0,xyxy[3]-xyxy[1])
            detections.append({"detection_id":f"det-{int(time.time()*1000)}-{i}","camera_id":camera_id or settings.camera_id,"timestamp":now(),"confidence":round(conf,4),"class_name":names.get(cls,str(cls)),"bbox":xyxy,"visual_area_proxy":round(area,2),"inference_latency_ms":latency,"model_version":Path(settings.model_weights).stem})
    payload={"status":"completed","file":file.filename,"latency_ms":latency,"count":len(detections),"detections":detections}
    await broadcast({"type":"detection_update","payload":payload,"timestamp":now()}); return payload

@app.get("/api/cameras")
async def cameras(): return [{"camera_id":settings.camera_id,"name":"Primary UAV","source_type":"UAV","url":settings.camera_url,"active":bool(settings.camera_url),"gps_locked":settings.latitude is not None and settings.longitude is not None}]
@app.get("/api/fires")
async def list_fires(): return list(fires.values())
@app.get("/api/satellite/fires")
async def satellite_fires(): return live_state.get("satellite",{})
@app.get("/api/fires/{event_id}")
async def fire(event_id:str):
    if event_id not in fires: raise HTTPException(404,"Fire event not found.")
    return fires[event_id]
@app.get("/api/environment/current")
async def environment_current(latitude:float|None=None,longitude:float|None=None):
    if latitude is None: latitude=settings.latitude
    if longitude is None: longitude=settings.longitude
    env=await environment_provider.current(latitude,longitude)
    extra=await collect_live_sources(latitude,longitude,include_satellite=False); env.update(extra.get("air_quality",{})); env["terrain"]=extra.get("terrain",{}); return env
@app.get("/api/environment/history")
async def environment_history_endpoint(): return list(environment_history)
@app.get("/api/live/status")
async def live_status(): return {"timestamp":live_state.get("timestamp"),"location":{"latitude":settings.latitude,"longitude":settings.longitude},"sources":{"weather":environment_provider.name,"air_quality":live_state.get("air_quality",{}).get("air_quality_status","UNAVAILABLE"),"terrain":live_state.get("terrain",{}).get("terrain_status","UNAVAILABLE"),"satellite":live_state.get("satellite",{}).get("satellite_status","UNAVAILABLE")},"config":{"firms_key_configured":bool(settings.firms_map_key),"firms_sources":[x.strip() for x in settings.firms_source.split(",") if x.strip()],"firms_radius_km":settings.firms_radius_km,"weather_provider":environment_provider.name,"demo_mode":settings.demo_mode}}
@app.get("/api/alerts")
async def list_alerts(): return list(alerts.values())
@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge(alert_id:str):
    if alert_id not in alerts: raise HTTPException(404,"Alert not found.")
    alerts[alert_id]["acknowledged"]=True; alerts[alert_id]["acknowledged_at"]=now(); return alerts[alert_id]
@app.get("/api/analytics/overview")
async def analytics():
    active=[f for f in fires.values() if f.get("status")=="ACTIVE"]; score=max((f.get("risk_score",0) for f in active),default=0)
    return {"total_events":len(fires),"active_events":len(active),"alert_count":len(alerts),"satellite_events":len(live_state.get("satellite",{}).get("fires",[])),"risk_level":"CRITICAL" if score>=80 else "HIGH" if score>=60 else "MODERATE" if score>=40 else "LOW","source_status":environment_provider.name,"model_metrics":{},"timestamp":now()}
@app.get("/api/dashboard/summary")
async def summary():
    if not live_state.get("timestamp"): await collect_once()
    env=environment_history[-1] if environment_history else await environment_provider.current(settings.latitude,settings.longitude)
    gpu=await system_gpu(); model=runtime.get_status(); stats=await analytics(); sat=live_state.get("satellite",{})
    return {"timestamp":now(),"health":await health(),"environment":env,"environment_history":list(environment_history)[-48:],"fires":list(fires.values()),"satellite_fires":sat.get("fires",[]),"satellite_meta":{k:v for k,v in sat.items() if k!="fires"},"alerts":list(alerts.values()),"analytics":stats,"gpu":gpu,"model":model,"live":await live_status(),"providers":{"satellite":sat.get("satellite_status","UNAVAILABLE"),"terrain":live_state.get("terrain",{}).get("terrain_status","UNAVAILABLE"),"vegetation":"UNAVAILABLE"},"risk_history":list(risk_history)[-48:]}

@app.websocket("/ws/live")
async def websocket_live(websocket:WebSocket):
    await websocket.accept(); connections.append(websocket)
    await websocket.send_json({"type":"live_update","timestamp":now(),"environment":environment_history[-1] if environment_history else None,"satellite":live_state.get("satellite",{}),"terrain":live_state.get("terrain",{})})
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connections: connections.remove(websocket)
