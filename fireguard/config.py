from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file=".env",env_prefix="FIREGUARD_",extra="ignore")
    app_name:str="EcoSpread-YOLO"; demo_mode:bool=False; database_url:str="sqlite:///./fireguard.db"; model_weights:str|None=None; device:str="cpu"; dataset_path:str=""; cors_origins:str="http://localhost:5173"
    confidence_threshold:float=0.35; temporal_window:int=12; minimum_persistence:int=3; camera_frame_skip:int=0
    latitude:float|None=None; longitude:float|None=None; live_poll_seconds:int=60
    environment_provider:str="open_meteo"; weather_api_url:str="https://api.open-meteo.com/v1/forecast"; air_quality_api_url:str="https://air-quality-api.open-meteo.com/v1/air-quality"; weather_api_key:str|None=None; environment_max_age_seconds:int=1800; environment_timeout_seconds:float=10.0
    nws_user_agent:str="EcoSpread-YOLO (set FIREGUARD_NWS_USER_AGENT to your contact email)"
    alert_cooldown_seconds:int=60; upload_max_mb:int=100; camera_url:str|None=None; camera_id:str="default-camera"
    firms_map_key:str|None=None; firms_source:str="VIIRS_NOAA21_NRT,VIIRS_NOAA20_NRT,VIIRS_SNPP_NRT"; firms_region:str="world"; firms_days:int=1; firms_radius_km:float=250.0; firms_poll_seconds:int=600; satellite_provider:str="firms"
    elevation_api_url:str="https://api.open-meteo.com/v1/elevation"; terrain_provider:str="open_meteo_elevation"
    vegetation_api_url:str|None=None; vegetation_provider:str="none"; alert_threshold:float=0.6; forecast_horizons:str="30,60"
settings=Settings()
