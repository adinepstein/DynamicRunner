# Gemini agent prompts

Versioned prompt templates for DynamicRunner's two agents.

| File | Agent | Model | Trigger |
|---|---|---|---|
| `planner.system.v1.md` | Planner | gemini-2.5-pro | Onboarding, race change, manual regenerate |
| `adapter.system.v1.md` | Adapter | gemini-2.5-flash | Weekly cron, missed workout, HRV/sleep/load triggers, performance drift |
| `planner.fewshots.v1.md` | Planner | — | Few-shot examples appended to the planner prompt |

## Conventions

- File name pattern: `<agent>.<role>.v<N>.md`. Major version bumps are breaking; the version is logged on **`agent_runs`** records (e.g. `prompt_version`).
- Prompts use Markdown. The runtime substitutes `{{variables}}` before sending to Gemini.
- Output is constrained by JSON Schema (`shared/schemas/plan-output.schema.json` and `adapter-output.schema.json`). The schema is sent to Gemini via structured-output mode, so prompts focus on *intent* not on shape.
- All physiological inputs are pseudonymous (no name, email, exact birthdate). Only age, sex, weight, and derived numbers go to the model.

## Tool registry (shared)

| Tool | Used by | Purpose |
|---|---|---|
| `get_athlete_state(uid)` | Planner, Adapter | Latest profile, fitness, recovery |
| `get_recent_activities(uid, days)` | Adapter | Activities + check-ins for the window |
| `get_plan(uid, planId)` | Planner, Adapter | Current plan + upcoming workouts |
| `propose_plan(uid, planJson)` | Planner | Persists a new plan after schema + guardrail validation |
| `patch_workout(uid, workoutId, patch, reason)` | Adapter | Modifies one planned workout |
| `push_workout_to_garmin(uid, workoutId)` | Backend post-agent | Translates schema → Garmin payload, uploads via garth |

The agent never calls `push_workout_to_garmin` directly; that's handled by the backend after a patch is persisted.

## Example outputs and validation

- Example model outputs live in `backend/prompts/examples/`.
- Validate the examples against JSON Schema:

```bash
cd backend
.venv/bin/python scripts/validate_prompt_examples.py
```

- `pytest` also validates these examples against generated Pydantic models (`tests/test_prompt_example_outputs.py`).
