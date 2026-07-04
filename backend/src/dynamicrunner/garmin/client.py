"""GarminClient — Protocol + curl_cffi/garth implementation for FastAPI service.

Encapsulates Garmin Connect login (including MFA), token persistence, and
basic Connect API calls. The PoC scripts (backend/scripts/) validated the
approach; this module wraps it for production use in the API.
"""

from __future__ import annotations

import json
import random
import time
import warnings
from dataclasses import dataclass
from enum import Enum

import structlog

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    import garth
    from garth.exc import GarthHTTPError

from curl_cffi import requests as curl_requests
from curl_cffi.requests.exceptions import HTTPError as CurlCffiHTTPError

log = structlog.get_logger(__name__)

IMPERSONATE_TARGET = "chrome131"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
PRE_LOGIN_DELAY_RANGE_S = (3, 8)

LOGIN_HTTP_ERRORS = (GarthHTTPError, CurlCffiHTTPError)


class LoginStatus(str, Enum):
    SUCCESS = "success"
    MFA_REQUIRED = "mfa_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"
    SERVER_ERROR = "server_error"


@dataclass
class LoginResult:
    status: LoginStatus
    tokens_json: bytes | None = None
    garmin_user_id: str | None = None
    mfa_session: bytes | None = None
    error_message: str | None = None


@dataclass
class MfaResult:
    status: LoginStatus
    tokens_json: bytes | None = None
    garmin_user_id: str | None = None
    error_message: str | None = None


def _make_session() -> curl_requests.Session:
    sess = curl_requests.Session(impersonate=IMPERSONATE_TARGET)
    sess.headers["User-Agent"] = USER_AGENT
    return sess


def _serialize_client(client: garth.Client) -> bytes:
    """Serialize garth client tokens to JSON bytes for encrypted storage."""
    data = {
        "oauth1_token": getattr(client, "oauth1_token", None),
        "oauth1_token_secret": getattr(client, "oauth1_token_secret", None),
        "oauth_consumer": client.oauth_consumer.__dict__ if hasattr(client, "oauth_consumer") else None,
        "domain": client.domain,
    }
    if hasattr(client, "garth_tokens"):
        data["garth_tokens"] = client.garth_tokens
    else:
        # garth stores tokens as oauth1/oauth2 token pairs
        if client.oauth1_token:
            data["oauth1"] = {
                "oauth_token": client.oauth1_token.token,
                "oauth_token_secret": client.oauth1_token.token_secret,
            }
        if client.oauth2_token:
            data["oauth2"] = client.oauth2_token.__dict__
    return json.dumps(data, default=str, separators=(",", ":")).encode()


def _serialize_for_mfa(client: garth.Client) -> bytes:
    """Serialize partial client state for MFA continuation."""
    data = {
        "domain": client.domain,
        "_partial": True,
    }
    return json.dumps(data, default=str, separators=(",", ":")).encode()


def login(email: str, password: str) -> LoginResult:
    """Attempt Garmin login. Returns tokens on success or MFA session if required."""
    client = garth.Client()
    # garth's login requires a standard requests.Session (uses .adapters/.mount)
    # We do NOT swap in curl_cffi until after login succeeds.

    delay_s = random.uniform(*PRE_LOGIN_DELAY_RANGE_S)
    log.info("garmin.login.delay", delay_s=round(delay_s, 1))
    time.sleep(delay_s)

    mfa_needed = False

    def mfa_callback() -> str:
        nonlocal mfa_needed
        mfa_needed = True
        raise _MfaInterrupt()

    try:
        client.login(email, password, prompt_mfa=mfa_callback)
    except _MfaInterrupt:
        mfa_session = _serialize_for_mfa(client)
        return LoginResult(
            status=LoginStatus.MFA_REQUIRED,
            mfa_session=mfa_session,
        )
    except LOGIN_HTTP_ERRORS as exc:
        return _classify_login_error(exc)

    # Login succeeded — now swap in curl_cffi for Connect API calls
    client.sess = _make_session()

    tokens_json = _serialize_client(client)
    username = getattr(client, "username", None) or ""
    log.info("garmin.login.success", garmin_user_id=username)

    return LoginResult(
        status=LoginStatus.SUCCESS,
        tokens_json=tokens_json,
        garmin_user_id=username,
    )


def complete_mfa(email: str, password: str, mfa_code: str) -> MfaResult:
    """Complete MFA by re-doing login with the code provided.

    garth doesn't support resuming MFA from a serialized state, so we
    re-login with the code injected via prompt_mfa callback.
    """
    client = garth.Client()
    # Use default requests.Session for login (garth requires .adapters)

    delay_s = random.uniform(1, 3)
    time.sleep(delay_s)

    code_used = False

    def mfa_callback() -> str:
        nonlocal code_used
        if code_used:
            raise _MfaInterrupt()
        code_used = True
        return mfa_code

    try:
        client.login(email, password, prompt_mfa=mfa_callback)
    except _MfaInterrupt:
        return MfaResult(
            status=LoginStatus.INVALID_CREDENTIALS,
            error_message="MFA code rejected or expired",
        )
    except LOGIN_HTTP_ERRORS as exc:
        result = _classify_login_error(exc)
        return MfaResult(
            status=result.status,
            error_message=result.error_message,
        )

    # Login succeeded — swap in curl_cffi for Connect API calls
    client.sess = _make_session()

    tokens_json = _serialize_client(client)
    username = getattr(client, "username", None) or ""
    log.info("garmin.mfa.success", garmin_user_id=username)

    return MfaResult(
        status=LoginStatus.SUCCESS,
        tokens_json=tokens_json,
        garmin_user_id=username,
    )


class _MfaInterrupt(Exception):
    """Internal signal: garth requested MFA code."""


def _classify_login_error(exc: Exception) -> LoginResult:
    msg = str(exc)
    if "401" in msg:
        return LoginResult(
            status=LoginStatus.INVALID_CREDENTIALS,
            error_message="Invalid email or password",
        )
    if "429" in msg:
        return LoginResult(
            status=LoginStatus.RATE_LIMITED,
            error_message="Rate limited by Garmin. Wait and retry.",
        )
    if "403" in msg:
        return LoginResult(
            status=LoginStatus.BLOCKED,
            error_message="Blocked by Cloudflare. Try a different network.",
        )
    return LoginResult(
        status=LoginStatus.SERVER_ERROR,
        error_message=f"Garmin error: {msg}",
    )
