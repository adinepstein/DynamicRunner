# DynamicRunner

An Android app that generates and continuously adapts running training plans, using your Garmin Connect data and a Gemini-powered agent.

**POC backend:** **Supabase** (PostgreSQL + Auth + Realtime) plus **FastAPI** hosted on **Render** or **Fly.io**. A future production deployment may move to **AWS** (see [PRD.md](PRD.md) §7 “Production / migration”).

See [PRD.md](PRD.md) for the full product spec, [TODO.md](TODO.md) for the implementation plan, and [docs/architecture-poc.md](docs/architecture-poc.md) for the **POC architecture** one-pager (diagram + secrets + trust boundaries).

## Repository layout

```
.
├── PRD.md                  # Product requirements
├── TODO.md                 # Phased implementation checklist
├── README.md               # This file
├── shared/
│   └── schemas/            # Canonical JSON Schema (Flutter, FastAPI; GraphQL SDL optional for POC)
├── backend/
│   └── prompts/            # Gemini agent system prompts and few-shots
├── docs/
│   ├── architecture-poc.md # POC stack one-pager (Supabase + FastAPI + cron + FCM)
│   ├── threat-model.md     # Security threat model (POC Supabase + hosted backend)
│   └── access-control.md   # Authorization (RLS + FastAPI JWT)
├── app/                    # (Phase 1) Flutter Android app
├── backend/                # (Phase 1) FastAPI service (Garmin, agents, cron hooks)
└── infra/                  # Docker + host config (Render/Fly); full Terraform deferred until AWS migration
```

## Status

Phase 0 — Design & schemas. See [TODO.md](TODO.md).

## Stack at a glance

- **Mobile**: Flutter (Android first), Riverpod, go_router, fl_chart, Hive, **`supabase_flutter`** (auth + Postgres + Realtime), **`firebase_messaging`** (FCM token registration only)
- **Backend**: Python 3.12, FastAPI, Pydantic v2, **`garth`**, **`google-genai`**, Supabase JWT verification
- **Data & auth (POC)**: **Supabase** — PostgreSQL, **Row Level Security**, **Supabase Auth**; **service role** only on the server
- **Hosting**: FastAPI in Docker on **Render** or **Fly.io**
- **Push**: **FCM HTTP v1** — minimal Firebase project holds **only** FCM credentials (no Firestore as primary store)
- **Schedules**: External **HTTPS cron** or CI schedule calling protected FastAPI endpoints — **`[future-aws]`** EventBridge when migrating
- **AI**: Google Gemini — 2.5 Pro (Planner), 2.5 Flash (Adapter)

### Migration to AWS (not POC)

When scaling beyond the POC stack: **Cognito** (or mapped identities), **RDS/DynamoDB**, **KMS + Secrets Manager**, **API Gateway + App Runner**, **EventBridge**, optional **Pinpoint**, **S3**, **CloudWatch** — same logical product; infrastructure swap. One canonical narrative lives in **PRD §7** and **§13a**.

## Design principles

- **Garmin connection is mandatory.** No plan without watch data.
- **Adaptation > prescription.** Every workout the user does (or doesn't do) feeds the next decision.
- **Deterministic rules first, LLM second.** The rules engine handles obvious cases; Gemini handles judgement calls.
- **Auditable agent.** Every change to the plan is logged in Postgres with a reason the user can read.
- **Schema-validated AI output.** The Planner and Adapter agents always produce JSON that matches a strict schema; violations are rejected.
- **Security: password in, tokens stored.** The user's Garmin password is exchanged for OAuth tokens once and never persisted; tokens are encrypted at rest with a **server-only key** (POC: env-based; production: KMS).
- **Single source of truth for types.** JSON Schemas in `shared/schemas/` generate Pydantic models and Dart `freezed` models — keep generated REST/Supabase bindings aligned with those schemas.
