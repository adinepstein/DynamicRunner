"""DynamicRunner Phase 2.1a - Playwright-based Garmin login fallback.

When curl_cffi-based login fails (IP penalty, Cloudflare tightening,
behavioral fingerprinting, etc.), this script uses a real Chromium
browser via Playwright to perform the SSO login, captures the CAS
service ticket from the post-login redirect, and exchanges it for
OAuth tokens via garth's SSO helpers.

The resulting tokens are saved to the same ./.garth_tokens/ directory
that garmin_poc.py reads, so after a successful Playwright login the
main script will resume the session and pull data with no extra login.

Setup (one-time):

    cd backend/scripts
    source .venv/bin/activate
    pip install --index-url https://pypi.org/simple playwright
    playwright install chromium

Usage:

    python garmin_poc_playwright.py              # headed (recommended first run)
    python garmin_poc_playwright.py --headless

    python garmin_poc.py                       # pulls activities/metrics using saved tokens
"""

from __future__ import annotations

import argparse
import os
import re
import time
import sys
import warnings
from getpass import getpass
from pathlib import Path
from urllib.parse import parse_qs, urlencode

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    import garth
    from garth.auth_tokens import OAuth1Token
    from garth.exc import GarthException
    from garth.sso import (
        OAUTH_USER_AGENT,
        GarminOAuth1Session,
        SSO_PAGE_HEADERS,
        exchange,
    )

from playwright.sync_api import Frame
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

TOKEN_DIR = Path(__file__).parent / ".garth_tokens"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

SSO = "https://sso.garmin.com/sso"
SSO_EMBED = f"{SSO}/embed"
SIGNIN_URL = f"{SSO}/signin?" + urlencode(
    {
        "id": "gauth-widget",
        "embedWidget": "true",
        "gauthHost": SSO,
        "service": SSO_EMBED,
        "source": SSO_EMBED,
        "redirectAfterAccountLoginUrl": SSO_EMBED,
        "redirectAfterAccountCreationUrl": SSO_EMBED,
    }
)

USERNAME_SELECTOR = 'input[name="username"], input#email-field'
PASSWORD_SELECTOR = 'input[name="password"], input#password-field'
LOGIN_BUTTON_SELECTOR = '#login-btn-signin, button[data-testid="g__button"]'
MFA_INPUT_SELECTOR = (
    'input[name="mfa-code"], '
    'input#mfa-code-input, '
    'input[autocomplete="one-time-code"]'
)
MFA_SUBMIT_SELECTOR = (
    'button[data-testid="g__button"][type="submit"], '
    'button[type="submit"]'
)
TICKET_URL_PATTERN = "**/embed?ticket=*"

# SSO embed often loads username/password inside an iframe (`gauth-widget`).
# Filling top-level inputs misses the real form and never navigates to `?ticket=`.
POST_LOGIN_TIMEOUT_MS = 120_000


def _find_frame_with_visible_first(
    page: Page, selector: str, *, timeout_ms: int
) -> tuple[Frame, object]:
    """First frame where ``selector`` matches at least one visible element."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                loc = frame.locator(selector).first
                if loc.count() == 0:
                    continue
                loc.wait_for(state="visible", timeout=2000)
                return frame, loc
            except PWTimeoutError as exc:
                last_exc = exc
                continue
            except Exception as exc:
                last_exc = exc
                continue
        page.wait_for_timeout(400)
    raise PWTimeoutError(
        f"Timed out waiting for visible {selector!r} in any frame."
    ) from last_exc


def _page_has_ticket_url(page: Page) -> bool:
    u = page.url
    return "ticket=" in u and ("embed" in u or "ST-" in u or "sso.garmin.com" in u)


def _wait_ticket_mfa_or_error(
    page: Page, *, timeout_ms: int
) -> tuple[str, Frame | str | None]:
    """Return ``('ticket', None)``, ``('mfa', frame)``, or ``('error', message)``."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if _page_has_ticket_url(page):
            return "ticket", None

        for frame in page.frames:
            try:
                mloc = frame.locator(MFA_INPUT_SELECTOR).first
                if mloc.count() == 0:
                    continue
                mloc.wait_for(state="visible", timeout=600)
                return "mfa", frame
            except PWTimeoutError:
                continue
            except Exception:
                continue

        for frame in page.frames:
            try:
                err = frame.locator(
                    ".error, .alert-danger, .alert, [role='alert']"
                ).first
                if err.count() == 0:
                    continue
                if not err.is_visible():
                    continue
                txt = (err.inner_text(timeout=800) or "").strip()
                if len(txt) >= 3:
                    return "error", txt
            except Exception:
                continue

        page.wait_for_timeout(350)

    raise PWTimeoutError("post_login_poll")


def get_credentials() -> tuple[str, str]:
    email = os.environ.get("GARMIN_EMAIL") or input("Garmin email: ").strip()
    password = os.environ.get("GARMIN_PASSWORD") or getpass("Garmin password: ")
    if not email or not password:
        sys.exit("Email and password are required.")
    return email, password


def _save_screenshot(page: Page, name: str) -> Path:
    path = Path(__file__).parent / f"playwright_debug_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"  Saved screenshot: {path}")
    except Exception as exc:
        print(f"  (could not save screenshot {name}: {exc})")
    return path


def get_ticket_via_playwright(email: str, password: str, *, headless: bool) -> str:
    print(f"Launching Chromium ({'headless' if headless else 'headed'})...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = ctx.new_page()

        try:
            page.goto(SIGNIN_URL, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=25_000)
            except PWTimeoutError:
                pass
            login_frame, _ = _find_frame_with_visible_first(
                page, USERNAME_SELECTOR, timeout_ms=30_000
            )
        except PWTimeoutError:
            _save_screenshot(page, "signin_load_timeout")
            browser.close()
            sys.exit(
                "Timed out loading Garmin sign-in. The page may have served a "
                "Cloudflare challenge. See playwright_debug_signin_load_timeout.png."
            )

        print("Filling credentials (inside SSO iframe if present)...")
        login_frame.locator(USERNAME_SELECTOR).first.fill(email)
        login_frame.locator(PASSWORD_SELECTOR).first.fill(password)
        login_frame.locator(LOGIN_BUTTON_SELECTOR).first.click()

        try:
            status, extra = _wait_ticket_mfa_or_error(
                page, timeout_ms=POST_LOGIN_TIMEOUT_MS
            )
        except PWTimeoutError:
            _save_screenshot(page, "post_credential_timeout")
            current_url = page.url
            browser.close()
            sys.exit(
                f"Timed out after submitting credentials ({POST_LOGIN_TIMEOUT_MS // 1000}s). "
                f"Current URL: {current_url}\n"
                "The real login form may still be inside an iframe, or Garmin showed "
                "Cloudflare / captcha (complete it in the browser if headed, then re-run). "
                "See playwright_debug_post_credential_timeout.png."
            )

        if status == "error":
            _save_screenshot(page, "login_error_banner")
            browser.close()
            sys.exit(f"Garmin sign-in error: {extra}")

        if status == "mfa":
            mfa_frame = extra
            assert isinstance(mfa_frame, Frame)
            mfa_input = mfa_frame.locator(MFA_INPUT_SELECTOR).first
            if not mfa_input.is_visible():
                _save_screenshot(page, "no_ticket_no_mfa")
                browser.close()
                sys.exit(
                    "MFA branch but MFA field not visible. "
                    "Check playwright_debug_no_ticket_no_mfa.png."
                )
            mfa_code = input("Garmin MFA code (from email or SMS): ").strip()
            mfa_input.fill(mfa_code)
            try:
                mfa_frame.locator(MFA_SUBMIT_SELECTOR).first.click()
            except Exception:
                mfa_input.press("Enter")
            try:
                page.wait_for_url(TICKET_URL_PATTERN, timeout=120_000)
            except PWTimeoutError:
                _save_screenshot(page, "mfa_timeout")
                browser.close()
                sys.exit(
                    "Timed out waiting for ticket after MFA submission. "
                    "Check playwright_debug_mfa_timeout.png — wrong or expired "
                    "MFA code, or extra challenge in the browser."
                )

        ticket_url = page.url
        browser.close()

    match = re.search(r"[?&]ticket=(ST-[^&\s]+)", ticket_url)
    if not match:
        sys.exit(f"No CAS ticket in URL: {ticket_url}")
    return match.group(1)


def get_oauth1_token_web_embed(ticket: str, client: garth.Client) -> OAuth1Token:
    """OAuth preauthorized call with login-url matching the browser SSO service.

    garth's built-in ``get_oauth1_token`` hardcodes
    ``login-url=https://mobile.integration.garmin.com/gcm/android``.
    Playwright uses ``service=https://sso.garmin.com/sso/embed`` (see
    ``SIGNIN_URL``). CAS validates the ticket against *that* service; using
    the Android login-url produces **401 Unauthorized**.
    """
    sess = GarminOAuth1Session(parent=client.sess)
    url = f"https://connectapi.{client.domain}/oauth-service/oauth/preauthorized"
    resp = sess.get(
        url,
        params={
            "ticket": ticket,
            "login-url": SSO_EMBED,
            "accepts-mfa-tokens": "true",
        },
        headers=OAUTH_USER_AGENT,
        timeout=client.timeout,
    )
    resp.raise_for_status()
    parsed = parse_qs(resp.text)
    token = {k: v[0] for k, v in parsed.items()}
    return OAuth1Token(domain=client.domain, **token)  # type: ignore[arg-type]


def complete_login_playwright(ticket: str, client: garth.Client):
    """Mirror of garth.sso._complete_login but OAuth step uses web embed login-url."""
    try:
        client.get(
            "sso",
            "/portal/sso/embed",
            headers={**SSO_PAGE_HEADERS, "Sec-Fetch-Site": "same-origin"},
            referrer=True,
        )
    except GarthException:
        pass

    oauth1 = get_oauth1_token_web_embed(ticket, client)
    oauth2 = exchange(oauth1, client, login=True)
    return oauth1, oauth2


def exchange_and_save(ticket: str) -> None:
    print("Exchanging CAS ticket for OAuth tokens via garth...")
    # Keep garth's default `requests.Session` (do not swap in curl_cffi here).
    # `GarminOAuth1Session` copies `parent.adapters['https://']` from the
    # parent session; curl_cffi's Session has no `.adapters` and crashes.
    # Playwright already cleared Cloudflare; OAuth preauthorized + exchange
    # calls use garth's own OAuth1 session with standard requests adapters.
    client = garth.Client()
    # garth.Client never initializes last_resp in __init__. _complete_login's
    # first HTTP call is client.get(..., referrer=True); garth/http.request()
    # evaluates `if referrer is True and self.last_resp` before the request runs,
    # which raises AttributeError if last_resp was never set. Prime it so the
    # first GET skips the Referer header (None is falsy) instead of crashing.
    client.last_resp = None  # type: ignore[assignment]
    oauth1, oauth2 = complete_login_playwright(ticket, client)
    client.configure(oauth1_token=oauth1, oauth2_token=oauth2)
    TOKEN_DIR.mkdir(exist_ok=True)
    client.dump(str(TOKEN_DIR))
    print(f"\nLogged in as {client.username}.")
    print(f"Tokens saved to {TOKEN_DIR}.")
    print("\nNext step: run `python garmin_poc.py` to pull recent activities,")
    print("daily metrics, and HRV. It will resume the session from these tokens.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium without a visible window. Default is headed.",
    )
    args = parser.parse_args()

    print("DynamicRunner - Garmin Connect PoC (Playwright fallback)")
    email, password = get_credentials()
    ticket = get_ticket_via_playwright(email, password, headless=args.headless)
    print(f"Captured CAS ticket: {ticket[:30]}...")
    exchange_and_save(ticket)


if __name__ == "__main__":
    main()
