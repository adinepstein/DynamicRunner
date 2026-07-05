"""Feedback collection route for beta testing."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

from dynamicrunner.config import get_settings

router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    category: str
    message: str


@router.post("/feedback")
def submit_feedback(request: Request, body: FeedbackRequest) -> dict[str, str]:
    """Submit user feedback (stored for beta review)."""
    uid: str = request.state.uid
    settings = get_settings()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    httpx.post(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/analytics_events",
        headers=headers,
        json={
            "user_id": uid,
            "event": "feedback",
            "properties": {
                "category": body.category,
                "message": body.message,
            },
        },
        timeout=10,
    )

    return {"status": "received"}
