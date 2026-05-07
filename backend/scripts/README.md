# DynamicRunner — Standalone scripts

One-off scripts used during development. None of these are deployed; they exist so we can validate external dependencies (Garmin, Gemini, Garmin push) before committing to the full FastAPI service.

## `garmin_poc.py` — Phase 2.1

Logs into Garmin Connect, handles MFA, persists OAuth tokens locally, and prints the last 7 days of activities + daily metrics + HRV.

### Important context

**`garth` was deprecated on 2026-03-27** — Garmin's Cloudflare layer broke the default mobile auth path.

The primary PoC path now:

1. **Swaps garth's HTTP session** for `curl_cffi.requests.Session(impersonate="chrome131")` so the TLS handshake matches real Chrome (JA3/JA4), not Python `requests`.
2. Sets a consistent Chrome User-Agent on `client.sess.headers`.
3. Uses a randomized **30–45 second pre-login delay** before submitting credentials (Cloudflare WAF mitigation).

If login still returns **429**, run **`garmin_poc_playwright.py`** first (real Chromium → CAS ticket → garth token exchange → same `.garth_tokens/` cache). Then run `garmin_poc.py` again — it resumes without logging in.

See PRD Section 16 and threat-model T6 for the full fallback ladder.

## `garmin_poc_playwright.py` — Phase 2.1a (when curl_cffi login fails)

Opens a real Chromium window (Playwright), completes Garmin SSO in the browser, extracts the `ticket=ST-...` from the redirect URL, then calls garth's `_complete_login(ticket, client)` to obtain OAuth tokens and saves them to `./.garth_tokens/`.

**Note:** the ticket exchange step must use garth's default `requests` session, not `curl_cffi` — `GarminOAuth1Session` mounts adapters from `parent.adapters['https://']`, which only exists on a standard `requests.Session`.

**401 on `preauthorized`:** garth's stock flow passes `login-url` for the **Android** app. The Playwright sign-in uses **`service=https://sso.garmin.com/sso/embed`**. The CAS ticket is tied to that service; `garmin_poc_playwright.py` calls `preauthorized` with `login-url=https://sso.garmin.com/sso/embed` so validation succeeds.

### One-time browser install

After `pip install -r requirements.txt`:

```bash
playwright install chromium
```

### Run

```bash
python garmin_poc_playwright.py                 # headed (recommended first time)
python garmin_poc_playwright.py --headless      # CI / unattended

python garmin_poc.py                              # uses tokens from Playwright step
```

If Cloudflare shows a captcha in the headed window, solve it manually — the script continues once the redirect with `ticket=` appears.

Debug screenshots are written as `playwright_debug_*.png` on timeouts.

### Setup

```bash
cd backend/scripts
python -m venv .venv
source .venv/bin/activate
pip install --index-url https://pypi.org/simple -r requirements.txt
```

> The `--index-url` override is needed if your machine is configured to use a private package index (e.g. an AWS CodeArtifact repo from a company laptop). Drop it on a clean machine.

### Run

Interactive (prompts for email + password + MFA):

```bash
python garmin_poc.py
```

Or with environment variables (skips the email/password prompts; MFA still interactive):

```bash
GARMIN_EMAIL=you@example.com GARMIN_PASSWORD='...' python garmin_poc.py
```

After the first successful login, OAuth tokens are cached at `./.garth_tokens/`. Subsequent runs reuse them — no re-login needed unless tokens expire or you force it with:

```bash
rm -rf .garth_tokens
```

### What success looks like

```
DynamicRunner - Garmin Connect PoC
Domain: garmin.com (global; serves Israel users with no override needed)
User-Agent override active (Cloudflare bypass): Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...
Garmin email: ...
Garmin password: ...
Garmin MFA code (from email or SMS): ...
Logged in as your-username. Tokens cached at .garth_tokens

Profile: username=your-username  id=12345  display_name=Your Name

=== Activities 2026-04-22 -> 2026-04-28 ===
  started                 type                dist      time        pace     avgHR  TE_aer
  2026-04-22T18:30:00     running              8.42km     46:12     5:29/km    148   3.2
  2026-04-25T07:15:00     running             14.21km   1:18:45     5:32/km    152   3.8
  ...

=== Daily metrics (7 days ending 2026-04-28) ===
  date          steps   rhr  sleep_h  bb_high  stress   hrv
  2026-04-22    11423    52      7.4       95      28    44
  2026-04-23     8910    51      6.9       88      32    41
  ...
```

### Acceptance criteria (from TODO 2.1)

- [ ] Works against a real Israel-based Garmin account.
- [ ] Pulls 7 days of activities + daily metrics + HRV in <30 seconds (excluding interactive prompts).
- [ ] Token cache works — second run skips the login flow.
- [ ] MFA code is accepted on first try when present.
- [ ] No credentials are written to disk anywhere except the encrypted-by-Garmin OAuth tokens (verify with `grep -r your-password .garth_tokens` returning nothing).

### Things to verify against the Garmin Connect website

After running, log into [connect.garmin.com](https://connect.garmin.com) and spot-check:

- Activities count + distance + average HR for each run match.
- Daily steps, RHR, body battery high, sleep duration, and HRV last-night-avg match.
- Time zones look right (the script prints `startTimeLocal`).

### What this PoC does *not* yet do

- It doesn't push a structured workout to the watch (Phase 5.2).
- It doesn't persist anything in DynamoDB or any AWS service (Phase 2.4 onwards).
- It doesn't encrypt the OAuth tokens with KMS — they're plain on disk for the PoC. This is fine because nothing else lives in this folder; the folder is gitignored. **Never copy `.garth_tokens/` to a shared location.**
