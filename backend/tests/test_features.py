"""Tests for feature extraction service."""

from __future__ import annotations

from datetime import date

from dynamicrunner.features import (
    TrainingFeatures,
    WeeklySummary,
    _compute_weekly_summaries,
    _detect_trend,
    _is_running_activity,
    _iso_week_key,
    features_to_prompt_context,
)


class TestIsRunningActivity:
    def test_running(self) -> None:
        payload = {"activityType": {"typeKey": "running"}}
        assert _is_running_activity(payload) is True

    def test_trail_running(self) -> None:
        payload = {"activityType": {"typeKey": "trail_running"}}
        assert _is_running_activity(payload) is True

    def test_cycling_not_running(self) -> None:
        payload = {"activityType": {"typeKey": "cycling"}}
        assert _is_running_activity(payload) is False

    def test_empty_payload(self) -> None:
        assert _is_running_activity({}) is False


class TestIsoWeekKey:
    def test_known_date(self) -> None:
        d = date(2026, 1, 5)  # Monday of week 2
        assert _iso_week_key(d) == "2026-W02"

    def test_year_boundary(self) -> None:
        d = date(2025, 12, 29)  # ISO week 1 of 2026
        assert _iso_week_key(d) == "2026-W01"


class TestComputeWeeklySummaries:
    def test_empty_data(self) -> None:
        result = _compute_weekly_summaries([], [])
        assert result == []

    def test_single_activity(self) -> None:
        activities = [
            {
                "activity_date": "2026-01-05",
                "payload": {
                    "activityType": {"typeKey": "running"},
                    "distance": 10000,
                    "duration": 3000,
                    "averageHR": 150,
                    "elevationGain": 50,
                },
            }
        ]
        result = _compute_weekly_summaries(activities, [])
        assert len(result) == 1
        assert result[0].iso_week == "2026-W02"
        assert result[0].total_distance_m == 10000
        assert result[0].run_count == 1

    def test_non_running_excluded(self) -> None:
        activities = [
            {
                "activity_date": "2026-01-05",
                "payload": {
                    "activityType": {"typeKey": "cycling"},
                    "distance": 50000,
                    "duration": 7200,
                },
            }
        ]
        result = _compute_weekly_summaries(activities, [])
        assert result == []

    def test_metrics_aggregation(self) -> None:
        metrics = [
            {
                "metric_date": "2026-01-05",
                "payload": {
                    "resting_hr": 55,
                    "hrv_last_night_avg": 45,
                    "sleeping_seconds": 28800,
                    "body_battery_high": 80,
                    "average_stress": 30,
                },
            },
            {
                "metric_date": "2026-01-06",
                "payload": {
                    "resting_hr": 57,
                    "hrv_last_night_avg": 42,
                    "sleeping_seconds": 25200,
                    "body_battery_high": 75,
                    "average_stress": 35,
                },
            },
        ]
        result = _compute_weekly_summaries([], metrics)
        assert len(result) == 1
        assert result[0].avg_resting_hr == 56.0
        assert result[0].avg_hrv == 43.5


class TestDetectTrend:
    def test_increasing(self) -> None:
        summaries = [
            WeeklySummary(iso_week="W01", total_distance_m=20000),
            WeeklySummary(iso_week="W02", total_distance_m=22000),
            WeeklySummary(iso_week="W03", total_distance_m=30000),
            WeeklySummary(iso_week="W04", total_distance_m=35000),
        ]
        assert _detect_trend(summaries) == "increasing"

    def test_decreasing(self) -> None:
        summaries = [
            WeeklySummary(iso_week="W01", total_distance_m=40000),
            WeeklySummary(iso_week="W02", total_distance_m=38000),
            WeeklySummary(iso_week="W03", total_distance_m=20000),
            WeeklySummary(iso_week="W04", total_distance_m=15000),
        ]
        assert _detect_trend(summaries) == "decreasing"

    def test_stable(self) -> None:
        summaries = [
            WeeklySummary(iso_week="W01", total_distance_m=30000),
            WeeklySummary(iso_week="W02", total_distance_m=31000),
            WeeklySummary(iso_week="W03", total_distance_m=29000),
            WeeklySummary(iso_week="W04", total_distance_m=30000),
        ]
        assert _detect_trend(summaries) == "stable"

    def test_too_few_weeks(self) -> None:
        summaries = [WeeklySummary(iso_week="W01", total_distance_m=30000)]
        assert _detect_trend(summaries) == "stable"


class TestFeaturesToPromptContext:
    def test_basic_conversion(self) -> None:
        features = TrainingFeatures(
            user_id="test-uid",
            computed_at="2026-01-10",
            weeks_available=4,
            weekly_summaries=[
                WeeklySummary(
                    iso_week="2026-W02",
                    total_distance_m=30000,
                    total_duration_s=9000,
                    run_count=3,
                    longest_run_m=12000,
                    avg_pace_s_per_km=300.0,
                    avg_hr=150,
                    avg_hrv=45.0,
                    avg_sleep_hours=7.5,
                    intensity_score=112.5,
                ),
            ],
            current_weekly_volume_m=30000,
            peak_weekly_volume_m=35000,
            avg_weekly_volume_m=28000,
            trend_direction="increasing",
            avg_resting_hr=55.0,
        )
        ctx = features_to_prompt_context(features)

        assert ctx["weeks_of_data"] == 4
        assert ctx["current_weekly_km"] == 30.0
        assert ctx["trend"] == "increasing"
        assert ctx["avg_resting_hr"] == 55.0
        assert len(ctx["recent_weeks"]) == 1
        assert ctx["recent_weeks"][0]["distance_km"] == 30.0
        assert ctx["recent_weeks"][0]["avg_pace_min_km"] == "5:00"
