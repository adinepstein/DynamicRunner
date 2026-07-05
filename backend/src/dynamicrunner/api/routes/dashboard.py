"""Dashboard data routes — training load, HRV, plan progress."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Request

from dynamicrunner.config import get_settings
from dynamicrunner.training_load import compute_training_load

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/training-load")
def get_training_load(request: Request, days: int = 42) -> dict[str, Any]:
    """Get CTL/ATL/TSB/ACWR chart data for the authenticated user."""
    uid: str = request.state.uid
    settings = get_settings()
    return compute_training_load(settings, uid, days=min(days, 90))


@router.get("/progress")
def get_plan_progress(request: Request) -> dict[str, Any]:
    """Get plan progress summary for the home widget."""
    uid: str = request.state.uid
    settings = get_settings()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    # Fetch active plan
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/plans",
        params={
            "user_id": f"eq.{uid}",
            "status": "eq.active",
            "select": "id,payload,created_at",
            "limit": "1",
        },
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    plans = resp.json()

    if not plans:
        return {"has_plan": False}

    plan = plans[0]
    plan_id = plan["id"]
    plan_payload = plan.get("payload", {})

    # Fetch all workouts for this plan
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
        params={
            "plan_id": f"eq.{plan_id}",
            "user_id": f"eq.{uid}",
            "select": "payload,scheduled_date",
            "order": "scheduled_date.asc",
        },
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    workouts = resp.json()

    total = len(workouts)
    completed = sum(
        1 for w in workouts if (w.get("payload") or {}).get("status") == "completed"
    )
    skipped = sum(
        1 for w in workouts if (w.get("payload") or {}).get("status") == "skipped"
    )
    rest_days = sum(
        1 for w in workouts if (w.get("payload") or {}).get("type") == "rest"
    )

    trainable = total - rest_days
    completion_pct = round(completed / trainable * 100) if trainable > 0 else 0

    # Compute weeks progress
    if workouts:
        from datetime import date

        first_date = workouts[0].get("scheduled_date", "")[:10]
        last_date = workouts[-1].get("scheduled_date", "")[:10]
        try:
            first = date.fromisoformat(first_date)
            last = date.fromisoformat(last_date)
            today = date.today()
            total_weeks = max(1, (last - first).days // 7 + 1)
            weeks_elapsed = max(0, min(total_weeks, (today - first).days // 7 + 1))
        except ValueError:
            total_weeks = 0
            weeks_elapsed = 0
    else:
        total_weeks = 0
        weeks_elapsed = 0

    return {
        "has_plan": True,
        "plan_id": plan_id,
        "race_type": plan_payload.get("raceType"),
        "race_date": plan_payload.get("raceDate"),
        "total_workouts": total,
        "completed": completed,
        "skipped": skipped,
        "rest_days": rest_days,
        "completion_pct": completion_pct,
        "total_weeks": total_weeks,
        "weeks_elapsed": weeks_elapsed,
    }
