"""Tests for the guardrails layer."""

from __future__ import annotations

from dynamicrunner.ai.guardrails import (
    check_long_run_cap,
    check_no_back_to_back_hard,
    check_taper,
    check_weekly_volume_increase,
    validate_plan,
)


def _make_workout(date: str, wtype: str, duration_s: int = 3600) -> dict:
    return {
        "scheduledDate": date,
        "type": wtype,
        "title": f"{wtype} run",
        "estimatedDurationSec": duration_s,
        "structure": {},
    }


class TestWeeklyVolumeIncrease:
    def test_stable_volume_passes(self) -> None:
        workouts = [
            _make_workout("2026-01-05", "easy", 3600),  # W02 Mon
            _make_workout("2026-01-07", "easy", 3600),  # W02 Wed
            _make_workout("2026-01-12", "easy", 3600),  # W03 Mon
            _make_workout("2026-01-14", "easy", 3800),  # W03 Wed (~5% increase)
        ]
        failures = check_weekly_volume_increase(workouts)
        assert failures == []

    def test_excessive_increase_fails(self) -> None:
        workouts = [
            _make_workout("2026-01-05", "easy", 3000),  # W02
            _make_workout("2026-01-12", "easy", 5000),  # W03 (~67% increase)
        ]
        failures = check_weekly_volume_increase(workouts)
        assert len(failures) == 1
        assert "exceeds 10%" in failures[0]

    def test_deload_week_allowed(self) -> None:
        workouts = [
            _make_workout("2026-01-05", "easy", 5000),  # W02
            _make_workout("2026-01-12", "easy", 3000),  # W03 (deload, decrease)
        ]
        failures = check_weekly_volume_increase(workouts)
        assert failures == []

    def test_rest_days_excluded(self) -> None:
        workouts = [
            _make_workout("2026-01-05", "easy", 3600),
            _make_workout("2026-01-06", "rest", 0),
            _make_workout("2026-01-12", "easy", 3900),
        ]
        failures = check_weekly_volume_increase(workouts)
        assert failures == []


class TestNoBackToBackHard:
    def test_consecutive_hard_days_fail(self) -> None:
        workouts = [
            _make_workout("2026-01-05", "intervals"),
            _make_workout("2026-01-06", "tempo"),
        ]
        failures = check_no_back_to_back_hard(workouts)
        assert len(failures) == 1
        assert "Back-to-back" in failures[0]

    def test_hard_then_easy_passes(self) -> None:
        workouts = [
            _make_workout("2026-01-05", "intervals"),
            _make_workout("2026-01-06", "easy"),
            _make_workout("2026-01-07", "tempo"),
        ]
        failures = check_no_back_to_back_hard(workouts)
        assert failures == []

    def test_non_consecutive_hard_passes(self) -> None:
        workouts = [
            _make_workout("2026-01-05", "intervals"),
            _make_workout("2026-01-08", "threshold"),
        ]
        failures = check_no_back_to_back_hard(workouts)
        assert failures == []

    def test_easy_consecutive_passes(self) -> None:
        workouts = [
            _make_workout("2026-01-05", "easy"),
            _make_workout("2026-01-06", "easy"),
        ]
        failures = check_no_back_to_back_hard(workouts)
        assert failures == []


class TestLongRunCap:
    def test_long_run_under_35_percent_passes(self) -> None:
        workouts = [
            _make_workout("2026-01-05", "easy", 3600),
            _make_workout("2026-01-06", "easy", 3600),
            _make_workout("2026-01-07", "long", 3600),  # 33% of total
            _make_workout("2026-01-08", "easy", 3600),
        ]
        failures = check_long_run_cap(workouts)
        assert failures == []

    def test_long_run_over_35_percent_fails(self) -> None:
        workouts = [
            _make_workout("2026-01-05", "easy", 2000),
            _make_workout("2026-01-07", "long", 5000),  # 71% of total
        ]
        failures = check_long_run_cap(workouts)
        assert len(failures) == 1
        assert "35%" in failures[0]


class TestTaper:
    def test_proper_taper_passes(self) -> None:
        plan_output = {
            "plan": {"raceDate": "2026-02-01"},
            "workouts": [
                # Peak week (W03): 10000s
                _make_workout("2026-01-12", "easy", 3000),
                _make_workout("2026-01-14", "tempo", 4000),
                _make_workout("2026-01-16", "long", 3000),
                # Week before race (W04): 7000s (~70%)
                _make_workout("2026-01-19", "easy", 3000),
                _make_workout("2026-01-21", "easy", 2000),
                _make_workout("2026-01-23", "easy", 2000),
                # Race week (W05): 4000s (~40%)
                _make_workout("2026-01-26", "easy", 2000),
                _make_workout("2026-01-28", "easy", 1000),
                _make_workout("2026-01-30", "easy", 1000),
            ],
        }
        failures = check_taper(plan_output)
        assert failures == []

    def test_no_taper_fails(self) -> None:
        # Race on 2026-01-30 (W05). Peak in W03 = 10000s.
        # Race week W05 = 8000s = 80% of peak → should fail (max 60%)
        plan_output = {
            "plan": {"raceDate": "2026-01-30"},
            "workouts": [
                # W02: 8000s
                _make_workout("2026-01-05", "easy", 4000),
                _make_workout("2026-01-07", "easy", 4000),
                # W03: 10000s (peak)
                _make_workout("2026-01-12", "easy", 5000),
                _make_workout("2026-01-14", "tempo", 5000),
                # W04: 9000s
                _make_workout("2026-01-19", "easy", 4500),
                _make_workout("2026-01-21", "tempo", 4500),
                # W05 (race week): 8000s → 80% of peak — too high
                _make_workout("2026-01-26", "tempo", 4000),
                _make_workout("2026-01-28", "intervals", 4000),
            ],
        }
        failures = check_taper(plan_output)
        assert len(failures) == 1
        assert "Race week" in failures[0]


class TestValidatePlan:
    def test_valid_plan_passes(self) -> None:
        plan_output = {
            "plan": {
                "raceDate": "2026-03-01",
                "methodology": "polarized_80_20",
                "weeklyStructure": [{"isoWeek": "2026-W05"}],
            },
            "workouts": [
                _make_workout("2026-01-26", "easy", 3600),
                _make_workout("2026-01-27", "rest", 0),
                _make_workout("2026-01-28", "easy", 3600),
            ],
            "selfCritique": {
                "weeklyVolumeIncreaseOk": True,
                "tapersCorrectly": True,
                "noBackToBackHard": True,
                "longRunCapOk": True,
                "comments": "All good.",
            },
        }
        result = validate_plan(plan_output)
        assert result.passed is True
        assert result.failures == []

    def test_empty_workouts_fails(self) -> None:
        plan_output = {
            "plan": {"raceDate": "2026-03-01"},
            "workouts": [],
            "selfCritique": {},
        }
        result = validate_plan(plan_output)
        assert result.passed is False
        assert "no workouts" in result.failures[0].lower()
