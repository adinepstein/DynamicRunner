# Shared JSON schemas

These are the **canonical** schemas for DynamicRunner. They define the contract between the Flutter app, the FastAPI backend, the Gemini agents, and **PostgreSQL** storage (e.g. `jsonb` columns aligned to these shapes).

**Optional:** GraphQL SDL or OpenAPI can be generated from the same source for documentation or tooling — **AppSync was the AWS-era target**; POC uses REST + Supabase client + RLS.

**All consumers generate code from these:**

- **Backend (Python)**: `datamodel-code-generator` produces Pydantic v2 models.
- **App (Flutter/Dart)**: `quicktype` (or `json_serializable` from a manual transcription) produces `freezed` + `json_serializable` models.

**Rules:**

1. Schemas are versioned. Breaking changes bump a major version (e.g. `workout.v2.schema.json`).
2. Never hand-edit generated code; always change the schema and regenerate.
3. Gemini agents are constrained to these schemas via structured-output mode. The schemas double as agent output contracts.

## Files

| File | Purpose |
|---|---|
| `athlete-profile.schema.json` | The user's running fitness profile, computed from 90 days of Garmin data plus self-reported fields |
| `daily-metrics.schema.json` | Daily physiological snapshot (HRV, sleep, RHR, body battery, training load) |
| `activity.schema.json` | A single completed Garmin activity (run) |
| `plan.schema.json` | A periodized race plan (top-level metadata) |
| `workout.schema.json` | A single planned workout with structured intervals and targets |
| `week-override.schema.json` | A per-ISO-week schedule override created by user drag-drop |
| `checkin.schema.json` | Post-workout RPE and feeling submission |
| `agent-run.schema.json` | Audit record of one agent invocation (planner or adapter) |
| `plan-output.schema.json` | The Planner agent's structured output (a plan + all its workouts) |
| `adapter-output.schema.json` | The Adapter agent's structured output (a list of patches) |

## Common types

`common.schema.json` defines reusable enums and value objects used across the others:

- HR zones (1–5)
- Pace value (sec/km)
- Workout types
- Statuses
- Methodologies
