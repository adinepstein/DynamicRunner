"""Activity-to-workout matcher.

When a new Garmin activity is synced, this module matches it to the
planned workout for that day and updates the workout status accordingly.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import structlog

from dynamicrunner.config import Settings

log = structlog.get_logger(__name__)


def match_activity_to_workout(
    settings: Settings, user_id: str, activity: dict[str, Any]
) -> str | None:
    """Match a synced activity to a planned workout.

    Looks for a planned workout on the same day as the activity.
    If found, marks it as completed and links the activity ID.

    Returns the matched workout_id or None.
    """
    activity_date = activity.get("activity_date") or activity.get("startTimeLocal", "")[:10]
    if not activity_date:
        return None

    garmin_activity_id = str(activity.get("garmin_activity_id") or activity.get("activityId", ""))

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    # Find planned workout for that day
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
        params={
            "user_id": f"eq.{user_id}",
            "scheduled_date": f"eq.{activity_date}",
            "select": "id,payload",
        },
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    workouts = resp.json()

    if not workouts:
        return None

    # Find best match: prefer unmatched workout that isn't rest
    best_match = None
    for w in workouts:
        payload = w.get("payload", {})
        if payload.get("type") == "rest":
            continue
        if payload.get("completedActivityId"):
            continue
        best_match = w
        break

    if not best_match:
        # All workouts already matched or are rest days
        return None

    workout_id = best_match["id"]
    payload = best_match.get("payload", {})

    # Update workout: mark as completed, link activity
    payload["status"] = "completed"
    payload["completedActivityId"] = garmin_activity_id

    headers_write = {**headers, "Content-Type": "application/json", "Prefer": "return=minimal"}
    resp = httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
        params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"},
        headers=headers_write,
        json={"payload": payload},
        timeout=10,
    )
    resp.raise_for_status()

    log.info(
        "matcher.matched",
        user_id=user_id,
        workout_id=workout_id,
        activity_id=garmin_activity_id,
        date=activity_date,
    )
    return workout_id


def run_matching_for_user(settings: Settings, user_id: str, days: int = 2) -> int:
    """Run activity matching for recent days. Returns count of matches made."""
    from datetime import timedelta

    since = (date.today() - timedelta(days=days)).isoformat()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/activities",
        params={
            "user_id": f"eq.{user_id}",
            "activity_date": f"gte.{since}",
            "select": "garmin_activity_id,activity_date,payload",
            "order": "activity_date.asc",
        },
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    activities = resp.json()

    matched = 0
    for a in activities:
        result = match_activity_to_workout(settings, user_id, a)
        if result:
            matched += 1

    return matched
