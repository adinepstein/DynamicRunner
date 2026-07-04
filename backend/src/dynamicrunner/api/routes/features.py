"""Feature extraction API route."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from dynamicrunner.config import get_settings
from dynamicrunner.features import extract_features, features_to_prompt_context

router = APIRouter(prefix="/features", tags=["features"])


class FeaturesResponse(BaseModel):
    user_id: str
    computed_at: str
    weeks_available: int
    current_weekly_km: float
    peak_weekly_km: float
    avg_weekly_km: float
    trend: str
    prompt_context: dict[str, Any]


@router.get("", response_model=FeaturesResponse)
def get_features(request: Request, days: int = 90) -> FeaturesResponse:
    """Extract training features for the authenticated user."""
    uid: str = request.state.uid
    settings = get_settings()

    features = extract_features(settings, uid, days=days)
    prompt_ctx = features_to_prompt_context(features)

    return FeaturesResponse(
        user_id=uid,
        computed_at=features.computed_at,
        weeks_available=features.weeks_available,
        current_weekly_km=round(features.current_weekly_volume_m / 1000, 1),
        peak_weekly_km=round(features.peak_weekly_volume_m / 1000, 1),
        avg_weekly_km=round(features.avg_weekly_volume_m / 1000, 1),
        trend=features.trend_direction,
        prompt_context=prompt_ctx,
    )
