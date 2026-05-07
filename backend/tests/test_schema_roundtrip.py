from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema import RefResolver

from dynamicrunner.schema_models import (
    Activity,
    AdapterAgentOutput,
    AgentRun,
    AthleteProfile,
    Checkin,
    DailyMetrics,
    PlannerAgentOutput,
    WeekScheduleOverride,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "shared" / "schemas"


SCHEMAS = {path.name: json.loads(path.read_text()) for path in SCHEMA_DIR.glob("*.schema.json")}
SCHEMA_STORE = {schema["$id"]: schema for schema in SCHEMAS.values()}


def _assert_jsonschema_valid(instance: dict, schema_filename: str) -> None:
    schema = SCHEMAS[schema_filename]
    resolver = RefResolver.from_schema(schema, store=SCHEMA_STORE)
    jsonschema.validate(instance=instance, schema=schema, resolver=resolver)


@pytest.mark.parametrize(
    ("model_cls", "schema_name", "payload"),
    [
        (
            PlannerAgentOutput,
            "plan-output.schema.json",
            {
                "plan": {
                    "raceType": "10k",
                    "raceDate": "2026-06-21",
                    "methodology": "polarized_80_20",
                    "methodologyRationale": "Your recent load distribution and recovery signals support a polarized approach to improve threshold pace with lower injury risk.",
                    "weeklyStructure": [
                        {
                            "isoWeek": "2026-W22",
                            "phase": "build",
                            "targetVolumeKm": 48.0,
                            "qualitySessions": 2,
                        }
                    ],
                },
                "workouts": [
                    {
                        "scheduledDate": "2026-06-01",
                        "type": "easy",
                        "title": "Easy aerobic run",
                        "estimatedDurationSec": 2700,
                        "structure": {
                            "mainSteps": [
                                {
                                    "kind": "repeat",
                                    "repeat": 2,
                                    "steps": [{"kind": "duration", "seconds": 900}],
                                }
                            ]
                        },
                        "targets": {"rpeRange": [3, 4]},
                    }
                ],
                "selfCritique": {
                    "weeklyVolumeIncreaseOk": True,
                    "tapersCorrectly": True,
                    "noBackToBackHard": True,
                    "longRunCapOk": True,
                    "comments": "Volume changes are conservative and include one quality session buffer to protect recovery.",
                },
            },
        ),
        (
            AdapterAgentOutput,
            "adapter-output.schema.json",
            {
                "patches": [
                    {
                        "op": "move",
                        "workoutId": "w1",
                        "newDate": "2026-06-02",
                        "reason": "You missed yesterday's session and sleep was adequate, so moving it one day keeps the week structure stable.",
                    }
                ],
                "summary": "One missed workout was shifted to tomorrow to preserve stimulus and keep the rest of the microcycle intact.",
                "noChangeNeeded": False,
            },
        ),
        (
            AthleteProfile,
            "athlete-profile.schema.json",
            {
                "uid": "user-1",
                "self": {
                    "age": 34,
                    "sex": "male",
                    "weightKg": 73.5,
                    "timezone": "Asia/Jerusalem",
                },
                "fitness": {},
                "preferences": {
                    "units": "metric",
                    "trainingDaysPerWeek": 5,
                    "preferredTrainingDays": ["sun", "mon", "wed", "thu", "sat"],
                    "longRunDay": "sat",
                },
                "computedAt": "2026-05-01T08:00:00Z",
            },
        ),
        (
            Activity,
            "activity.schema.json",
            {
                "uid": "user-1",
                "garminActivityId": "ga-1",
                "startedAt": "2026-05-01T05:00:00Z",
                "type": "running",
                "durationSec": 3600,
                "distanceM": 10000.0,
            },
        ),
        (
            DailyMetrics,
            "daily-metrics.schema.json",
            {
                "uid": "user-1",
                "date": "2026-05-01",
                "syncedAt": "2026-05-01T05:30:00Z",
            },
        ),
        (
            Checkin,
            "checkin.schema.json",
            {
                "uid": "user-1",
                "workoutId": "w1",
                "rpe": 6,
                "feeling": "good",
                "submittedAt": "2026-05-01T07:00:00Z",
            },
        ),
        (
            WeekScheduleOverride,
            "week-override.schema.json",
            {
                "uid": "user-1",
                "planId": "plan-1",
                "isoWeek": "2026-W22",
                "createdBy": "user",
                "createdAt": "2026-05-01T08:00:00Z",
                "workoutDateMap": [{"workoutId": "w1", "date": "2026-06-02"}],
            },
        ),
        (
            AgentRun,
            "agent-run.schema.json",
            {
                "id": "run-1",
                "uid": "user-1",
                "agent": "adapter",
                "trigger": "weekly_review",
                "model": "gemini-2.5-flash",
                "createdAt": "2026-05-01T09:00:00Z",
                "status": "success",
            },
        ),
    ],
)
def test_generated_model_roundtrip_matches_schema(
    model_cls: type,
    schema_name: str,
    payload: dict,
) -> None:
    model = model_cls.model_validate(payload)
    dumped = model.model_dump(mode="json", exclude_none=True)
    _assert_jsonschema_valid(dumped, schema_name)
