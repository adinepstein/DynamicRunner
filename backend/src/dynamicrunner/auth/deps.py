from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dynamicrunner.auth.jwt import JwtVerificationError, SupabaseJwtVerifier, VerifiedToken
from dynamicrunner.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


def get_jwt_verifier(settings: Annotated[Settings, Depends(get_settings)]) -> SupabaseJwtVerifier:
    if not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SUPABASE_URL is not configured",
        )
    return SupabaseJwtVerifier.from_supabase_url(
        settings.supabase_url,
        audience=settings.supabase_jwt_audience,
    )


def get_verified_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[SupabaseJwtVerifier, Depends(get_jwt_verifier)],
) -> VerifiedToken:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return verifier.verify(credentials.credentials)
    except JwtVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_uid(token: Annotated[VerifiedToken, Depends(get_verified_token)]) -> str:
    return token.sub


def get_optional_uid(request: Request) -> str | None:
    uid = getattr(request.state, "uid", None)
    return uid if isinstance(uid, str) else None
