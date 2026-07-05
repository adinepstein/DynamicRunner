"""GDPR-compliant account deletion pipeline.

Flow: soft delete (mark account) → 30-day grace period → hard delete.
Hard delete removes all user data from all tables.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import httpx
import structlog

from dynamicrunner.config import Settings

log = structlog.get_logger(__name__)

GRACE_PERIOD_DAYS = 30

TABLES_WITH_USER_DATA = [
    "checkins",
    "workouts",
    "plans",
    "agent_runs",
    "activities",
    "daily_metrics",
    "garmin_credentials",
    "garmin_profiles",
    "analytics_events",
    "profiles",
]


def request_deletion(settings: Settings, user_id: str) -> dict[str, Any]:
    """Initiate soft deletion — marks the account for deletion after grace period."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    deletion_date = (date.today() + timedelta(days=GRACE_PERIOD_DAYS)).isoformat()

    resp = httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/profiles",
        params={"user_id": f"eq.{user_id}"},
        headers=headers,
        json={
            "athlete_profile": {
                "deletion_requested": True,
                "deletion_date": deletion_date,
                "deletion_requested_at": datetime.utcnow().isoformat(),
            }
        },
        timeout=10,
    )
    resp.raise_for_status()

    log.info("gdpr.deletion_requested", user_id=user_id, deletion_date=deletion_date)

    return {
        "status": "scheduled",
        "deletion_date": deletion_date,
        "grace_period_days": GRACE_PERIOD_DAYS,
    }


def cancel_deletion(settings: Settings, user_id: str) -> dict[str, str]:
    """Cancel a pending deletion during the grace period."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    resp = httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/profiles",
        params={"user_id": f"eq.{user_id}"},
        headers=headers,
        json={
            "athlete_profile": {
                "deletion_requested": False,
                "deletion_date": None,
                "deletion_requested_at": None,
            }
        },
        timeout=10,
    )
    resp.raise_for_status()

    log.info("gdpr.deletion_cancelled", user_id=user_id)
    return {"status": "cancelled"}


def execute_hard_delete(settings: Settings, user_id: str) -> dict[str, Any]:
    """Execute permanent deletion of all user data.

    Called by cron after the grace period expires.
    """
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Prefer": "return=minimal",
    }

    deleted_tables: list[str] = []
    errors: list[str] = []

    for table in TABLES_WITH_USER_DATA:
        try:
            resp = httpx.delete(
                f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}",
                params={"user_id": f"eq.{user_id}"},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            deleted_tables.append(table)
        except Exception as exc:
            errors.append(f"{table}: {exc}")
            log.error("gdpr.table_delete_failed", table=table, user_id=user_id, error=str(exc))

    # Delete the Supabase Auth user via admin API
    try:
        resp = httpx.delete(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
            timeout=10,
        )
        if resp.status_code in (200, 204):
            deleted_tables.append("auth_user")
        else:
            errors.append(f"auth_user: status {resp.status_code}")
    except Exception as exc:
        errors.append(f"auth_user: {exc}")

    log.info(
        "gdpr.hard_delete_complete",
        user_id=user_id,
        tables_deleted=len(deleted_tables),
        errors=len(errors),
    )

    return {
        "status": "deleted" if not errors else "partial",
        "tables_deleted": deleted_tables,
        "errors": errors,
    }


def process_expired_deletions(settings: Settings) -> dict[str, Any]:
    """Find users past their grace period and execute hard deletes.

    Called by a daily cron job.
    """
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    today = date.today().isoformat()

    # Find profiles with deletion_requested and past deletion_date
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/profiles",
        params={
            "select": "user_id,athlete_profile",
        },
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()

    processed: list[str] = []
    for row in resp.json():
        profile = row.get("athlete_profile") or {}
        if not profile.get("deletion_requested"):
            continue
        deletion_date = profile.get("deletion_date")
        if not deletion_date or deletion_date > today:
            continue

        user_id = row["user_id"]
        execute_hard_delete(settings, user_id)
        processed.append(user_id)

    log.info("gdpr.batch_complete", processed=len(processed))
    return {"processed": len(processed), "user_ids": processed}
