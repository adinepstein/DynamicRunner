# Dart Codegen Spec

This spec defines how DynamicRunner generates Dart model types from canonical JSON Schemas in `shared/schemas/`.

## Goal

Keep Flutter model types aligned with backend and agent contracts by generating Dart code from the same schema source.

## Generator

- Tool: `quicktype` (CLI via `npx quicktype`)
- Input language: `schema`
- Output language: `dart`
- Mode: types-only (`--just-types`)

## Entry Script

- Script: `shared/schemas/scripts/generate_dart_models.sh`
- Default app target: `app/lib/src/generated/models`
- Override target app directory:

```bash
APP_DIR=/absolute/path/to/app ./shared/schemas/scripts/generate_dart_models.sh
```

## Schema to Dart mapping

| Schema file | Top-level Dart type | Output file |
|---|---|---|
| `athlete-profile.schema.json` | `AthleteProfile` | `athlete_profile.dart` |
| `daily-metrics.schema.json` | `DailyMetrics` | `daily_metrics.dart` |
| `activity.schema.json` | `Activity` | `activity.dart` |
| `plan.schema.json` | `Plan` | `plan.dart` |
| `workout.schema.json` | `Workout` | `workout.dart` |
| `week-override.schema.json` | `WeekScheduleOverride` | `week_override.dart` |
| `checkin.schema.json` | `Checkin` | `checkin.dart` |
| `agent-run.schema.json` | `AgentRun` | `agent_run.dart` |
| `plan-output.schema.json` | `PlannerAgentOutput` | `plan_output.dart` |
| `adapter-output.schema.json` | `AdapterAgentOutput` | `adapter_output.dart` |

## Workflow

1. Update one or more JSON Schemas under `shared/schemas/`.
2. Regenerate backend models (`backend/scripts/generate_schema_models.sh`).
3. Regenerate Dart types (`shared/schemas/scripts/generate_dart_models.sh`).
4. Run backend + app tests.

## Constraints

- Do not hand-edit generated files in `app/lib/src/generated/models/`.
- Make schema changes in `shared/schemas/` and regenerate.
- Keep field naming consistent across backend and app; prefer schema changes over manual app-side aliases.
