# DynamicRunner — Access Control Specification

**Version:** 0.2 (POC — Supabase + FastAPI)
**Last updated:** 2026-05-06
**Replaces:** v0.1 (AWS Cognito + AppSync); see PRD §7 for production AWS targets.

This document defines who can read and write what, and **where enforcement happens**: Postgres **Row Level Security (RLS)**, **Supabase Auth JWTs**, and **FastAPI** handlers that verify those JWTs (or **cron secrets** for internal jobs).

## 1. Identity

- **Identity provider:** **Supabase Auth** (email/password + Google OIDC).
- **Token used by clients:** Supabase **user JWT** (access token) on requests to FastAPI and (when using the Supabase client) on Postgres via `anon` key + user session.
- **Trusted user identifier:** JWT claim **`sub`** (UUID). Referred to as **`uid`** in application code.
- **Never trusted as identity:** any `uid` in query string, body, path, or GraphQL-style arguments. If present, it **must** equal the verified `sub` or the request is rejected.

## 2. Trust boundary overview

```
[ Flutter app ]
     |
     | Supabase Auth session (JWT)
     |
     +---> [ Supabase Postgres ]   RLS enforces user_id = auth.uid()
     |         ^
     |         | Realtime (optional) on allowed tables
     |
     +---> [ FastAPI on Render/Fly ]
               |
               +-- Verifies JWT (JWKS) -> uid for user routes
               +-- Verifies cron secret / HMAC for /internal/* schedules
               |
               v
           [ Postgres via service role | garth | Gemini | FCM ]
```

The Flutter app **never** receives the **Supabase service role key**. It uses the **anon** key plus signed-in session for RLS-bound queries. Privileged writes (Garmin tokens, agent runs, bulk sync) go through **FastAPI** with **service role** or equivalent DB credentials **only on the server**.

## 3. Client-direct paths (Supabase)

These are typical **PostgREST / Supabase client** surfaces **after RLS** is applied. Exact table and RPC names are defined in migrations; operation names below are **logical**.

| Operation / surface | Auth | Notes |
|---|---|---|
| Read/update **own profile** | User JWT | `user_id = auth.uid()` |
| Read **plans / workouts / daily_metrics / activities** for self | User JWT | RLS on `user_id` |
| Insert/update **check-ins**, **week overrides** (narrow write surface) | User JWT | RLS + optional RPC validation |
| Subscribe **Realtime** to `garmin_profiles`, `workouts`, etc. | User JWT | Filtered by RLS / publication |
| **Garmin tokens**, **agent orchestration**, **push to Garmin**, **account delete** | **Not** via anon client | Only FastAPI with service role |

**Explicitly not client-direct:** anything touching encrypted Garmin blobs, Planner/Adapter invocation, structured push to Garmin, GDPR pipeline internals — **FastAPI only**.

## 4. FastAPI handler surface

Every **user-authenticated** handler:

1. Verifies the Supabase JWT signature against the project **JWKS** (cached).
2. Validates **issuer**, **audience**, and **expiry**.
3. Extracts **`sub`** as **`uid`** for all downstream queries.
4. Rejects any request that tries to operate on another user's resources (400/403).

| Endpoint (illustrative) | Auth | Purpose |
|---|---|---|
| `POST /garmin/login` | User JWT | Exchange Garmin credentials → encrypt → store in Postgres |
| `POST /garmin/mfa` | User JWT | Complete MFA during login |
| `DELETE /garmin` | User JWT | Wipe tokens, disconnect, remove from cron registry |
| `POST /onboarding/...` | User JWT | Profile / race goal |
| `POST /plans/regenerate` | User JWT | Trigger Planner |
| `POST /workouts/{id}/push-to-garmin` | User JWT | Upload workout via garth |
| `DELETE /account` | User JWT | Start GDPR delete pipeline |
| `POST /internal/sync` / `POST /internal/weekly-review` | **Cron secret** or **HMAC**, not user JWT | Scheduled jobs (daily sync, Saturday review, push tomorrow) |

## 5. Scheduled / internal callers

External cron (e.g. cron-job.org) or GitHub Actions calls **`/internal/*`** with a **shared secret** header or **signed payload**. These endpoints use the **service role** (or a dedicated DB role) to iterate eligible users and run sync — **never** exposed to browsers or the mobile app.

## 6. Role matrix (simplified)

| Credential | Postgres | Garmin | Gemini | FCM |
|---|---|---|---|---|
| Anon + user JWT | Per **RLS** only | no | no | no |
| Service role (server) | Full within app schema | yes (egress) | yes | yes |
| Cron secret | n/a — invokes FastAPI which uses service role | via worker | via worker | via worker |

## 7. Test enforcement

CI should include:

- Integration: authenticate as user **A**, attempt every API path and Supabase query with user **B**'s id — **must fail closed**.
- Unit: FastAPI middleware — missing token → 401; wrong iss/aud → 401; expired → 401; path `uid` ≠ `sub` → 400/403.
- SQL: negative tests for RLS (role `authenticated` cannot read other users' rows).

## 8. Open items

- [ ] Finalize whether **week override** validation runs in Postgres (RPC + RLS) or only in FastAPI.
- [ ] Confirm **Realtime** publication list per table to avoid leaking metadata.
- [ ] **`[future-aws]`** Map this matrix to Cognito + IAM + RDS policies when migrating (PRD §7).
