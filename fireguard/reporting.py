from __future__ import annotations

from typing import Any

from .config import settings


def extract_dataset_report(path: str = "reports/dataset_report.json") -> dict[str, Any] | None:
    import json
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
