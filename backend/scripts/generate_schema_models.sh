#!/usr/bin/env bash
# Regenerate Pydantic models from ../shared/schemas/*.schema.json
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/.." && pwd)"
SCHEMAS="$REPO_ROOT/shared/schemas"
OUT="$ROOT/src/dynamicrunner/schema_models"
VENV_BIN="$ROOT/.venv/bin"

if [[ ! -x "$VENV_BIN/datamodel-codegen" ]]; then
  echo "Run: cd backend && PIP_INDEX_URL=https://pypi.org/simple python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

DC() {
  "$VENV_BIN/datamodel-codegen" \
    --input-file-type jsonschema \
    --use-standard-collections \
    --disable-timestamp \
    --formatters ruff-format \
    "$@"
}

mkdir -p "$OUT"
touch "$OUT/__init__.py"

# Planner domain (Plan, Workout, PlannerAgentOutput) — supersedes standalone plan/workout roots for codegen.
DC --input "$SCHEMAS/plan-output.schema.json" --output "$OUT/planner_domain.py"
DC --input "$SCHEMAS/adapter-output.schema.json" --output "$OUT/adapter_domain.py"
DC --input "$SCHEMAS/activity.schema.json" --output "$OUT/activity.py"
DC --input "$SCHEMAS/daily-metrics.schema.json" --output "$OUT/daily_metrics.py"
DC --input "$SCHEMAS/athlete-profile.schema.json" --output "$OUT/athlete_profile.py"
DC --input "$SCHEMAS/checkin.schema.json" --output "$OUT/checkin.py"
DC --input "$SCHEMAS/week-override.schema.json" --output "$OUT/week_override.py"
DC --input "$SCHEMAS/agent-run.schema.json" --output "$OUT/agent_run.py"

echo "OK — wrote Python models under $OUT"
