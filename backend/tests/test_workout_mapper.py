"""Tests for the Garmin workout mapper."""

from __future__ import annotations

from dynamicrunner.garmin.workout_mapper import map_workout_to_garmin


class TestMapWorkoutToGarmin:
    def test_simple_easy_run(self) -> None:
        payload = {
            "title": "Easy aerobic run",
            "type": "easy",
            "estimatedDurationSec": 3000,
            "structure": {
                "mainSteps": [
                    {"kind": "duration", "seconds": 3000, "target": {"kind": "hrZone", "zone": 2}}
                ]
            },
        }
        result = map_workout_to_garmin(payload)

        assert result["workoutName"] == "Easy aerobic run"
        assert result["sportType"]["sportTypeKey"] == "running"
        assert len(result["workoutSegments"]) == 1
        steps = result["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 1
        assert steps[0]["endCondition"]["conditionTypeKey"] == "time"
        assert steps[0]["endCondition"]["conditionValue"] == 3000

    def test_warmup_main_cooldown(self) -> None:
        payload = {
            "title": "Tempo with warm/cool",
            "type": "tempo",
            "estimatedDurationSec": 4200,
            "structure": {
                "warmup": {"kind": "duration", "seconds": 600, "target": {"kind": "hrZone", "zone": 1}},
                "mainSteps": [
                    {"kind": "duration", "seconds": 1800, "target": {"kind": "pace", "minSecPerKm": 270, "maxSecPerKm": 290}}
                ],
                "cooldown": {"kind": "duration", "seconds": 600, "target": {"kind": "hrZone", "zone": 1}},
            },
        }
        result = map_workout_to_garmin(payload)
        steps = result["workoutSegments"][0]["workoutSteps"]

        assert len(steps) == 3
        assert steps[0]["stepType"]["stepTypeKey"] == "warmup"
        assert steps[1]["stepType"]["stepTypeKey"] == "interval"
        assert steps[2]["stepType"]["stepTypeKey"] == "cooldown"

    def test_repeat_block(self) -> None:
        payload = {
            "title": "8x400m intervals",
            "type": "intervals",
            "estimatedDurationSec": 3600,
            "structure": {
                "warmup": {"kind": "duration", "seconds": 600},
                "mainSteps": [
                    {
                        "kind": "repeat",
                        "repeat": 8,
                        "steps": [
                            {"kind": "distance", "meters": 400, "target": {"kind": "pace", "minSecPerKm": 210, "maxSecPerKm": 220}},
                            {"kind": "duration", "seconds": 90, "target": {"kind": "hrZone", "zone": 1}},
                        ],
                    }
                ],
                "cooldown": {"kind": "duration", "seconds": 600},
            },
        }
        result = map_workout_to_garmin(payload)
        steps = result["workoutSegments"][0]["workoutSteps"]

        assert len(steps) == 3  # warmup, repeat, cooldown
        repeat_step = steps[1]
        assert repeat_step["type"] == "RepeatGroupDTO"
        assert repeat_step["numberOfIterations"] == 8
        assert len(repeat_step["workoutSteps"]) == 2

    def test_distance_step(self) -> None:
        payload = {
            "title": "5K test",
            "type": "test",
            "estimatedDurationSec": 1500,
            "structure": {
                "mainSteps": [{"kind": "distance", "meters": 5000}]
            },
        }
        result = map_workout_to_garmin(payload)
        steps = result["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["endCondition"]["conditionTypeKey"] == "distance"
        assert steps[0]["endCondition"]["conditionValue"] == 5000

    def test_hr_zone_target(self) -> None:
        payload = {
            "title": "Zone 2 run",
            "type": "easy",
            "estimatedDurationSec": 2400,
            "structure": {
                "mainSteps": [
                    {"kind": "duration", "seconds": 2400, "target": {"kind": "hrZone", "zone": 2}}
                ]
            },
        }
        result = map_workout_to_garmin(payload)
        steps = result["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
        assert steps[0]["zoneNumber"] == 2

    def test_pace_target(self) -> None:
        payload = {
            "title": "Tempo",
            "type": "tempo",
            "estimatedDurationSec": 1800,
            "structure": {
                "mainSteps": [
                    {"kind": "duration", "seconds": 1800, "target": {"kind": "pace", "minSecPerKm": 300, "maxSecPerKm": 320}}
                ]
            },
        }
        result = map_workout_to_garmin(payload)
        steps = result["workoutSegments"][0]["workoutSteps"]
        assert steps[0]["targetType"]["workoutTargetTypeKey"] == "pace.zone"
        # Faster pace (lower sec/km) → higher m/s
        assert steps[0]["targetValueTwo"] > steps[0]["targetValueOne"]

    def test_empty_structure_defaults(self) -> None:
        payload = {
            "title": "Quick run",
            "type": "easy",
            "estimatedDurationSec": 1800,
            "structure": {},
        }
        result = map_workout_to_garmin(payload)
        steps = result["workoutSegments"][0]["workoutSteps"]
        assert len(steps) == 1
        assert steps[0]["endCondition"]["conditionValue"] == 1800

    def test_title_truncated(self) -> None:
        payload = {
            "title": "A" * 100,
            "type": "easy",
            "estimatedDurationSec": 1800,
            "structure": {"mainSteps": [{"kind": "duration", "seconds": 1800}]},
        }
        result = map_workout_to_garmin(payload)
        assert len(result["workoutName"]) == 50
