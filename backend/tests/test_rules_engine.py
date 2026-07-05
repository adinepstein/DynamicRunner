"""Tests for the deterministic rules engine."""

from __future__ import annotations

from datetime import date

from dynamicrunner.adaptation import (
    RulesContext,
    rule_feeling_wrecked,
    rule_hrv_drop,
    rule_missed_workout,
    rule_rhr_elevated,
    rule_sleep_deficit,
    run_rules,
)


def _make_context(**kwargs) -> RulesContext:
    defaults = {
        "user_id": "test-user",
        "today": date(2026, 6, 10),
        "upcoming_workouts": [],
        "recent_activities": [],
        "daily_metrics": [],
        "checkins": [],
        "hrv_baseline": None,
        "rhr_baseline": None,
    }
    defaults.update(kwargs)
    return RulesContext(**defaults)


def _make_workout(workout_id: str, sched_date: str, wtype: str, status: str = "planned"):
    return {
        "id": workout_id,
        "payload": {
            "scheduledDate": sched_date,
            "type": wtype,
            "status": status,
            "title": f"{wtype} run",
        },
    }


class TestMissedWorkout:
    def test_moves_missed_to_today(self) -> None:
        yesterday = date(2026, 6, 9).isoformat()
        ctx = _make_context(
            upcoming_workouts=[_make_workout("w1", yesterday, "tempo")],
        )
        decisions = rule_missed_workout(ctx)
        assert len(decisions) == 1
        assert decisions[0].action == "move"
        assert decisions[0].new_date == "2026-06-10"

    def test_skips_if_today_has_hard(self) -> None:
        yesterday = date(2026, 6, 9).isoformat()
        today = date(2026, 6, 10).isoformat()
        ctx = _make_context(
            upcoming_workouts=[
                _make_workout("w1", yesterday, "intervals"),
                _make_workout("w2", today, "tempo"),
            ],
        )
        decisions = rule_missed_workout(ctx)
        assert len(decisions) == 1
        assert decisions[0].action == "skip"

    def test_ignores_completed(self) -> None:
        yesterday = date(2026, 6, 9).isoformat()
        ctx = _make_context(
            upcoming_workouts=[_make_workout("w1", yesterday, "tempo", status="completed")],
        )
        decisions = rule_missed_workout(ctx)
        assert decisions == []

    def test_ignores_rest_days(self) -> None:
        yesterday = date(2026, 6, 9).isoformat()
        ctx = _make_context(
            upcoming_workouts=[_make_workout("w1", yesterday, "rest")],
        )
        decisions = rule_missed_workout(ctx)
        assert decisions == []


class TestRhrElevated:
    def test_triggers_on_elevated_rhr(self) -> None:
        metrics = [
            {"payload": {"resting_hr": 65}},
            {"payload": {"resting_hr": 66}},
            {"payload": {"resting_hr": 64}},
        ]
        ctx = _make_context(
            rhr_baseline=55.0,
            daily_metrics=metrics,
            upcoming_workouts=[
                _make_workout("w1", "2026-06-10", "intervals"),
                _make_workout("w2", "2026-06-11", "tempo"),
            ],
        )
        decisions = rule_rhr_elevated(ctx)
        assert len(decisions) == 2
        assert all(d.action == "downgrade" for d in decisions)
        assert all(d.new_type == "easy" for d in decisions)

    def test_no_trigger_normal_rhr(self) -> None:
        metrics = [
            {"payload": {"resting_hr": 56}},
            {"payload": {"resting_hr": 55}},
            {"payload": {"resting_hr": 57}},
        ]
        ctx = _make_context(
            rhr_baseline=55.0,
            daily_metrics=metrics,
            upcoming_workouts=[_make_workout("w1", "2026-06-10", "intervals")],
        )
        decisions = rule_rhr_elevated(ctx)
        assert decisions == []


class TestHrvDrop:
    def test_triggers_on_low_hrv(self) -> None:
        # Baseline 45, SD ~6.75, threshold ~38.25
        metrics = [
            {"payload": {"hrv_last_night_avg": 35}},
            {"payload": {"hrv_last_night_avg": 33}},
            {"payload": {"hrv_last_night_avg": 36}},
            {"payload": {"hrv_last_night_avg": 34}},
            {"payload": {"hrv_last_night_avg": 37}},
        ]
        ctx = _make_context(
            hrv_baseline=45.0,
            daily_metrics=metrics,
            upcoming_workouts=[
                _make_workout("w1", "2026-06-10", "intervals"),
                _make_workout("w2", "2026-06-11", "tempo"),
                _make_workout("w3", "2026-06-12", "easy"),
            ],
        )
        decisions = rule_hrv_drop(ctx)
        assert len(decisions) == 2  # Max 2 hard downgraded
        assert all(d.new_type == "easy" for d in decisions)

    def test_no_trigger_normal_hrv(self) -> None:
        metrics = [
            {"payload": {"hrv_last_night_avg": 44}},
            {"payload": {"hrv_last_night_avg": 46}},
            {"payload": {"hrv_last_night_avg": 43}},
        ]
        ctx = _make_context(
            hrv_baseline=45.0,
            daily_metrics=metrics,
            upcoming_workouts=[_make_workout("w1", "2026-06-10", "intervals")],
        )
        decisions = rule_hrv_drop(ctx)
        assert decisions == []


class TestSleepDeficit:
    def test_triggers_on_low_sleep(self) -> None:
        metrics = [
            {"payload": {"sleeping_seconds": 18000}},  # 5h
            {"payload": {"sleeping_seconds": 19000}},  # 5.3h
            {"payload": {"sleeping_seconds": 17000}},  # 4.7h
            {"payload": {"sleeping_seconds": 20000}},  # 5.5h
            {"payload": {"sleeping_seconds": 19500}},  # 5.4h
        ]
        ctx = _make_context(
            daily_metrics=metrics,
            upcoming_workouts=[_make_workout("w1", "2026-06-10", "tempo")],
        )
        decisions = rule_sleep_deficit(ctx)
        assert len(decisions) == 1
        assert decisions[0].action == "modify"

    def test_no_trigger_good_sleep(self) -> None:
        metrics = [
            {"payload": {"sleeping_seconds": 28800}},  # 8h
            {"payload": {"sleeping_seconds": 27000}},  # 7.5h
        ]
        ctx = _make_context(
            daily_metrics=metrics,
            upcoming_workouts=[_make_workout("w1", "2026-06-10", "tempo")],
        )
        decisions = rule_sleep_deficit(ctx)
        assert decisions == []


class TestFeelingWrecked:
    def test_triggers_on_wrecked(self) -> None:
        checkins = [
            {"payload": {"feeling": "wrecked", "rpe": 9}},
            {"payload": {"feeling": "sore", "rpe": 8}},
        ]
        ctx = _make_context(
            checkins=checkins,
            upcoming_workouts=[_make_workout("w1", "2026-06-10", "intervals")],
        )
        decisions = rule_feeling_wrecked(ctx)
        assert len(decisions) == 1
        assert decisions[0].action == "insert_rest"

    def test_no_trigger_good_feeling(self) -> None:
        checkins = [
            {"payload": {"feeling": "good", "rpe": 6}},
            {"payload": {"feeling": "great", "rpe": 5}},
        ]
        ctx = _make_context(
            checkins=checkins,
            upcoming_workouts=[_make_workout("w1", "2026-06-10", "intervals")],
        )
        decisions = rule_feeling_wrecked(ctx)
        assert decisions == []


class TestRunRules:
    def test_empty_context_no_decisions(self) -> None:
        ctx = _make_context()
        decisions = run_rules(ctx)
        assert decisions == []

    def test_multiple_rules_fire(self) -> None:
        yesterday = date(2026, 6, 9).isoformat()
        ctx = _make_context(
            rhr_baseline=55.0,
            daily_metrics=[
                {"payload": {"resting_hr": 65}},
                {"payload": {"resting_hr": 66}},
                {"payload": {"resting_hr": 64}},
            ],
            upcoming_workouts=[
                _make_workout("w1", yesterday, "tempo"),
                _make_workout("w2", "2026-06-10", "intervals"),
                _make_workout("w3", "2026-06-11", "long"),
            ],
        )
        decisions = run_rules(ctx)
        # Should have both missed workout and RHR decisions
        assert len(decisions) >= 2
