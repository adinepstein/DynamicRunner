from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from dynamicrunner.auth.jwt import JwtVerificationError, SupabaseJwtVerifier
from dynamicrunner.config import Settings
from dynamicrunner.logging_config import generate_request_id

log = structlog.get_logger(__name__)

PUBLIC_PATHS = frozenset({"/healthz", "/docs", "/openapi.json", "/redoc"})
INTERNAL_PREFIX = "/internal/"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Adds request_id to each request and logs request/response with timing."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or generate_request_id()
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        log.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            user_id=getattr(request.state, "uid", None),
        )

        response.headers["X-Request-ID"] = request_id
        return response


class SupabaseAuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        verifier_factory: Callable[[], SupabaseJwtVerifier | None] | None = None,
    ) -> None:
        super().__init__(app)
        self._settings = settings
        self._verifier_factory = verifier_factory

    def _get_verifier(self) -> SupabaseJwtVerifier | None:
        if self._verifier_factory is not None:
            return self._verifier_factory()
        if not self._settings.supabase_url:
            return None
        return SupabaseJwtVerifier.from_supabase_url(
            self._settings.supabase_url,
            audience=self._settings.supabase_jwt_audience,
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in PUBLIC_PATHS or request.url.path.startswith(INTERNAL_PREFIX):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing bearer token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        verifier = self._get_verifier()
        if verifier is None:
            log.warning("auth.skipped", reason="SUPABASE_URL not configured")
            return JSONResponse(
                status_code=503,
                content={"detail": "SUPABASE_URL is not configured"},
            )

        token = auth_header.removeprefix("Bearer ").strip()
        try:
            verified = verifier.verify(token)
        except JwtVerificationError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        request.state.uid = verified.sub
        request.state.jwt_claims = verified.claims
        return await call_next(request)
