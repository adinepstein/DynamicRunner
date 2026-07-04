"""Plan generation and retrieval API routes."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from dynamicrunner.ai.planner import generate_plan
from dynamicrunner.config import get_settings

import httpx

router = APIRouter(prefix="/plan", tags=["plan"])


class GeneratePlanResponse(BaseModel):
    status: str
    message: str
    plan_id: str | None = None


class PlanResponse(BaseModel):
    id: str
    status: str
    payload: dict[str, Any]
    created_at: str


class WorkoutResponse(BaseModel):
    id: str
    scheduled_date: str
    payload: dict[str, Any]


@router.post("/generate", response_model=GeneratePlanResponse)
def trigger_plan_generation(request: Request) -> GeneratePlanResponse:
    """Trigger AI plan generation for the authenticated user.

    Runs in a background thread and returns immediately.
    """
    uid: str = request.state.uid
    settings = get_settings()

    if not settings.gemini_api_key:
        return GeneratePlanResponse(
            status="error",
            message="AI plan generation is not configured (missing GEMINI_API_KEY)",
        )

    def _generate() -> None:
        try:
            result = generate_plan(settings, uid)
            if not result.success:
                import structlog
                log = structlog.get_logger(__name__)
                log.warning("plan.generation_failed", user_id=uid, error=result.error)
        except Exception as exc:
            import structlog
            log = structlog.get_logger(__name__)
            log.error("plan.generation_exception", user_id=uid, error=str(exc))

    thread = threading.Thread(target=_generate, daemon=True)
    thread.start()

    return GeneratePlanResponse(
        status="generating",
        message="Plan generation started. Check back in 30-60 seconds.",
    )


@router.get("/active", response_model=PlanResponse | None)
def get_active_plan(request: Request) -> PlanResponse | None:
    """Get the user's currently active plan."""
    uid: str = request.state.uid
    settings = get_settings()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/plans",
        params={
            "user_id": f"eq.{uid}",
            "status": "eq.active",
            "select": "id,status,payload,created_at",
            "limit": "1",
        },
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()

    if not rows:
        return None

    row = rows[0]
    return PlanResponse(
        id=row["id"],
        status=row["status"],
        payload=row["payload"],
        created_at=row["created_at"],
    )


@router.get("/workouts", response_model=list[WorkoutResponse])
def get_plan_workouts(
    request: Request,
    plan_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[WorkoutResponse]:
    """Get workouts for the active plan (or specified plan_id)."""
    uid: str = request.state.uid
    settings = get_settings()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    params: dict[str, str] = {
        "user_id": f"eq.{uid}",
        "select": "id,scheduled_date,payload",
        "order": "scheduled_date.asc",
    }

    if plan_id:
        params["plan_id"] = f"eq.{plan_id}"

    if from_date:
        params["scheduled_date"] = f"gte.{from_date}"
    if to_date:
        if "scheduled_date" in params:
            params["scheduled_date"] += f"&scheduled_date=lte.{to_date}"
        else:
            params["scheduled_date"] = f"lte.{to_date}"

    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
        params=params,
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()

    return [
        WorkoutResponse(
            id=row["id"],
            scheduled_date=row["scheduled_date"],
            payload=row["payload"],
        )
        for row in resp.json()
    ]
