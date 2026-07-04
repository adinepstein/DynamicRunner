"""Tests for the planner agent."""

from __future__ import annotations

from dynamicrunner.ai.planner import (
    _build_user_prompt,
    _get_race_goal,
    _validate_guardrails,
)


class TestValidateGuardrails:
    def test_all_passing(self) -> None:
        plan_output = {
            "plan": {
                "raceDate": "2026-06-01",
                "methodology": "polarized_80_20",
                "weeklyStructure": [{"isoWeek": "2026-W20"}],
            },
            "workouts": [
                {"scheduledDate": "2026-05-01", "type": "easy"},
            ],
            "selfCritique": {
                "weeklyVolumeIncreaseOk": True,
                "tapersCorrectly": True,
                "noBackToBackHard": True,
                "longRunCapOk": True,
            },
        }
        failures = _validate_guardrails(plan_output)
        assert failures == []

    def test_volume_failure(self) -> None:
        plan_output = {
            "plan": {
                "raceDate": "2026-06-01",
                "methodology": "polarized_80_20",
                "weeklyStructure": [{"isoWeek": "2026-W20"}],
            },
            "workouts": [{"scheduledDate": "2026-05-01", "type": "easy"}],
            "selfCritique": {
                "weeklyVolumeIncreaseOk": False,
                "tapersCorrectly": True,
                "noBackToBackHard": True,
                "longRunCapOk": True,
            },
        }
        failures = _validate_guardrails(plan_output)
        assert any("weeklyVolumeIncreaseOk" in f for f in failures)

    def test_missing_methodology(self) -> None:
        plan_output = {
            "plan": {
                "raceDate": "2026-06-01",
                "methodology": "",
                "weeklyStructure": [],
            },
            "workouts": [{"scheduledDate": "2026-05-01", "type": "easy"}],
            "selfCritique": {
                "weeklyVolumeIncreaseOk": True,
                "tapersCorrectly": True,
                "noBackToBackHard": True,
                "longRunCapOk": True,
            },
        }
        failures = _validate_guardrails(plan_output)
        assert any("methodology" in f.lower() for f in failures)

    def test_no_workouts(self) -> None:
        plan_output = {
            "plan": {"raceDate": "2026-06-01", "methodology": "x", "weeklyStructure": [{}]},
            "workouts": [],
            "selfCritique": {
                "weeklyVolumeIncreaseOk": True,
                "tapersCorrectly": True,
                "noBackToBackHard": True,
                "longRunCapOk": True,
            },
        }
        failures = _validate_guardrails(plan_output)
        assert any("No workouts" in f for f in failures)


class TestGetRaceGoal:
    def test_extracts_goal(self) -> None:
        profile = {"raceGoal": {"distance": "half_marathon", "date": "2026-09-01"}}
        goal = _get_race_goal(profile)
        assert goal["distance"] == "half_marathon"

    def test_missing_goal(self) -> None:
        assert _get_race_goal({}) == {}


class TestBuildUserPrompt:
    def test_builds_json(self) -> None:
        prompt = _build_user_prompt(
            {"age": 35, "sex": "male"},
            {"avg_weekly_km": 40.0},
            {"distance": "10k", "date": "2026-09-20"},
        )
        assert "35" in prompt
        assert "40.0" in prompt
        assert "10k" in prompt
