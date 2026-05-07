"""DynamicRunner Phase 2.1 - Garmin Connect proof of concept.

Validates that we can log in to Garmin Connect (with MFA) using the
unofficial `garth` library, persist OAuth tokens locally, and pull the
data we need for the MVP: activities, daily metrics, sleep, and HRV
for the last 7 days.

IMPORTANT - garth deprecation status (as of April 2026):
    `garth` was officially deprecated on 2026-03-27 because Garmin's
    Cloudflare layer began TLS-fingerprinting requests with the default
    mobile User-Agent (`GCM-iOS-5.7.2.1`) and rejecting them.

    The community User-Agent-only workaround stopped working for many
    users (429 from Cloudflare even with a current Chrome UA) because
    Cloudflare also fingerprints the TLS handshake itself (JA3/JA4),
    not just headers. The fix that survives this is `curl_cffi`, which
    impersonates a real Chrome client at the TLS layer.

    This script swaps garth's underlying `requests.Session` with a
    `curl_cffi.requests.Session(impersonate="chrome131")`. The session
    APIs are compatible, so garth's login, token refresh, and `connectapi`
    calls all keep working. Confirmed working approach (April 2026) by
    the `garmin-health-data` project.

    If even this stops working, the fallbacks (in order of effort):
      1. Bump the `IMPERSONATE_TARGET` to a newer Chrome version.
      2. Add the longer (90s+) randomized pre-login delay.
      3. Playwright-driven login that captures the OAuth ticket from a
         real Chromium session and hands it to garth for API calls.
      4. Migrate to the official Garmin Health API (partner approval
         required; weeks-to-months lead time).

Region note (Israel users):
    Garmin Connect serves Israel users through its standard global
    domain (`garmin.com`), which is `garth`'s default. There is no
    separate Israel endpoint. Only China users (`garmin.cn`) need a
    domain override via `garth.configure(domain="garmin.cn")`.

Usage:
    cd backend/scripts
    python -m venv .venv
    source .venv/bin/activate
    pip install --index-url https://pypi.org/simple -r requirements.txt
    python garmin_poc.py

Optional environment variables (skip the interactive email/password prompts):
    GARMIN_EMAIL
    GARMIN_PASSWORD

Tokens are cached in ./.garth_tokens/. Delete that folder to force a
fresh login.
"""

from __future__ import annotations

import os
import random
import sys
import time
import warnings
from datetime import date, timedelta
from getpass import getpass
from pathlib import Path
from typing import Any

# Suppress garth's own DeprecationWarning during import; we acknowledge it
# explicitly above and the script still works fine for the PoC.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    import garth
    from garth.exc import GarthHTTPError

from curl_cffi import requests as curl_requests
from curl_cffi.requests.exceptions import HTTPError as CurlCffiHTTPError

# Any HTTP error garth's stack might raise after our session swap.
# We need to catch curl_cffi's HTTPError because garth's `raise_for_status()`
# call propagates the underlying session library's exception class.
LOGIN_HTTP_ERRORS = (GarthHTTPError, CurlCffiHTTPError)

TOKEN_DIR = Path(__file__).parent / ".garth_tokens"

# curl_cffi impersonation target. The string here is matched against
# curl_cffi's BrowserType enum. Bump to a newer Chrome if Cloudflare
# starts rejecting this fingerprint.
IMPERSONATE_TARGET = "chrome131"

# Default UA for chrome131 impersonation is desktop. We override it to a
# desktop Chrome UA so the entire request (TLS + headers + UA) tells
# Cloudflare a consistent story: "I am desktop Chrome 131."
USER_AGENT_FOR_GARTH = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Cloudflare's WAF rate-limits requests that arrive too quickly after
# the initial cookie-priming GET. This randomized delay is the same
# mitigation used by garmin-health-data (April 2026) and reduces 429s.
PRE_LOGIN_DELAY_RANGE_S = (30, 45)


def get_credentials() -> tuple[str, str]:
    email = os.environ.get("GARMIN_EMAIL") or input("Garmin email: ").strip()
    password = os.environ.get("GARMIN_PASSWORD") or getpass("Garmin password: ")
    if not email or not password:
        sys.exit("Email and password are required.")
    return email, password


def mfa_prompt() -> str:
    return input("Garmin MFA code (from email or SMS): ").strip()


def make_impersonating_session() -> curl_requests.Session:
    """Build a curl_cffi session that impersonates Chrome at the TLS layer."""
    sess = curl_requests.Session(impersonate=IMPERSONATE_TARGET)
    # Override the UA so headers match the impersonation target consistently.
    sess.headers["User-Agent"] = USER_AGENT_FOR_GARTH
    return sess


def get_client() -> garth.Client:
    """Resume a saved session if possible, otherwise log in fresh."""
    client = garth.Client()

    # garth's `configure()` always calls `sess.mount("https://", adapter)`.
    # curl_cffi's Session has no `.mount`, so token files MUST be loaded while
    # the default `requests.Session` is still attached. After `load()` succeeds,
    # swap in TLS-impersonating transport for Connect API calls.
    if TOKEN_DIR.exists():
        try:
            client.load(str(TOKEN_DIR))
            client.sess = make_impersonating_session()
            _ = client.username
            print(f"Resumed Garmin session for {client.username}")
            return client
        except Exception as exc:
            print(f"Saved tokens are invalid ({exc!s}); logging in fresh.")

    # Fresh login: impersonate Chrome at TLS for the mobile SSO endpoints.
    client.sess = make_impersonating_session()

    email, password = get_credentials()

    delay_s = random.uniform(*PRE_LOGIN_DELAY_RANGE_S)
    print(f"Waiting {delay_s:.1f}s before submitting credentials (Cloudflare WAF mitigation)...")
    time.sleep(delay_s)

    try:
        client.login(email, password, prompt_mfa=mfa_prompt)
    except LOGIN_HTTP_ERRORS as exc:
        # Try to extract the status code from either exception flavor.
        msg = str(exc)
        status = None
        for code in (401, 403, 429, 500, 502, 503, 504):
            if str(code) in msg:
                status = code
                break
        sys.exit(
            f"\nLogin failed: {exc}\n"
            "\n"
            f"Diagnosis (status={status}):\n"
            "  401 -> wrong username/password (or password change required).\n"
            "  403 -> Cloudflare blocked the request (TLS or behavior fingerprint).\n"
            "  429 -> rate-limited. Two common causes:\n"
            "         (a) IP-level penalty from previous failed attempts. Try a\n"
            "             different network (mobile hotspot or VPN) to confirm.\n"
            "             Garmin's penalty can last 1-24 hours.\n"
            "         (b) The login endpoint requires browser behavior we don't\n"
            "             replicate yet. Escalate to Playwright-driven login\n"
            "             (see TODO 2.1a fallback).\n"
            "  5xx -> Garmin server issue. Wait and retry."
        )

    TOKEN_DIR.mkdir(exist_ok=True)
    client.dump(str(TOKEN_DIR))
    print(f"Logged in as {client.username}. Tokens cached at {TOKEN_DIR}")
    return client


def safe_get(client: garth.Client, path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        return client.connectapi(path, params=params)
    except (GarthHTTPError, CurlCffiHTTPError) as exc:
        # curl_cffi uses its own HTTPError class; garth only wraps `requests.HTTPError`,
        # so Connect API failures surface as CurlCffiHTTPError unless caught here.
        return {"_error": str(exc)}


def fmt_seconds(seconds: float | int | None) -> str:
    if not seconds:
        return "-"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def fmt_pace(distance_m: float | None, duration_s: float | None) -> str:
    if not distance_m or not duration_s:
        return "-"
    sec_per_km = duration_s / (distance_m / 1000.0)
    m, s = divmod(int(sec_per_km), 60)
    return f"{m}:{s:02d}/km"


def print_activities(client: garth.Client, start: date, end: date) -> None:
    print(f"\n=== Activities {start.isoformat()} -> {end.isoformat()} ===")
    activities = safe_get(
        client,
        "/activitylist-service/activities/search/activities",
        params={"limit": 50, "startDate": start.isoformat(), "endDate": end.isoformat()},
    )
    if isinstance(activities, dict) and "_error" in activities:
        print(f"  (error: {activities['_error']})")
        return

    runs = [
        a for a in (activities or [])
        if "running" in (a.get("activityType") or {}).get("typeKey", "").lower()
    ]
    if not runs:
        print("  (no running activities in window)")
        return

    print(f"  {'started':22s}  {'type':18s}  {'dist':>7s}  {'time':>8s}  {'pace':>10s}  {'avgHR':>5s}  {'TE_aer':>6s}")
    for a in runs[:20]:
        started = a.get("startTimeLocal", "?")
        type_key = (a.get("activityType") or {}).get("typeKey", "?")
        dist_m = a.get("distance") or 0
        dur_s = a.get("duration") or 0
        avg_hr = a.get("averageHR")
        te_aer = a.get("aerobicTrainingEffect")
        print(
            f"  {started:22s}  {type_key:18s}  "
            f"{dist_m / 1000:6.2f}km  "
            f"{fmt_seconds(dur_s):>8s}  "
            f"{fmt_pace(dist_m, dur_s):>10s}  "
            f"{avg_hr if avg_hr is not None else '-':>5}  "
            f"{te_aer if te_aer is not None else '-':>6}"
        )


def print_daily_metrics(client: garth.Client, start: date, days: int) -> None:
    print(f"\n=== Daily metrics ({days} days ending {(start + timedelta(days=days - 1)).isoformat()}) ===")
    print(f"  {'date':10s}  {'steps':>6s}  {'rhr':>4s}  {'sleep_h':>7s}  {'bb_high':>7s}  {'stress':>6s}  {'hrv':>4s}")
    for n in range(days):
        d = start + timedelta(days=n)
        # Must use query param `calendarDate`, not path `/daily/{date}` — the latter
        # returns 403 from Connect API (same contract as garth.data.DailySummary.get).
        ds = safe_get(
            client,
            f"/usersummary-service/usersummary/daily/?calendarDate={d.isoformat()}",
        ) or {}
        if isinstance(ds, dict) and "_error" in ds:
            print(f"  {d.isoformat()}  (error: {ds['_error']})")
            continue
        hrv = safe_get(client, f"/hrv-service/hrv/{d.isoformat()}")
        hrv_avg = None
        if isinstance(hrv, dict) and "hrvSummary" in hrv:
            hrv_avg = (hrv.get("hrvSummary") or {}).get("lastNightAvg")

        sleep_sec = ds.get("sleepingSeconds") or 0
        print(
            f"  {d.isoformat()}  "
            f"{ds.get('totalSteps', '-'):>6}  "
            f"{ds.get('restingHeartRate', '-'):>4}  "
            f"{(sleep_sec / 3600):>7.1f}  "
            f"{ds.get('bodyBatteryHighestValue', '-'):>7}  "
            f"{ds.get('averageStressLevel', '-'):>6}  "
            f"{hrv_avg if hrv_avg is not None else '-':>4}"
        )


def diagnose() -> None:
    """Quick check: does Cloudflare let our impersonating session through
    on a non-credential endpoint? If this returns 200 with a `__cf_bm`
    cookie, our TLS impersonation is working and any 429 on /login is
    almost certainly an IP-level penalty (try a different network)."""
    print("Diagnosis mode: testing cookie-priming GET only.\n")
    sess = make_impersonating_session()
    try:
        r = sess.get(
            "https://sso.garmin.com/sso/mobile/sso/en/sign-in",
            params={"clientId": "GCM_ANDROID_DARK"},
            timeout=15,
        )
        print(f"  GET status:  {r.status_code}")
        print(f"  Cookies set: {list(sess.cookies.keys())[:10]}")
        if r.status_code == 200 and any(
            c in sess.cookies for c in ("__cf_bm", "_cfuvid", "__cflb")
        ):
            print("\n  RESULT: TLS impersonation is working. Cloudflare passed our")
            print("  bot check on the GET endpoint. If /login still 429s, the")
            print("  cause is almost certainly an IP-level rate-limit penalty.")
            print("\n  Next step: try the full login from a different network")
            print("  (mobile hotspot or VPN). If that succeeds, we're good.")
            print("  If that also fails, escalate to Playwright (TODO 2.1a fallback).")
        else:
            print("\n  RESULT: TLS impersonation may have stopped working.")
            print("  Try bumping IMPERSONATE_TARGET to chrome133 or chrome136.")
    except Exception as exc:
        print(f"  GET failed: {type(exc).__name__}: {exc}")


def main() -> None:
    if "--diagnose" in sys.argv:
        diagnose()
        return

    print("DynamicRunner - Garmin Connect PoC")
    print("Domain: garmin.com (global; serves Israel users with no override needed)")
    print(f"TLS impersonation: {IMPERSONATE_TARGET}")
    print(f"User-Agent: {USER_AGENT_FOR_GARTH[:70]}...")

    client = get_client()
    profile = client.user_profile or {}
    print(f"\nProfile: username={client.username}  id={profile.get('id', '?')}  "
          f"display_name={profile.get('displayName', '?')}")

    days = 7
    end = date.today()
    start = end - timedelta(days=days - 1)

    print_activities(client, start, end)
    print_daily_metrics(client, start, days)

    print(f"\nPoC complete. Tokens cached at {TOKEN_DIR}")
    print("Delete that folder to force a fresh login next run.")


if __name__ == "__main__":
    main()
