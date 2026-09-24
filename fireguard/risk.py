from __future__ import annotations

from dataclasses import dataclass


def risk_level(score: float) -> str:
    if score < 20:
        return "LOW"
    if score < 40:
        return "GUARDED"
    if score < 60:
        return "MODERATE"
    if score < 80:
        return "HIGH"
    return "CRITICAL"


@dataclass
class RiskWeights:
    visual: float = 0.25
    persistence: float = 0.15
    growth: float = 0.15
    wind: float = 0.10
    temperature: float = 0.10
    humidity: float = 0.10
    dryness: float = 0.10
    smoke: float = 0.05


def calculate_risk(features: dict[str, float], weights: RiskWeights | None = None) -> dict[str, float | str | dict]:
    weights = weights or RiskWeights()
    score = 0.0
    for key in weights.__annotations__:
        value = float(features.get(key, 0.0))
        score += min(max(value, 0.0), 100.0) * getattr(weights, key)
    score = min(100.0, max(0.0, score))
    return {"score": round(score, 2), "level": risk_level(score), "features": features}
