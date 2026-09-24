from __future__ import annotations

from typing import Any


class FireguardRuntime:
    def __init__(self, model_path: str | None = None, device: str = "cpu"):
        self.model_path = model_path
        self.device = device

    def get_status(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "device": self.device,
            "status": "READY" if self.model_path else "UNAVAILABLE",
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "note": "Model weights are required before inference can run.",
        }


class ModelRuntime:
    def __init__(self, weights_path: str | None = None):
        self.weights_path = weights_path

    def status(self) -> dict[str, Any]:
        return {
            "weights_path": self.weights_path,
            "ready": bool(self.weights_path),
            "note": "Real YOLO weights are required before production inference.",
        }
