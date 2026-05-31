#!/usr/bin/env bash
# Generate Dart model types from shared JSON Schemas.
#
# Usage:
#   ./shared/schemas/scripts/generate_dart_models.sh
#   APP_DIR=/abs/path/to/app ./shared/schemas/scripts/generate_dart_models.sh
#
# Requirements:
#   - Node.js + npm available
#   - quicktype CLI (invoked through npx)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCHEMA_DIR="$REPO_ROOT/shared/schemas"
APP_DIR="${APP_DIR:-$REPO_ROOT/app}"
OUT_DIR="$APP_DIR/lib/src/generated/models"

if [[ ! -d "$SCHEMA_DIR" ]]; then
  echo "Schema directory not found: $SCHEMA_DIR" >&2
  exit 1
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "App directory not found: $APP_DIR" >&2
  echo "Set APP_DIR=... once Flutter app scaffold exists." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

generate() {
  local schema_file="$1"
  local top_level="$2"
  local out_file="$3"

  npx --yes quicktype \
    --src-lang schema \
    --lang dart \
    --just-types \
    --no-date-times \
    --top-level "$top_level" \
    --src "$SCHEMA_DIR/$schema_file" \
    --out "$OUT_DIR/$out_file"
}

generate "athlete-profile.schema.json" "AthleteProfile" "athlete_profile.dart"
generate "daily-metrics.schema.json" "DailyMetrics" "daily_metrics.dart"
generate "activity.schema.json" "Activity" "activity.dart"
generate "plan.schema.json" "Plan" "plan.dart"
generate "workout.schema.json" "Workout" "workout.dart"
generate "week-override.schema.json" "WeekScheduleOverride" "week_override.dart"
generate "checkin.schema.json" "Checkin" "checkin.dart"
generate "agent-run.schema.json" "AgentRun" "agent_run.dart"
generate "plan-output.schema.json" "PlannerAgentOutput" "plan_output.dart"
generate "adapter-output.schema.json" "AdapterAgentOutput" "adapter_output.dart"

echo "OK — generated Dart models in $OUT_DIR"
