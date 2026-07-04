"""Internal endpoints — protected by CRON_SECRET, not user JWT.

These are called by external schedulers (GitHub Actions, cron-job.org, etc.)
to trigger periodic sync jobs.
"""

from __future__ import annotations

import threading
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request, status

from dynamicrunner.config import get_settings
from dynamicrunner.garmin.backfill import BackfillError, run_backfill

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _verify_cron_secret(request: Request) -> None:
    """Verify the request carries a valid CRON_SECRET."""
    settings = get_settings()
    if not settings.cron_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CRON_SECRET not configured",
        )

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth.removeprefix("Bearer ").strip()
    if token != settings.cron_secret:
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.post("/sync")
def trigger_sync_all(request: Request) -> dict[str, Any]:
    """Trigger a daily delta sync for all connected users.

    Called by external cron ~04:00 user-local (or a single global schedule).
    Syncs last 2 days to catch late-arriving Garmin data.
    """
    _verify_cron_secret(request)
    settings = get_settings()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/garmin_profiles",
        params={
            "select": "user_id",
            "sync_status": "in.(ok,error)",
            "reauth_required": "eq.false",
        },
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    users = resp.json()

    if not users:
        return {"status": "ok", "synced": 0, "message": "No users to sync"}

    user_ids = [u["user_id"] for u in users]
    log.info("sync.triggered", user_count=len(user_ids))

    def _sync_user(uid: str) -> None:
        try:
            run_backfill(settings, uid, days=2)
        except BackfillError as exc:
            log.error("sync.user_failed", user_id=uid, error=str(exc))
        except Exception as exc:
            log.exception("sync.user_unexpected", user_id=uid, error=str(exc))

    # Run each user sync in a separate thread (bounded concurrency)
    threads: list[threading.Thread] = []
    for uid in user_ids:
        t = threading.Thread(target=_sync_user, daemon=True, name=f"sync-{uid[:8]}")
        t.start()
        threads.append(t)

    return {
        "status": "started",
        "synced": len(user_ids),
        "message": f"Delta sync started for {len(user_ids)} user(s)",
    }


@router.post("/sync/{user_id}")
def trigger_sync_user(user_id: str, request: Request) -> dict[str, Any]:
    """Trigger a delta sync for a specific user (last 2 days)."""
    _verify_cron_secret(request)
    settings = get_settings()

    def _run() -> None:
        try:
            run_backfill(settings, user_id, days=2)
        except BackfillError as exc:
            log.error("sync.user_failed", user_id=user_id, error=str(exc))
        except Exception as exc:
            log.exception("sync.user_unexpected", user_id=user_id, error=str(exc))

    thread = threading.Thread(target=_run, daemon=True, name=f"sync-{user_id[:8]}")
    thread.start()

    return {"status": "started", "user_id": user_id, "days": 2}
