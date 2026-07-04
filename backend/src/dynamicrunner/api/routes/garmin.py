"""FastAPI routes for Garmin login + MFA + backfill."""

from __future__ import annotations

import threading

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from dynamicrunner.config import get_settings
from dynamicrunner.garmin import GarminCredentialStore, GarminTokens
from dynamicrunner.garmin.backfill import BackfillError, run_backfill
from dynamicrunner.garmin.client import LoginStatus, complete_mfa, login

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/garmin", tags=["garmin"])


class GarminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class GarminMfaRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    mfa_code: str = Field(min_length=4, max_length=10)


class GarminLoginResponse(BaseModel):
    status: str
    message: str | None = None
    garmin_user_id: str | None = None


class BackfillResponse(BaseModel):
    status: str
    message: str


class GarminStatusResponse(BaseModel):
    connected: bool
    sync_status: str
    reauth_required: bool
    garmin_user_id: str | None = None
    last_sync_at: str | None = None
    backfill_progress: dict[str, object] | None = None


@router.get("/status", response_model=GarminStatusResponse)
def garmin_status(request: Request) -> GarminStatusResponse:
    """Get current Garmin connection status for the authenticated user."""
    uid: str = request.state.uid
    settings = get_settings()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/garmin_profiles",
        params={"user_id": f"eq.{uid}", "select": "*"},
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()

    if not rows:
        return GarminStatusResponse(
            connected=False,
            sync_status="disconnected",
            reauth_required=False,
        )

    row = rows[0]
    return GarminStatusResponse(
        connected=row.get("sync_status") != "disconnected",
        sync_status=row.get("sync_status", "disconnected"),
        reauth_required=row.get("reauth_required", False),
        garmin_user_id=row.get("garmin_user_id"),
        last_sync_at=row.get("last_sync_at"),
        backfill_progress=row.get("backfill_progress"),
    )


@router.post("/login", response_model=GarminLoginResponse)
def garmin_login(body: GarminLoginRequest, request: Request) -> GarminLoginResponse:
    """Initiate Garmin login. Returns success or MFA required."""
    uid: str = request.state.uid

    result = login(body.email, body.password)

    if result.status == LoginStatus.SUCCESS:
        _store_tokens(uid, result.tokens_json, result.garmin_user_id)
        _update_garmin_profile(uid, result.garmin_user_id, sync_status="ok")
        return GarminLoginResponse(
            status="success",
            garmin_user_id=result.garmin_user_id,
        )

    if result.status == LoginStatus.MFA_REQUIRED:
        return GarminLoginResponse(
            status="mfa_required",
            message="Enter your MFA code from email or authenticator app.",
        )

    if result.status == LoginStatus.INVALID_CREDENTIALS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.error_message or "Invalid Garmin credentials",
        )

    if result.status == LoginStatus.RATE_LIMITED:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result.error_message or "Rate limited by Garmin",
        )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=result.error_message or "Garmin login failed",
    )


@router.post("/mfa", response_model=GarminLoginResponse)
def garmin_mfa(body: GarminMfaRequest, request: Request) -> GarminLoginResponse:
    """Complete MFA-protected Garmin login."""
    uid: str = request.state.uid

    result = complete_mfa(body.email, body.password, body.mfa_code)

    if result.status == LoginStatus.SUCCESS:
        _store_tokens(uid, result.tokens_json, result.garmin_user_id)
        _update_garmin_profile(uid, result.garmin_user_id, sync_status="ok")
        return GarminLoginResponse(
            status="success",
            garmin_user_id=result.garmin_user_id,
        )

    if result.status == LoginStatus.INVALID_CREDENTIALS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.error_message or "MFA code rejected",
        )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=result.error_message or "Garmin MFA failed",
    )


@router.post("/backfill", response_model=BackfillResponse)
def garmin_backfill(request: Request) -> BackfillResponse:
    """Trigger a 90-day backfill for the authenticated user.

    Runs the backfill in a background thread so the HTTP response returns
    immediately. Progress is written to garmin_profiles.backfill_progress.
    """
    uid: str = request.state.uid
    settings = get_settings()

    # Quick check: user has stored credentials
    store = GarminCredentialStore(settings)
    tokens = store.load_tokens(uid)
    if tokens is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Garmin credentials stored. Please link your account first.",
        )

    def _run() -> None:
        try:
            run_backfill(settings, uid)
        except BackfillError as exc:
            log.error("backfill.failed", user_id=uid, error=str(exc))
        except Exception as exc:
            log.exception("backfill.unexpected_error", user_id=uid, error=str(exc))

    thread = threading.Thread(target=_run, daemon=True, name=f"backfill-{uid[:8]}")
    thread.start()

    return BackfillResponse(
        status="started",
        message="Backfill started. Check garmin_profiles for progress.",
    )


class DisconnectResponse(BaseModel):
    status: str
    deleted_credentials: bool
    deleted_activities: int
    deleted_metrics: int


@router.delete("", response_model=DisconnectResponse)
def garmin_disconnect(request: Request, delete_data: bool = False) -> DisconnectResponse:
    """Disconnect Garmin account.

    Deletes encrypted credentials and marks garmin_profiles as disconnected.
    If delete_data=true, also removes all synced activities and daily_metrics.
    """
    uid: str = request.state.uid
    settings = get_settings()

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    # 1. Delete encrypted credentials
    store = GarminCredentialStore(settings)
    store.delete_tokens(uid)

    # 2. Mark garmin_profiles as disconnected
    httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/garmin_profiles",
        params={"user_id": f"eq.{uid}"},
        headers=headers,
        json={
            "sync_status": "disconnected",
            "reauth_required": False,
            "backfill_progress": None,
            "last_sync_at": None,
        },
        timeout=10,
    )

    deleted_activities = 0
    deleted_metrics = 0

    # 3. Optionally delete synced data
    if delete_data:
        # Count then delete activities
        count_headers = {**headers, "Prefer": "count=exact"}
        resp = httpx.head(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/activities",
            params={"user_id": f"eq.{uid}"},
            headers=count_headers,
            timeout=10,
        )
        content_range = resp.headers.get("content-range", "")
        if "/" in content_range:
            try:
                deleted_activities = int(content_range.split("/")[1])
            except (ValueError, IndexError):
                pass

        httpx.delete(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/activities",
            params={"user_id": f"eq.{uid}"},
            headers=headers,
            timeout=10,
        )

        # Count then delete daily_metrics
        resp = httpx.head(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/daily_metrics",
            params={"user_id": f"eq.{uid}"},
            headers=count_headers,
            timeout=10,
        )
        content_range = resp.headers.get("content-range", "")
        if "/" in content_range:
            try:
                deleted_metrics = int(content_range.split("/")[1])
            except (ValueError, IndexError):
                pass

        httpx.delete(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/daily_metrics",
            params={"user_id": f"eq.{uid}"},
            headers=headers,
            timeout=10,
        )

    log.info(
        "garmin.disconnected",
        user_id=uid,
        delete_data=delete_data,
        activities=deleted_activities,
        metrics=deleted_metrics,
    )

    return DisconnectResponse(
        status="disconnected",
        deleted_credentials=True,
        deleted_activities=deleted_activities,
        deleted_metrics=deleted_metrics,
    )


def _store_tokens(uid: str, tokens_json: bytes | None, garmin_user_id: str | None) -> None:
    if tokens_json is None:
        return
    settings = get_settings()
    store = GarminCredentialStore(settings)
    tokens = GarminTokens(
        oauth1_token=garmin_user_id or "",
        oauth1_token_secret="",
        raw={"__blob": tokens_json.decode()},
    )
    store.store_tokens(uid, tokens)


def _update_garmin_profile(uid: str, garmin_user_id: str | None, sync_status: str) -> None:
    """Upsert garmin_profiles row via Supabase REST."""
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    payload = {
        "user_id": uid,
        "garmin_user_id": garmin_user_id or "",
        "sync_status": sync_status,
    }
    try:
        resp = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/garmin_profiles",
            headers=headers,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.error("garmin_profiles.upsert_failed", user_id=uid, error=str(exc))
