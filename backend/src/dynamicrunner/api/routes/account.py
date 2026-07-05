"""Account management routes — deletion, export."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from dynamicrunner.config import get_settings
from dynamicrunner.gdpr import cancel_deletion, request_deletion

router = APIRouter(prefix="/account", tags=["account"])


@router.post("/delete")
def delete_account(request: Request) -> dict[str, Any]:
    """Request account deletion (30-day grace period)."""
    uid: str = request.state.uid
    settings = get_settings()
    return request_deletion(settings, uid)


@router.post("/cancel-delete")
def cancel_account_deletion(request: Request) -> dict[str, str]:
    """Cancel a pending account deletion."""
    uid: str = request.state.uid
    settings = get_settings()
    return cancel_deletion(settings, uid)
