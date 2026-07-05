"""Push structured workouts to Garmin Connect.

Uses garth + curl_cffi to upload a structured workout and returns
the Garmin workout ID for linking back to our workout record.
"""

from __future__ import annotations

import json
import warnings
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
from dynamicrunner.garmin.workout_mapper import map_workout_to_garmin

log = structlog.get_logger(__name__)

IMPERSONATE_TARGET = "chrome131"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _make_session() -> curl_requests.Session:
    sess = curl_requests.Session(impersonate=IMPERSONATE_TARGET)
    sess.headers["User-Agent"] = USER_AGENT
    return sess


def _restore_client(tokens: GarminTokens) -> garth.Client:
    """Restore garth client from stored tokens."""
    client = garth.Client()
    raw = tokens.raw
    blob_str = raw.get("__blob")
    if blob_str:
        import tempfile
        from pathlib import Path

        blob = json.loads(blob_str)
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


def push_workout_to_garmin(
    settings: Settings,
    user_id: str,
    workout_id: str,
    workout_payload: dict[str, Any],
) -> str | None:
    """Upload a structured workout to Garmin Connect.

    Args:
        settings: App settings.
        user_id: The user's ID.
        workout_id: Our internal workout ID (for linking).
        workout_payload: The workout payload from our schema.

    Returns:
        The Garmin workoutId string if successful, None on failure.
    """
    log.info("garmin.push_workout_start", user_id=user_id, workout_id=workout_id)

    # Load credentials
    store = GarminCredentialStore(settings)
    tokens = store.load_tokens(user_id)
    if tokens is None:
        log.warning("garmin.push_no_credentials", user_id=user_id)
        return None

    # Restore client
    try:
        client = _restore_client(tokens)
    except Exception as exc:
        log.error("garmin.push_restore_failed", user_id=user_id, error=str(exc))
        return None

    # Map to Garmin format
    garmin_payload = map_workout_to_garmin(workout_payload)

    # Upload via Garmin Connect API
    try:
        response = client.connectapi(
            "/workout-service/workout",
            method="POST",
            json=garmin_payload,
        )
    except (GarthHTTPError, CurlCffiHTTPError) as exc:
        log.error("garmin.push_upload_failed", user_id=user_id, error=str(exc))
        return None

    if not response or not isinstance(response, dict):
        log.warning("garmin.push_unexpected_response", user_id=user_id, response=response)
        return None

    garmin_workout_id = str(response.get("workoutId", ""))
    if not garmin_workout_id:
        log.warning("garmin.push_no_id_returned", user_id=user_id)
        return None

    # Update our workout record with the Garmin ID
    _update_workout_garmin_id(settings, user_id, workout_id, garmin_workout_id)

    log.info(
        "garmin.push_workout_success",
        user_id=user_id,
        workout_id=workout_id,
        garmin_workout_id=garmin_workout_id,
    )
    return garmin_workout_id


def _update_workout_garmin_id(
    settings: Settings, user_id: str, workout_id: str, garmin_workout_id: str
) -> None:
    """Store the Garmin workout ID on our workout record."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # We need to update the payload jsonb to include garminWorkoutId
    # Using Postgres jsonb concatenation via RPC or direct patch
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
        params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}", "select": "payload"},
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return

    payload = rows[0].get("payload", {})
    payload["garminWorkoutId"] = garmin_workout_id
    payload["status"] = "planned"

    httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
        params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"},
        headers=headers,
        json={"payload": payload},
        timeout=10,
    )
