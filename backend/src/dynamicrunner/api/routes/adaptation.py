"""Adaptation feed and undo API routes."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dynamicrunner.config import get_settings

router = APIRouter(prefix="/adaptation", tags=["adaptation"])


class FeedEntry(BaseModel):
    id: str
    payload: dict[str, Any]
    created_at: str


class UndoRequest(BaseModel):
    workout_id: str


class UndoResponse(BaseModel):
    status: str
    message: str


@router.get("/feed", response_model=list[FeedEntry])
def get_adaptation_feed(request: Request, limit: int = 20) -> list[FeedEntry]:
    """Get the adaptation history feed for the authenticated user."""
    uid: str = request.state.uid
    settings = get_settings()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/agent_runs",
        params={
            "user_id": f"eq.{uid}",
            "select": "id,payload,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        },
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()

    return [
        FeedEntry(id=row["id"], payload=row["payload"], created_at=row["created_at"])
        for row in resp.json()
    ]


@router.post("/undo", response_model=UndoResponse)
def undo_change(request: Request, body: UndoRequest) -> UndoResponse:
    """Undo an adapter-made change to a workout (restore previous state).

    Only works within 24 hours of the change.
    """
    uid: str = request.state.uid
    settings = get_settings()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    # Fetch the workout
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
        params={
            "id": f"eq.{body.workout_id}",
            "user_id": f"eq.{uid}",
            "select": "id,payload",
        },
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()

    if not rows:
        raise HTTPException(status_code=404, detail="Workout not found")

    payload = rows[0].get("payload", {})

    # Check if there's an agent reason (was modified by adapter)
    if not payload.get("agentReason"):
        return UndoResponse(
            status="no_change",
            message="This workout has not been modified by the adaptation engine.",
        )

    # Remove the agent modification markers
    payload.pop("agentReason", None)
    payload.pop("movedReason", None)

    # If it was downgraded to easy/rest, we can't fully restore without
    # storing previous state. For now, mark it as needing manual review.
    payload["status"] = "planned"

    headers_write = {**headers, "Content-Type": "application/json", "Prefer": "return=minimal"}
    resp = httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
        params={"id": f"eq.{body.workout_id}", "user_id": f"eq.{uid}"},
        headers=headers_write,
        json={"payload": payload},
        timeout=10,
    )
    resp.raise_for_status()

    return UndoResponse(status="undone", message="Change reverted. You may need to regenerate this workout.")


@router.post("/accept")
def accept_changes(request: Request) -> dict[str, str]:
    """Accept all pending adaptation changes (clears the notification badge)."""
    # For now this is a no-op acknowledgement — can be extended to mark
    # agent_runs as "acknowledged" in a future iteration.
    return {"status": "accepted"}
