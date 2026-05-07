# DynamicRunner — Threat Model (POC)

**Version:** 0.3 (Supabase + hosted FastAPI)
**Last updated:** 2026-05-06
**Scope:** POC — Android Flutter app, **Supabase** (Postgres + Auth + optional Realtime), **FastAPI** on **Render/Fly**, encrypted Garmin tokens in Postgres, **FCM HTTP v1** (minimal Firebase credentials only), unofficial Garmin Connect via **`garth`**, **Gemini**. Re-review at Phase 8 (hardening) and after architectural changes.

Prior AWS-specific controls (KMS, Secrets Manager, AppSync, Cognito) are **production migration targets** — see PRD §7 and §14.

## 1. Assets

| # | Asset | Sensitivity |
|---|---|---|
| A1 | User's Garmin email + password (in transit, briefly in backend memory) | **Critical** |
| A2 | User's Garmin OAuth1 + OAuth2 tokens (encrypted at rest in **Postgres**) | **High** |
| A3 | User physiological data (HRV, sleep, activities, etc.) in **Postgres** | **High** |
| A4 | Training plans + agent decisions in **Postgres** | Medium |
| A5 | **Supabase Auth** users & sessions | Critical (managed by Supabase) |
| A6 | **`APP_ENCRYPTION_KEY`** (or Fernet key) in host env — wraps Garmin ciphertext | **Critical** |
| A7 | **Supabase service role key** + **cron shared secret** on the FastAPI host | **Critical** |
| A8 | Gemini API key (env / secrets on host) | Medium |
| A9 | FCM service account / HTTP v1 credentials | Medium |

## 2. Trust boundaries

```
[ Android device ]  --(TLS, Supabase JWT)-->  [ Supabase PostgREST / Realtime ]
       |                                              |
       |                                              v
       |                                        [ Postgres + RLS ]
       |
       ----(TLS, Supabase JWT / cron secret)---->  [ FastAPI ]
                                                          |
                                                          v
                                                   [ Postgres service role ]
                                                   [ garth -> Garmin ]
                                                   [ Gemini API ]
                                                   [ FCM -> device ]
```

The Android device is **untrusted**. Authorization relies on:

1. **Postgres RLS** — rows scoped to `auth.uid()` for client-direct access.
2. **FastAPI** — verifies Supabase JWT (**JWKS**); uses **`sub`** as the only trusted `uid`; cron routes verify a **server secret**, not user JWT.

**Production (`[future-aws]`):** replace Supabase client path with Cognito + API Gateway + IAM-scoped access as needed; **keep** the principle: verified identity + row-level isolation + no secrets in the app.

## 3. Top threats and mitigations

### T1 — Garmin password leak in backend

**Scenario:** Password in FastAPI worker memory; logging or memory-dump exfiltration.

**Likelihood:** Medium. **Impact:** Critical.

**Mitigations:** Same as v0.2: password only in request-local scope; **structlog** redacts `password`, `token`, `secret`; code review on `/garmin/login`; host memory is a managed-provider boundary (Render/Fly).

### T2 — Garmin token theft from Postgres

**Scenario:** Attacker obtains DB backup or SQL injection reads encrypted blob.

**Likelihood:** Low–Medium. **Impact:** High.

**Mitigations:**

- **At rest:** AES-GCM/Fernet ciphertext only; **no plaintext** in logs or analytics.
- **Key separation:** encryption key in **env** / platform secrets — **not** in DB; **`[future-aws]`** move to **KMS envelope encryption + Secrets Manager**.
- **Transport:** TLS to Supabase and to FastAPI.
- **RLS:** anon/authenticated roles cannot `select` token columns if stored in a **server-only table** accessible only via **service role** from FastAPI (preferred) or strict column-level policies.
- **Disconnect:** delete ciphertext rows on disconnect; rotate app key on compromise (documented procedure).

### T3 — Cross-user access (broken RLS or FastAPI bug)

**Scenario:** User B's data read via crafted API or SQL.

**Likelihood:** Medium. **Impact:** High.

**Mitigations:**

- RLS policies **`user_id = auth.uid()`** on all user tables; integration tests with two sessions.
- FastAPI rejects any body/path `uid` ≠ JWT `sub`.
- **`[future-aws]`** Re-run this matrix against Cognito + RDS IAM patterns.

### T4 — Gemini prompt injection via user fields

**Scenario:** Malicious free text in injury notes or check-ins manipulates the model.

**Likelihood:** Medium. **Impact:** Medium.

**Mitigations:** Delimited user text in prompts; guardrails **after** model output; schema max lengths — unchanged from v0.2.

### T5 — Unsafe hallucinated workout

**Likelihood:** Medium. **Impact:** High.

**Mitigations:** Deterministic guardrails (PRD §10.4); **`agent_runs`** audit in Postgres — 12 month retention intent.

### T6 — Garmin unofficial API / TLS fingerprinting

**Status:** See PRD §16 — Cloudflare / UA issues; PoC uses **`backend/scripts/garmin_poc.py`** patterns; swap-in `GarminClient` implementations.

**Mitigations:** Same layered approach (UA, curl_cffi, Playwright, future Health API); feature flags and sync health metrics (**Sentry** / host logs for POC; **`[future-aws]`** CloudWatch).

### T7 — Account takeover via compromised email

**Scenario:** Email compromised → Supabase password reset → health data exposed.

**Likelihood:** Low–Medium. **Impact:** High.

**Mitigations:** Prefer Google sign-in; step-up re-auth for disconnect / delete; **`[future-aws]`** Cognito advanced security optional.

### T8 — Over-privileged server

**Scenario:** Bug allows cross-user reads because FastAPI uses service role carelessly.

**Likelihood:** Medium. **Impact:** High.

**Mitigations:** Every query **filters by `uid` from JWT**; static analysis / review on service-role code paths; least DB grants on roles used by FastAPI.

### T9 — GDPR delete incomplete

**Scenario:** User deletes account; residue in Postgres, Auth, or cron registry.

**Likelihood:** Low. **Impact:** High.

**Mitigations:** Ordered pipeline: cancel cron → delete Postgres rows by `user_id` → **Supabase Auth admin delete user** → verify Storage bucket prefix if used → audit log.

## 4. Out-of-scope risks (POC)

- DDoS — platform default + rate limits; **`[future-aws]`** WAF before public launch.
- Insider — CloudTrail equivalent **`[future-aws]`**; POC relies on Supabase audit logs + Git history.
- Supply-chain — pinned deps, Renovate; **`[future-aws]`** CodeArtifact optional.

## 5. Sign-off

This threat model is the **POC security baseline**. Changes to trust boundaries (new DB, new auth provider, new PII fields) require an addendum.
