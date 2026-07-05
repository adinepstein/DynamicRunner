"""Post-workout check-in API route."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from dynamicrunner.config import get_settings

router = APIRouter(prefix="/checkin", tags=["checkin"])


class CheckinRequest(BaseModel):
    workout_id: str
    rpe: int = Field(ge=1, le=10)
    feeling: str = Field(pattern="^(great|good|flat|sore|wrecked)$")
    notes: str = Field(default="", max_length=500)


class CheckinResponse(BaseModel):
    status: str
    checkin_id: str | None = None


@router.post("", response_model=CheckinResponse)
def submit_checkin(request: Request, body: CheckinRequest) -> CheckinResponse:
    """Submit a post-workout check-in (RPE + feeling)."""
    uid: str = request.state.uid
    settings = get_settings()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    # Verify the workout belongs to this user
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
        params={
            "id": f"eq.{body.workout_id}",
            "user_id": f"eq.{uid}",
            "select": "id",
        },
        headers={
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        },
        timeout=10,
    )
    resp.raise_for_status()
    if not resp.json():
        raise HTTPException(status_code=404, detail="Workout not found")

    # Upsert check-in (unique on user_id + workout_id)
    checkin_payload: dict[str, Any] = {
        "user_id": uid,
        "workout_id": body.workout_id,
        "payload": {
            "rpe": body.rpe,
            "feeling": body.feeling,
            "notes": body.notes,
        },
    }

    resp = httpx.post(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/checkins",
        headers={**headers, "Prefer": "resolution=merge-duplicates,return=representation"},
        json=checkin_payload,
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()
    checkin_id = rows[0]["id"] if rows else None

    return CheckinResponse(status="saved", checkin_id=checkin_id)
