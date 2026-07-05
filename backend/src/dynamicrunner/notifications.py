"""Push notification service using FCM HTTP v1.

Sends notifications to users for:
- Daily morning briefing (06:30 local)
- Missed workout reminder
- Weekly review summary
- Re-auth prompt
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from dynamicrunner.config import Settings

log = structlog.get_logger(__name__)

FCM_V1_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"


def send_push(
    settings: Settings,
    fcm_token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    category: str = "general",
) -> bool:
    """Send a push notification via FCM HTTP v1.

    Returns True if delivery was accepted.
    """
    if not getattr(settings, "fcm_project_id", None):
        log.warning("push.skipped", reason="no FCM project configured")
        return False

    access_token = _get_access_token(settings)
    if not access_token:
        log.error("push.auth_failed")
        return False

    url = FCM_V1_URL.format(project_id=settings.fcm_project_id)
    message: dict[str, Any] = {
        "message": {
            "token": fcm_token,
            "notification": {
                "title": title,
                "body": body,
            },
            "android": {
                "priority": "high",
                "notification": {
                    "channel_id": category,
                },
            },
            "data": data or {},
        }
    }

    try:
        resp = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=message,
            timeout=10,
        )
        if resp.status_code == 200:
            log.info("push.sent", category=category)
            return True
        log.warning("push.failed", status=resp.status_code, body=resp.text[:200])
        return False
    except Exception as exc:
        log.error("push.error", error=str(exc))
        return False


def send_morning_briefing(
    settings: Settings,
    fcm_token: str,
    workout_title: str,
    workout_type: str,
) -> bool:
    """Send the daily morning workout briefing."""
    return send_push(
        settings,
        fcm_token,
        title="Today's Workout",
        body=f"{workout_title} — tap to see the details",
        data={"route": "/today", "type": workout_type},
        category="morning_briefing",
    )


def send_missed_workout_reminder(
    settings: Settings,
    fcm_token: str,
    workout_title: str,
) -> bool:
    """Send a missed workout reminder with options."""
    return send_push(
        settings,
        fcm_token,
        title="Missed Workout",
        body=f"You missed '{workout_title}'. It's been moved to tomorrow.",
        data={"route": "/today", "action": "missed"},
        category="missed_workout",
    )


def send_weekly_summary(
    settings: Settings,
    fcm_token: str,
    summary: str,
) -> bool:
    """Send the weekly review summary notification."""
    return send_push(
        settings,
        fcm_token,
        title="Weekly Review",
        body=summary,
        data={"route": "/changes"},
        category="weekly_review",
    )


def send_reauth_prompt(
    settings: Settings,
    fcm_token: str,
) -> bool:
    """Prompt user to re-authenticate Garmin."""
    return send_push(
        settings,
        fcm_token,
        title="Garmin Reconnect Needed",
        body="Your Garmin connection expired. Tap to reconnect.",
        data={"route": "/settings", "action": "reauth"},
        category="reauth",
    )


def _get_access_token(settings: Settings) -> str | None:
    """Get OAuth2 access token for FCM using service account credentials.

    In production, this uses the Google Auth library with the service
    account JSON. For the POC, we support a pre-configured token or
    the google-auth library if available.
    """
    # Check if a static token is configured (for dev/testing)
    fcm_token = getattr(settings, "fcm_access_token", None)
    if fcm_token:
        return fcm_token

    # Try using google-auth library
    try:
        from google.oauth2 import service_account  # type: ignore[import-untyped]
        from google.auth.transport.requests import Request as AuthRequest  # type: ignore[import-untyped]

        credentials = service_account.Credentials.from_service_account_file(
            getattr(settings, "fcm_service_account_path", ""),
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )
        credentials.refresh(AuthRequest())
        return credentials.token
    except Exception as exc:
        log.warning("push.google_auth_failed", error=str(exc))
        return None
