from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlmodel import Session

from fireguard.models import Detection


class DetectionService:
    def __init__(self, session: Session):
        self.session = session

    def create_detection(self, camera_id: str, confidence: float, class_name: str = "fire") -> Detection:
        detection = Detection(
            detection_id=f"det-{uuid4().hex[:12]}",
            event_id=None,
            camera_id=camera_id,
            source_type="IMAGE",
            timestamp=datetime.utcnow(),
            confidence=confidence,
            class_name=class_name,
            x1=0.0,
            y1=0.0,
            x2=0.0,
            y2=0.0,
            visual_area_proxy=None,
            model_version="yolo11n",
            is_valid=True,
        )
        self.session.add(detection)
        self.session.commit()
        self.session.refresh(detection)
        return detection
