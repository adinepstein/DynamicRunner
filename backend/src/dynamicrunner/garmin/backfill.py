"""Garmin 90-day backfill service.

Fetches activities, daily metrics (steps, RHR, sleep, body battery, stress),
and HRV from Garmin Connect for a given user. Writes results idempotently
to Supabase (upsert on natural keys).
"""

from __future__ import annotations

import time
import warnings
from datetime import date, timedelta
from typing import Any

import httpx
import structlog

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    import garth
    from garth.exc import GarthHTTPError

from curl_cffi import requests as curl_requests
from curl_cffi.requests.exceptions import HTTPError as CurlCffiHTTPError

from dynamicrunner.config import Settings
from dynamicrunner.garmin import GarminCredentialStore, GarminTokens

log = structlog.get_logger(__name__)

IMPERSONATE_TARGET = "chrome131"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

BACKFILL_DAYS = 90
ACTIVITIES_PAGE_SIZE = 50
REQUEST_DELAY_S = 1.0


class BackfillError(Exception):
    """Raised when backfill fails in a non-recoverable way."""


class TokenExpiredError(BackfillError):
    """Raised when stored tokens are expired/invalid and re-auth is needed."""


def _make_session() -> curl_requests.Session:
    sess = curl_requests.Session(impersonate=IMPERSONATE_TARGET)
    sess.headers["User-Agent"] = USER_AGENT
    return sess


def _restore_garth_client(tokens: GarminTokens) -> garth.Client:
    """Restore a garth Client from stored token blob."""
    client = garth.Client()

    raw = tokens.raw
    blob_str = raw.get("__blob")
    if blob_str:
        import json
        import tempfile
        from pathlib import Path

        blob = json.loads(blob_str)
        # garth stores tokens as files in a directory; we recreate that structure
        tmpdir = Path(tempfile.mkdtemp())
        if "oauth1" in blob:
            (tmpdir / "oauth1_token.json").write_text(json.dumps(blob["oauth1"]))
        if "oauth2" in blob:
            (tmpdir / "oauth2_token.json").write_text(json.dumps(blob["oauth2"]))
        try:
            client.load(str(tmpdir))
        except Exception:
            pass

    client.sess = _make_session()
    return client


def _safe_get(client: garth.Client, path: str, params: dict[str, Any] | None = None) -> Any:
    """Make a Connect API call with error handling."""
    try:
        return client.connectapi(path, params=params)
    except (GarthHTTPError, CurlCffiHTTPError) as exc:
        msg = str(exc)
        if "401" in msg or "403" in msg:
            raise TokenExpiredError(f"Token expired/invalid: {msg}") from exc
        log.warning("garmin.api_error", path=path, error=msg)
        return None


def _fetch_activities(
    client: garth.Client, start: date, end: date
) -> list[dict[str, Any]]:
    """Fetch all activities in date range, paginated."""
    all_activities: list[dict[str, Any]] = []
    offset = 0

    while True:
        time.sleep(REQUEST_DELAY_S)
        result = _safe_get(
            client,
            "/activitylist-service/activities/search/activities",
            params={
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "limit": ACTIVITIES_PAGE_SIZE,
                "start": offset,
            },
        )
        if not result or not isinstance(result, list):
            break

        all_activities.extend(result)

        if len(result) < ACTIVITIES_PAGE_SIZE:
            break
        offset += ACTIVITIES_PAGE_SIZE

    return all_activities


def _fetch_daily_metrics(
    client: garth.Client, target_date: date
) -> dict[str, Any] | None:
    """Fetch daily summary + HRV for a single date."""
    summary = _safe_get(
        client,
        f"/usersummary-service/usersummary/daily/?calendarDate={target_date.isoformat()}",
    )
    if not summary or not isinstance(summary, dict):
        return None

    time.sleep(REQUEST_DELAY_S)

    hrv = _safe_get(client, f"/hrv-service/hrv/{target_date.isoformat()}")
    hrv_avg = None
    if isinstance(hrv, dict) and "hrvSummary" in hrv:
        hrv_avg = (hrv.get("hrvSummary") or {}).get("lastNightAvg")

    return {
        "date": target_date.isoformat(),
        "steps": summary.get("totalSteps"),
        "resting_hr": summary.get("restingHeartRate"),
        "sleeping_seconds": summary.get("sleepingSeconds"),
        "body_battery_high": summary.get("bodyBatteryHighestValue"),
        "body_battery_low": summary.get("bodyBatteryLowestValue"),
        "average_stress": summary.get("averageStressLevel"),
        "vo2max_running": summary.get("currentDayRestingHeartRate"),
        "hrv_last_night_avg": hrv_avg,
        "raw_summary": summary,
        "raw_hrv": hrv if isinstance(hrv, dict) else None,
    }


def _upsert_activities(
    settings: Settings, user_id: str, activities: list[dict[str, Any]]
) -> int:
    """Upsert activities to Supabase. Returns count of rows written."""
    if not activities:
        return 0

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    rows = []
    for a in activities:
        garmin_id = str(a.get("activityId", ""))
        if not garmin_id:
            continue
        activity_date = a.get("startTimeLocal", "")[:10]
        if not activity_date:
            continue
        rows.append({
            "user_id": user_id,
            "garmin_activity_id": garmin_id,
            "activity_date": activity_date,
            "payload": a,
        })

    if not rows:
        return 0

    # Batch in chunks of 50 to avoid payload limits
    chunk_size = 50
    written = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        resp = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/activities",
            headers=headers,
            json=chunk,
            timeout=30,
        )
        resp.raise_for_status()
        written += len(chunk)

    return written


def _upsert_daily_metrics(
    settings: Settings, user_id: str, metrics: list[dict[str, Any]]
) -> int:
    """Upsert daily metrics to Supabase. Returns count of rows written."""
    if not metrics:
        return 0

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    rows = []
    for m in metrics:
        rows.append({
            "user_id": user_id,
            "metric_date": m["date"],
            "payload": m,
        })

    chunk_size = 50
    written = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        resp = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/daily_metrics",
            headers=headers,
            json=chunk,
            timeout=30,
        )
        resp.raise_for_status()
        written += len(chunk)

    return written


def _update_backfill_progress(
    settings: Settings, user_id: str, progress: dict[str, Any]
) -> None:
    """Update garmin_profiles.backfill_progress for UI display."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/garmin_profiles",
        params={"user_id": f"eq.{user_id}"},
        headers=headers,
        json={"backfill_progress": progress, "sync_status": "syncing"},
        timeout=10,
    )
    resp.raise_for_status()


def _mark_sync_complete(settings: Settings, user_id: str) -> None:
    """Mark garmin_profiles as sync complete."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/garmin_profiles",
        params={"user_id": f"eq.{user_id}"},
        headers=headers,
        json={
            "sync_status": "ok",
            "last_sync_at": "now()",
            "backfill_progress": {"status": "complete", "percent": 100},
        },
        timeout=10,
    )
    resp.raise_for_status()


def _mark_sync_error(settings: Settings, user_id: str, error: str, reauth: bool = False) -> None:
    """Mark garmin_profiles with error status."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    payload: dict[str, Any] = {
        "sync_status": "reauth_required" if reauth else "error",
        "reauth_required": reauth,
        "backfill_progress": {"status": "error", "error": error},
    }
    resp = httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/garmin_profiles",
        params={"user_id": f"eq.{user_id}"},
        headers=headers,
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()


def run_backfill(settings: Settings, user_id: str, days: int = BACKFILL_DAYS) -> dict[str, Any]:
    """Run the full backfill for a user. Returns summary stats.

    This is a synchronous, blocking operation (designed to run in a background
    thread or worker). Updates garmin_profiles.backfill_progress as it goes.
    """
    log.info("backfill.start", user_id=user_id, days=days)

    # 1. Load encrypted tokens
    store = GarminCredentialStore(settings)
    tokens = store.load_tokens(user_id)
    if tokens is None:
        _mark_sync_error(settings, user_id, "No stored credentials", reauth=True)
        raise BackfillError("No stored Garmin credentials for user")

    # 2. Restore garth client
    try:
        client = _restore_garth_client(tokens)
    except Exception as exc:
        _mark_sync_error(settings, user_id, f"Token restore failed: {exc}", reauth=True)
        raise BackfillError(f"Failed to restore Garmin session: {exc}") from exc

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # 3. Fetch activities
    _update_backfill_progress(settings, user_id, {
        "status": "fetching_activities",
        "percent": 10,
    })

    try:
        activities = _fetch_activities(client, start_date, end_date)
    except TokenExpiredError as exc:
        _mark_sync_error(settings, user_id, str(exc), reauth=True)
        raise

    activity_count = _upsert_activities(settings, user_id, activities)
    log.info("backfill.activities_done", user_id=user_id, count=activity_count)

    # 4. Fetch daily metrics (day by day)
    _update_backfill_progress(settings, user_id, {
        "status": "fetching_metrics",
        "percent": 40,
    })

    all_metrics: list[dict[str, Any]] = []
    total_days = (end_date - start_date).days + 1

    for i in range(total_days):
        target = start_date + timedelta(days=i)
        metrics = _fetch_daily_metrics(client, target)
        if metrics:
            all_metrics.append(metrics)

        # Update progress periodically (every 10 days)
        if i > 0 and i % 10 == 0:
            pct = 40 + int((i / total_days) * 50)
            _update_backfill_progress(settings, user_id, {
                "status": "fetching_metrics",
                "percent": pct,
                "days_processed": i,
                "days_total": total_days,
            })

    metrics_count = _upsert_daily_metrics(settings, user_id, all_metrics)
    log.info("backfill.metrics_done", user_id=user_id, count=metrics_count)

    # 5. Mark complete
    _mark_sync_complete(settings, user_id)

    summary = {
        "activities": activity_count,
        "daily_metrics": metrics_count,
        "days": days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    log.info("backfill.complete", user_id=user_id, **summary)
    return summary
