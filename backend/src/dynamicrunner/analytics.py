"""Analytics event tracking.

Tracks key product events to the `analytics_events` table in Supabase.
This provides onboarding funnel, DAU, plan completion, and agent acceptance
metrics without requiring a third-party analytics provider.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx
import structlog

from dynamicrunner.config import Settings

log = structlog.get_logger(__name__)


def track_event(
    settings: Settings,
    user_id: str,
    event: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Track an analytics event."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    try:
        httpx.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/analytics_events",
            headers=headers,
            json={
                "user_id": user_id,
                "event": event,
                "properties": properties or {},
                "event_date": date.today().isoformat(),
                "created_at": datetime.utcnow().isoformat(),
            },
            timeout=5,
        )
    except Exception as exc:
        log.warning("analytics.track_failed", event=event, error=str(exc))


# Standard event names
EVENT_SIGNUP = "signup"
EVENT_ONBOARDING_START = "onboarding_start"
EVENT_ONBOARDING_STEP = "onboarding_step"
EVENT_ONBOARDING_COMPLETE = "onboarding_complete"
EVENT_GARMIN_CONNECTED = "garmin_connected"
EVENT_GARMIN_DISCONNECTED = "garmin_disconnected"
EVENT_PLAN_GENERATED = "plan_generated"
EVENT_WORKOUT_COMPLETED = "workout_completed"
EVENT_WORKOUT_PUSHED = "workout_pushed"
EVENT_CHECKIN_SUBMITTED = "checkin_submitted"
EVENT_ADAPTATION_RUN = "adaptation_run"
EVENT_ADAPTATION_ACCEPTED = "adaptation_accepted"
EVENT_ADAPTATION_UNDONE = "adaptation_undone"
EVENT_APP_OPEN = "app_open"


def compute_metrics(settings: Settings, days: int = 30) -> dict[str, Any]:
    """Compute key product metrics for the analytics dashboard."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    from datetime import timedelta
    since = (date.today() - timedelta(days=days)).isoformat()

    # DAU — distinct users with app_open in last N days
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/analytics_events",
        params={
            "event": f"eq.{EVENT_APP_OPEN}",
            "event_date": f"gte.{since}",
            "select": "user_id",
        },
        headers=headers,
        timeout=15,
    )

    dau_users: set[str] = set()
    if resp.status_code == 200:
        for row in resp.json():
            dau_users.add(row["user_id"])

    # Onboarding funnel
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/analytics_events",
        params={
            "event": f"in.({EVENT_ONBOARDING_START},{EVENT_ONBOARDING_COMPLETE})",
            "event_date": f"gte.{since}",
            "select": "event,user_id",
        },
        headers=headers,
        timeout=10,
    )

    onboarding_started: set[str] = set()
    onboarding_completed: set[str] = set()
    if resp.status_code == 200:
        for row in resp.json():
            if row["event"] == EVENT_ONBOARDING_START:
                onboarding_started.add(row["user_id"])
            elif row["event"] == EVENT_ONBOARDING_COMPLETE:
                onboarding_completed.add(row["user_id"])

    onboarding_rate = (
        round(len(onboarding_completed) / len(onboarding_started) * 100)
        if onboarding_started
        else 0
    )

    # Plan completion — users with at least one completed workout
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/analytics_events",
        params={
            "event": f"eq.{EVENT_WORKOUT_COMPLETED}",
            "event_date": f"gte.{since}",
            "select": "user_id",
        },
        headers=headers,
        timeout=10,
    )

    active_trainers: set[str] = set()
    if resp.status_code == 200:
        for row in resp.json():
            active_trainers.add(row["user_id"])

    return {
        "period_days": days,
        "dau_unique": len(dau_users),
        "onboarding_started": len(onboarding_started),
        "onboarding_completed": len(onboarding_completed),
        "onboarding_conversion_pct": onboarding_rate,
        "active_trainers": len(active_trainers),
    }
