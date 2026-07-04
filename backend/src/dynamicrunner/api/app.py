from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Callable

import structlog
from fastapi import FastAPI

from dynamicrunner.api.middleware import SupabaseAuthMiddleware
from dynamicrunner.api.routes import features, garmin, health, internal, me
from dynamicrunner.auth.jwt import SupabaseJwtVerifier
from dynamicrunner.config import Settings, get_settings
from dynamicrunner.logging_config import configure_logging

log = structlog.get_logger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    verifier_factory: Callable[[], SupabaseJwtVerifier | None] | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(level=resolved_settings.log_level, json_logs=resolved_settings.log_json)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if "YOUR_PROJECT" in resolved_settings.supabase_url:
            log.warning(
                "api.supabase_url_placeholder",
                hint="Set SUPABASE_URL in backend/.env to your real project URL, then restart.",
            )
        log.info(
            "api.startup",
            supabase_configured=bool(resolved_settings.supabase_url),
        )
        yield

    app = FastAPI(title="DynamicRunner API", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(garmin.router)
    app.include_router(features.router)
    app.include_router(internal.router)

    app.add_middleware(
        SupabaseAuthMiddleware,
        settings=resolved_settings,
        verifier_factory=verifier_factory,
    )

    return app
