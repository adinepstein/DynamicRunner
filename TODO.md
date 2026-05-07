# DynamicRunner — Implementation TODO

**Companion to:** [PRD.md](PRD.md)
**Target:** Lean MVP, ~12 weeks, Android only.
**Cloud (POC):** **Supabase** (PostgreSQL + Auth + Realtime) + **FastAPI** on **Render** or **Fly.io**; **FCM HTTP v1** with a minimal Firebase project (credentials only); **external HTTPS cron** (or GitHub Actions schedule) for per-user jobs. **`[future-aws]`** tags tasks deferred to an AWS production migration (see PRD §7, §13a).
**Format:** Each task has a clear acceptance criterion. Update statuses as we go.

Legend: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked

---

## Phase 0 — Design & schemas (week 1–2)

Goal: lock the contracts before we write code, so the Flutter team and Python team can build in parallel.

- [!] **0.1 — Figma wireframes for the 8 core screens**
  - Screens: Sign-in, Garmin connect (with MFA), Backfill progress, Profile + race goal, Plan overview, Today's workout, Post-workout check-in, Settings.
  - Acceptance: clickable Figma prototype reviewed end-to-end; key states (loading, error, empty, offline) included.
  - **Blocked:** Requires active Figma design pass.
- [!] **0.2 — Visual design system**
  - Color palette (light + dark), typography scale, component library (buttons, cards, sliders, chips), iconography.
  - Acceptance: Figma library published; tokens exported to a Dart file (`design_tokens.dart`).
  - **Blocked:** Depends on 0.1 wireframes and design sign-off.
- [~] **0.3 — Finalize JSON schemas**
  - Athlete profile, plan, workout, daily metrics, check-in, agent run, plus planner/adapter agent output schemas.
  - **Drafted as JSON Schema 2020-12 in [`shared/schemas/`](shared/schemas/)** (canonical, language-agnostic). ✅ Backend codegen wired: `backend/scripts/generate_schema_models.sh` now generates Pydantic models under `backend/src/dynamicrunner/schema_models/`; round-trip tests added in `backend/tests/test_schema_roundtrip.py`.
  - Pending: quicktype / Dart `freezed` generation once Flutter scaffold exists (Phase 1).
  - Acceptance: Pydantic v2 models in backend repo; matching `freezed` Dart models in Flutter repo; REST/Supabase bindings aligned with the same schemas; round-trip serialization tested.
- [~] **0.4 — Agent prompt templates**
  - System prompt + few-shot examples for Planner; system prompt for Adapter; output schema enforcement.
  - **Drafted in [`backend/prompts/`](backend/prompts/) (`planner.system.v1.md`, `planner.fewshots.v1.md`, `adapter.system.v1.md`).** Pending: first end-to-end run against Gemini once backend is scaffolded.
  - Acceptance: prompts versioned in `backend/prompts/`; first manual run against Gemini produces a schema-valid plan for a sample athlete.
- [~] **0.5 — Authorization model**
  - Per-user access via **Postgres RLS** (Supabase client paths) and **FastAPI** (Supabase JWT verification + `sub` as `uid`). Service role / DB elevated access only on the server; Flutter never holds service credentials.
  - **Drafted in [`docs/access-control.md`](docs/access-control.md).** Pending: RLS policies + FastAPI auth middleware in Phase 1.
  - Acceptance: written access-control spec; integration test that an authenticated user A cannot read user B's items via any API path.
- [x] **0.6 — Threat model & data flow review**
  - Walk through Garmin auth, token storage, agent decisions, deletion flow.
  - Written in [`docs/threat-model.md`](docs/threat-model.md) (POC Supabase + FastAPI). 9 top threats identified with mitigations.
  - Acceptance: written 1-pager with identified risks and chosen mitigations; signed off.

## Phase 1 — Foundation (week 2–4)

- [ ] **1.1 — Repos & monorepo layout**
  - `app/` (Flutter), `backend/` (FastAPI), `infra/` (Docker + Render/Fly config; **`[future-aws]`** Terraform when migrating), `shared/` (JSON schemas), `docs/`.
  - Acceptance: GitHub repo created with branch protection on `main`.
- [ ] **1.2 — Flutter scaffold**
  - Project init, Riverpod, go_router, fl_chart, Hive, freezed/json_serializable, Sentry, **`supabase_flutter`** (auth + Postgres client + Realtime), **`firebase_messaging`** (FCM token registration only).
  - Acceptance: app boots to a placeholder home screen on a real device; Sentry receives a test crash; Supabase configured with project URL + anon key (placeholder dev project OK).
- [ ] **1.3 — FastAPI scaffold**
  - Project init with Poetry, FastAPI, Pydantic v2, structlog, ruff + mypy, pytest, **`supabase-py` or direct Postgres** as needed, **Supabase JWT verifier middleware** (validates JWT signature against project JWKS; extracts `sub` as `uid`).
  - Acceptance: `GET /healthz` returns 200; auth middleware rejects unauthenticated calls with 401 and accepts a valid Supabase user JWT.
- [ ] **1.4 — Supabase project + minimal Firebase (FCM only)**
  - Create a **Supabase** project: enable **Auth** (email/password + Google provider), **Postgres**, **Realtime** (toggle tables later). Store `SUPABASE_URL`, `SUPABASE_ANON_KEY`, **`SUPABASE_SERVICE_ROLE_KEY`** (backend only), `JWT_SECRET` context in env/secrets manager on the host — **never** commit service role to the app bundle.
  - Create a **minimal Firebase project** with **only** FCM Android config (`google-services.json` / HTTP v1 service account) — no Firestore, Auth, Storage, or Functions for app data.
  - Acceptance: Flutter can sign in via Supabase and obtain a session JWT; FastAPI validates that JWT; FCM token registration path stubbed or working.
- [ ] **1.5 — CI pipeline (GitHub Actions)**
  - Flutter analyze + test + build APK. Python lint + test + Docker build + deploy to **Render** or **Fly.io** on `main` (no ECR requirement for POC). Optional: SQL migration check against Supabase staging.
  - Acceptance: PR to `main` triggers pipeline green; hosted FastAPI URL serves new code within ~10 min of merge.
- [ ] **1.6 — Database schema + RLS (Supabase)**
  - Tables aligned with PRD §8 (users/profile, garmin_profiles, activities, daily_metrics, plans, workouts, etc.). **RLS** enabled: `user_id = auth.uid()` on user-owned rows; document which operations use **anon + JWT** vs **service role** in FastAPI.
  - Acceptance: migrations applied to dev Supabase; smoke test from SQL editor or Flutter that user A cannot `select` user B's rows.
- [ ] **1.7 — Auth + profile row wired end-to-end**
  - Email/password + Google via **Supabase Auth** in Flutter; on first login upsert profile row in Postgres (`user_id = sub`) with `createdAt`, timezone, default units (via FastAPI hook or Supabase trigger).
  - Acceptance: full sign-up, sign-out, sign-back-in flow works; profile row exists with correct `sub` as `uid`.

### `[future-aws]` — optional parallel track (skip for POC)

- Full **Terraform** for Cognito, AppSync, DynamoDB, App Runner, EventBridge, KMS, Pinpoint — defer until AWS migration ([PRD §7](PRD.md)).

## Phase 2 — Garmin integration (week 4–6)

- [x] **2.1 — `garth` login proof-of-concept**
  - Standalone Python script: log in (with MFA), pull last 7 days of activities, daily metrics, and HRV; print summary. **Israel users use the default global `garmin.com` domain — no override needed; only China requires `garmin.cn`.**
  - **Important context (2026-03-27)**: `garth` was deprecated because Garmin's Cloudflare layer began TLS-fingerprinting requests with the default mobile UA. Our script uses **curl_cffi** TLS impersonation + optional Playwright when SSO returns 429. See PRD Section 16 and threat-model T6.
  - **Implemented at [`backend/scripts/garmin_poc.py`](backend/scripts/garmin_poc.py)** with [README](backend/scripts/README.md). Verified against a real Israel-based Garmin account: activities + daily metrics + HRV; token resume after Playwright login; daily summary uses `?calendarDate=` (not path-style date) per Connect API contract.
  - Acceptance: works against a real Israel-based Garmin account; runs in <30 seconds (excluding interactive prompts / WAF delay); token cache lets the second run skip login.
- [x] **2.1a — Sync layer interface + curl_cffi + Playwright fallback** *(scripts / PoC scope)*
  - **curl_cffi**: `garmin_poc.py` loads tokens on the default `requests.Session` (garth `configure()` requires `.mount`), then swaps in `curl_cffi.requests.Session(impersonate="chrome131")` for Connect API calls.
  - **Playwright**: [`backend/scripts/garmin_poc_playwright.py`](backend/scripts/garmin_poc_playwright.py) — iframe-aware SSO, `login-url` aligned with web embed for OAuth exchange, tokens written to the same `./.garth_tokens/` as `garmin_poc.py`.
  - **Deferred to Phase 2 backend work**: define a `GarminClient` Protocol and wire optional Playwright + curl_cffi inside the FastAPI service (see 2.2–2.3).
  - Acceptance: user runs Playwright script once, then `garmin_poc.py` pulls data without password login; OR curl_cffi-only path works on a clean IP without Playwright.
- [ ] **2.2 — Encrypted credential storage**
  - Encrypt Garmin OAuth token blob with **`cryptography`** (Fernet or AES-GCM) using **`APP_ENCRYPTION_KEY`** (or similar) from env — store ciphertext in **Postgres** (`garmin_profiles` or dedicated table). **`[future-aws]`**: envelope encryption with KMS + Secrets Manager.
  - Acceptance: unit tests cover encrypt/decrypt round-trip; ciphertext useless without app key; passwords never logged or persisted; document key rotation for POC (see PRD §16).
- [ ] **2.3 — `POST /garmin/login` and `POST /garmin/mfa` endpoints**
  - Login flow per PRD Section 9; structured error responses for invalid credentials, locked account, MFA required.
  - Acceptance: end-to-end from Flutter UI through to encrypted token storage; password is wiped from memory after token exchange (verified by code review + log audit).
- [ ] **2.4 — 90-day backfill job**
  - Pulls activities, daily metrics, sleep, HRV, body battery, stress, VO2max history; idempotent; chunked to respect Garmin rate limits; writes to **Postgres** tables per PRD §8 (`user_id` + natural keys).
  - Acceptance: typical account fully backfilled in <2 minutes; re-run produces zero duplicates (idempotent on `garmin_activity_id` and `date`).
- [ ] **2.5 — Daily delta sync via cron → HTTPS**
  - Register users for **external cron** (e.g. cron-job.org) or **GitHub Actions** `schedule` calling **`POST /internal/sync`** (or per-user endpoint) with **`Authorization: Bearer <cron secret>`** or **HMAC**; fires ~user local 04:00 (store timezone on profile). **`[future-aws]`**: EventBridge Scheduler → signed API Gateway.
  - Acceptance: 95% of test users sync within 5 minutes of scheduled time; failures retry with exponential backoff up to 1 hour; alert on >5% sync-failure rate (Sentry or host metrics — **`[future-aws]`** CloudWatch alarm).
- [ ] **2.6 — Sync health monitoring & re-auth banner**
  - `sync_status` on `garmin_profiles`; backend marks `reauth_required` when refresh fails; **Supabase Realtime** (or poll) updates Flutter; banner with one-tap reconnect.
  - Acceptance: simulating an expired refresh token produces the banner within seconds; reconnect restores sync.
- [ ] **2.7 — Disconnect flow**
  - `DELETE /garmin` deletes ciphertext row(s), marks `garmin_profiles` disconnected, **removes user from cron registry** (or skip-list), optionally deletes synced activities (user choice).
  - Acceptance: tested end-to-end; no residual tokens in Postgres; cron no longer hits that user.

## Phase 3 — Onboarding & athlete profile (week 5–7)

- [ ] **3.1 — Onboarding flow UI**
  - 6-step flow per PRD Section 4.1; progress indicator; back navigation; resumable on app kill.
  - Acceptance: user can complete onboarding in <8 minutes on a typical device.
- [ ] **3.2 — Backfill progress screen**
  - Live progress via **Supabase Realtime** on `garmin_profiles` (or poll FastAPI); estimated time remaining derived from items synced so far.
  - Acceptance: progress updates within ~1 second of backend writes; works on poor networks (Realtime reconnects per Supabase client).
- [ ] **3.3 — Profile capture screen**
  - Age, sex, weight, injury free-text, recent races confirmation (auto-detected from Garmin).
  - Acceptance: data persisted to the **profile** row (`user_id = sub`); race auto-detection covers 90%+ of recent race-distance activities.
- [ ] **3.4 — Race goal screen**
  - Event picker, date picker (≥4 weeks out), goal pace with Garmin race-predictor as default, training-day chips, long-run day picker.
  - Acceptance: validation rules enforced; can't continue with invalid combinations.
- [ ] **3.5 — Feature extraction service (backend)**
  - Computes weekly mileage, paces by HR zone, longest recent run, recovery patterns, current VO2max, ACWR/CTL/ATL/TSB from 90-day history; output matches `athlete-profile.schema.json`.
  - Acceptance: deterministic output for a given input; unit-tested on 5 sample athletes; runs in <2 seconds.

## Phase 4 — AI plan generation (week 6–8)

- [ ] **4.1 — Gemini integration & cost guardrails**
  - `google-genai` client, structured output mode bound to `plan-output.schema.json`, per-call cost logging to **structured logs / Sentry breadcrumbs** ( **`[future-aws]`** CloudWatch metrics), hard token limits.
  - Acceptance: a manual call generates a valid plan; cost recorded in **`agent_runs`** and visible in observability tooling.
- [ ] **4.2 — Planner agent**
  - System prompt, few-shot examples, tool registry (`get_athlete_state`, `propose_plan`), schema validation, self-critique pass.
  - Acceptance: produces complete, schema-valid plans for 10 sample athletes covering different fitness levels and races; 100% pass guardrails.
- [ ] **4.3 — Plan persistence**
  - **Postgres transaction** (single round-trip or SQL procedure) to atomically write the new **plan** plus **workouts** rows; old plans archived (`status=abandoned`) on regenerate — **`[future-aws]`** DynamoDB `TransactWriteItems` equivalent.
  - Acceptance: race-condition test (two regenerates in flight) produces exactly one active plan.
- [ ] **4.4 — Plan viewer UI**
  - Calendar/week view (week starts Sunday), day detail view, **methodology prominently displayed in the plan summary header** (e.g., "Polarized 80/20 — chosen because your easy/hard split last 90d was 73/27") with an expandable rationale, "regenerate plan" action.
  - Acceptance: scrolling 16 weeks of plan stays at 60 fps; day view loads in <100 ms from cache; methodology + 1-paragraph rationale visible on the plan summary screen.
- [ ] **4.5 — Guardrails layer**
  - Pure-Python module enforcing PRD Section 10.4 rules; called by both Planner and Adapter.
  - Acceptance: 20 unit tests covering edge cases; rejects known-bad sample plans.

## Phase 5 — Workout execution loop (week 7–9)

- [ ] **5.1 — Workout schema → Garmin payload mapper**
  - Maps every step kind (duration, distance, repeat) and target kind (pace, HR zone, RPE) to Garmin's structured-workout JSON.
  - Acceptance: 30 unit tests; manual round-trip on a real watch confirms intervals execute correctly.
- [ ] **5.2 — `push_workout_to_garmin` tool**
  - Backend tool that uploads a workout to Garmin Connect via `garth`, stores the returned `garminWorkoutId` on the **`workouts`** row.
  - Acceptance: workout appears on the watch within 5 minutes of API call.
- [ ] **5.3 — Today screen**
  - Hero card with today's workout, structured intervals, target paces and HR zones, "push to watch" button (or auto-push status).
  - Acceptance: matches Figma; loads in <300 ms from local cache; falls back to **Supabase query** or FastAPI if cache cold.
- [ ] **5.4 — Auto-push overnight**
  - **HTTPS cron** (same pattern as Phase 2.5) ~04:30 local per user; backend pushes tomorrow's workout if not yet pushed — **`[future-aws]`** EventBridge Scheduler.
  - Acceptance: 95% of users have tomorrow's workout on watch by 06:00 local.
- [ ] **5.5 — Activity-to-workout matcher**
  - When Garmin sync brings in an activity, match it to the planned workout for that day; mark status accordingly via **Postgres** update with optimistic concurrency / `WHERE` clause.
  - Acceptance: matching accuracy ≥95% on 100 manual test cases.
- [ ] **5.6 — Post-workout check-in**
  - **FCM** push 30 min after activity sync; 5-second RPE + feeling flow; persisted via **Supabase insert/update under RLS** or **FastAPI** to **`checkins`** — **RLS** must enforce `user_id = auth.uid()` (or server-only path).
  - Acceptance: end-to-end flow tested; submission round-trip <500 ms; cross-user write impossible (integration test).

## Phase 6 — Adaptation engine (week 8–10)

- [ ] **6.1 — Deterministic rules engine**
  - All rules from PRD Section 12 implemented as pure functions; returns a list of `RuleDecision` objects. Includes the next-day-reschedule rule (consume rest day if needed) and the per-week schedule override validator.
  - Acceptance: 25 unit tests including: missed Tuesday intervals → moves to Wednesday even if Wednesday was rest; missed workout when next day is already hard → drops to "skipped"; user drag-drop that violates back-to-back-hard-days surfaces a warning.
- [ ] **6.2 — Adapter agent**
  - Gemini Flash, tool registry (`get_recent_activities`, `get_plan`, `patch_workout`), patch-only output schema bound to `adapter-output.schema.json`.
  - Acceptance: produces minimal patches (≤5 ops in typical cases); never rewrites the whole plan.
- [ ] **6.3 — Weekly review cron**
  - **HTTPS cron** triggers **Saturday 18:00 local** per user (week starts Sunday); invokes adapter run via FastAPI — **`[future-aws]`** EventBridge Scheduler.
  - Acceptance: 100% of active users get the summary card by Saturday 19:00 local.
- [ ] **6.4 — Event-driven triggers**
  - **POC:** post-sync FastAPI logic or lightweight job queue inspects new activities / daily metrics and enqueues an adapter run on missed-workout detection, HRV/sleep anomalies, performance drift — **`[future-aws]`** DynamoDB Streams → Lambda fan-out.
  - Acceptance: simulated triggers each produce the expected adaptation within 60 seconds.
- [ ] **6.5 — Audit log & in-app explanation**
  - Every patch shows up in a "What changed" feed sourced from **`agent_runs`**; user can tap to expand the agent's reasoning. **Supabase Realtime** (or poll) pushes new feed items.
  - Acceptance: every change in **`agent_runs`** is reflected in the in-app feed.
- [ ] **6.6 — Undo / accept**
  - Each change has a one-tap undo (within 24h) and an explicit accept (clears the badge). Undo stores previous **`workouts.structure`** (or `previous` jsonb) on patch.
  - Acceptance: undo restores the previous workout state exactly.
- [ ] **6.7 — Edit this week (drag-and-drop schedule override)**
  - "Edit this week" action on the plan screen. User can drag workouts to different days within the current ISO week or mark a day unavailable. Validates against guardrails and shows inline warnings rather than blocking. Persists **`week_overrides`** via Supabase (RLS) or FastAPI.
  - Acceptance: round-trip of an override correctly re-renders the week; long-run anchor preserved; guardrail warning shown when user creates back-to-back hard days; override does not affect future weeks unless user updates the default in settings.

## Phase 7 — Dashboard & notifications (week 9–11)

- [ ] **7.1 — Training-load chart**
  - 30-day CTL/ATL/TSB stacked area + ACWR overlay; touch interaction shows the day's values.
  - Acceptance: renders <300 ms; matches Garmin's training status within ±5%.
- [ ] **7.2 — HRV trend chart**
  - 28-day baseline band + nightly readings; "today vs baseline" callout.
  - Acceptance: data fetched from Hive cache (populated by **Realtime or query** on **`daily_metrics`**); offline-readable.
- [ ] **7.3 — Plan progress widget**
  - Weeks completed / weeks remaining, % workouts completed, current "training status" derived label.
  - Acceptance: visible on home screen; updates after each completed workout.
- [ ] **7.4 — Push notifications (FCM HTTP v1)**
  - Daily morning briefing (06:30 local), missed-workout reminder with the 3 one-tap options (do tomorrow / swap day / skip), weekly review summary (Saturday 18:00 local), re-auth prompt. Server sends via **FCM HTTP v1** using credentials from Phase 1.4 — **`[future-aws]`** Pinpoint as optional wrapper + analytics.
  - Acceptance: deliverable rate ≥98%; user can disable each category in settings; basic delivery/open tracking (product analytics or logs).
- [ ] **7.5 — Settings screen**
  - Garmin connection status, notification toggles, units, weekly-review time, disconnect Garmin, delete account.
  - Acceptance: every toggle persists; delete account fires the GDPR delete pipeline.

## Phase 8 — Hardening & beta (week 10–12)

- [ ] **8.1 — Sentry + structured logging**
  - Source maps uploaded to Sentry; backend **JSON logs** to stdout (host aggregates) — **`[future-aws]`** CloudWatch + X-Ray through API Gateway → App Runner → Postgres.
  - Acceptance: a thrown exception in Flutter is visible in Sentry with full stack and breadcrumbs; backend logs correlate requests (trace/request id in Gemini and Garmin logs).
- [ ] **8.2 — Analytics**
  - Onboarding funnel, DAU, plan-completion rate, agent-acceptance rate, sync health — pick a **product analytics** tool or structured-log queries; **`[future-aws]`** Pinpoint events + CloudWatch dashboards / QuickSight.
  - Acceptance: dashboard live showing all PRD success metrics.
- [ ] **8.3 — GDPR delete pipeline**
  - Soft delete → 30-day grace → hard delete. Hard delete walks: **all Postgres rows** for `user_id`; **Supabase Auth** user deletion; **encrypted Garmin** blob removed; **cron registry** cleared; **Supabase Storage** prefix if used; transactional email for confirmation (Supabase SMTP / Resend / SES).
  - Acceptance: end-to-end test; auditor can verify zero residual data via a follow-up scan.
- [ ] **8.4 — Load & sync stress test**
  - Simulate 1000 users syncing in the same hour; verify **Fly/Render** scaling, Garmin rate-limit handling, **Postgres** connection pool + query performance, **Realtime** subscription load (or poll fallback).
  - Acceptance: p95 sync time <5 minutes under load; zero data corruption; host metrics healthy — **`[future-aws]`** substitute App Runner + DynamoDB + AppSync targets.
- [ ] **8.5 — Closed beta with 10–20 runners**
  - Recruit via personal network and running clubs; weekly feedback survey; in-app feedback button.
  - Acceptance: 4-week beta produces a prioritized fix list; no P0 bugs at exit.
- [ ] **8.6 — Pre-launch checklist**
  - Privacy policy + terms of service published; Play Store listing complete; signed release APK; staged rollout plan (1% → 10% → 100%).
  - Acceptance: Play Store internal testing track approved.

---

## Cross-cutting / standing tasks

- [ ] Weekly review of Gemini cost per active user; alert (Sentry/host metrics) if >$1/month — **`[future-aws]`** CloudWatch alarm.
- [ ] Weekly review of Garmin sync failure rate; alert at >10% per-user failures.
- [ ] **`[future-aws]`** Annual rotation of AWS KMS customer-managed keys + Secrets Manager re-encryption. **POC:** rotate `APP_ENCRYPTION_KEY` per ops doc (PRD §16).
- [ ] Quarterly threat-model refresh.

## Resolved decisions (locked-in 2026-04-28; **POC cloud updated 2026-05-06**)

- **POC cloud**: **Supabase** (Postgres + Auth + Realtime) + **FastAPI** on **Render/Fly**; **FCM-only** Firebase for push; **HTTPS cron** for schedules; **`[future-aws]`** full AWS stack deferred (see PRD §7).
- **Single-region POC**; production AWS migration may use **`il-central-1`** (Tel Aviv) — not blocking POC.
- **Stack (POC)**: Supabase Auth (`sub` = `uid`), Postgres + RLS, optional Realtime; FastAPI with Supabase JWT verification; encrypted Garmin tokens in DB (env master key); Gemini cross-cloud for AI.
- **FCM project**: minimal Firebase project that holds **only** FCM credentials. No Firestore as primary store.
- **Garmin region**: Israel users use the default global `garmin.com` domain (no override needed). Per-user domain config is only required for China (`garmin.cn`) — deferred to post-MVP.
- **Previous Garmin Coach plans**: ignored. We do not import or migrate any existing Garmin Coach plan.
- **Weekly review time**: Saturday 18:00 local (week starts Sunday).
- **Methodology disclosure**: full disclosure on the plan summary screen.
- **App name**: DynamicRunner (working name; pending Play Store + trademark availability check).
- **Missed-workout rule**: workout moves to the next calendar day even if it was a rest day; user can also drag-drop via "Edit this week".

## New open questions (to surface as we build)

- [x] ~~Confirm the exact Garmin regional endpoint hostname for Israel users~~ — Resolved: Israel uses the default global `garmin.com`. Verified via 2.1 PoC.
- [ ] Define what happens if the user changes the goal race date mid-plan — minor patch via Adapter, or full Planner rerun?
- [ ] Race-day-of-week handling: most user races will be Friday/Saturday in Israel — confirm taper logic accounts for race not being on Sunday-end-of-week.
- [ ] **Supabase Realtime** scaling/cost at 10K users; if expensive, poll or selective subscriptions on affected screens — **`[future-aws]`** compare to AppSync fan-out.
- [ ] **`[future-aws]`** EventBridge Scheduler quotas vs external cron + DB fan-out at 10K+ users.
- [ ] Trademark + Play Store name availability check for "DynamicRunner".
