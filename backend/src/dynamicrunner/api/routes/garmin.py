"""FastAPI routes for Garmin login + MFA."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from dynamicrunner.config import get_settings
from dynamicrunner.garmin import GarminCredentialStore, GarminTokens
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
    import httpx

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
