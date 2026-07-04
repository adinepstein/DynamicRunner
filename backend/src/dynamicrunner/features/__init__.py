"""Feature extraction service.

Processes synced Garmin activities and daily metrics into structured training
features that the AI planner can use to assess fitness, fatigue, and readiness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx
import structlog

from dynamicrunner.config import Settings

log = structlog.get_logger(__name__)


@dataclass
class WeeklySummary:
    """Aggregated training features for one ISO week."""

    iso_week: str
    total_distance_m: float = 0
    total_duration_s: float = 0
    run_count: int = 0
    longest_run_m: float = 0
    avg_pace_s_per_km: float | None = None
    avg_hr: float | None = None
    elevation_gain_m: float = 0
    avg_resting_hr: float | None = None
    avg_hrv: float | None = None
    avg_sleep_hours: float | None = None
    avg_body_battery: float | None = None
    avg_stress: float | None = None
    intensity_score: float = 0


@dataclass
class TrainingFeatures:
    """Full feature set derived from raw Garmin data for a user."""

    user_id: str
    computed_at: str = ""
    weeks_available: int = 0
    weekly_summaries: list[WeeklySummary] = field(default_factory=list)
    current_weekly_volume_m: float = 0
    peak_weekly_volume_m: float = 0
    avg_weekly_volume_m: float = 0
    trend_direction: str = "stable"  # increasing, decreasing, stable
    estimated_vo2max: float | None = None
    avg_resting_hr: float | None = None
    recent_race_performances: list[dict[str, Any]] = field(default_factory=list)


def _fetch_activities(settings: Settings, user_id: str, since: date) -> list[dict[str, Any]]:
    """Fetch all activities from Supabase for user since given date."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/activities",
        params={
            "user_id": f"eq.{user_id}",
            "activity_date": f"gte.{since.isoformat()}",
            "order": "activity_date.asc",
            "select": "activity_date,payload",
        },
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_daily_metrics(settings: Settings, user_id: str, since: date) -> list[dict[str, Any]]:
    """Fetch all daily metrics from Supabase for user since given date."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/daily_metrics",
        params={
            "user_id": f"eq.{user_id}",
            "metric_date": f"gte.{since.isoformat()}",
            "order": "metric_date.asc",
            "select": "metric_date,payload",
        },
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _is_running_activity(payload: dict[str, Any]) -> bool:
    """Check if activity is a running type."""
    type_key = payload.get("activityType", {}).get("typeKey", "")
    return type_key in ("running", "trail_running", "treadmill_running", "track_running")


def _iso_week_key(d: date) -> str:
    """ISO week string like '2026-W03'."""
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _compute_weekly_summaries(
    activities: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> list[WeeklySummary]:
    """Group activities and metrics by ISO week and compute summaries."""
    week_data: dict[str, dict[str, Any]] = {}

    for row in activities:
        payload = row.get("payload", {})
        if not _is_running_activity(payload):
            continue

        act_date = date.fromisoformat(row["activity_date"])
        wk = _iso_week_key(act_date)

        if wk not in week_data:
            week_data[wk] = {
                "distances": [],
                "durations": [],
                "hrs": [],
                "elevations": [],
            }

        distance = payload.get("distance", 0) or 0
        duration = payload.get("duration", 0) or 0
        avg_hr = payload.get("averageHR", 0) or 0
        elev = payload.get("elevationGain", 0) or 0

        week_data[wk]["distances"].append(float(distance))
        week_data[wk]["durations"].append(float(duration))
        if avg_hr > 0:
            week_data[wk]["hrs"].append(float(avg_hr))
        week_data[wk]["elevations"].append(float(elev))

    # Metrics by week
    metrics_by_week: dict[str, dict[str, list[float]]] = {}
    for row in metrics:
        payload = row.get("payload", {})
        met_date = date.fromisoformat(row["metric_date"])
        wk = _iso_week_key(met_date)

        if wk not in metrics_by_week:
            metrics_by_week[wk] = {
                "resting_hrs": [],
                "hrvs": [],
                "sleep_hours": [],
                "body_battery": [],
                "stress": [],
            }

        rhr = payload.get("resting_hr")
        if rhr and rhr > 0:
            metrics_by_week[wk]["resting_hrs"].append(float(rhr))

        hrv = payload.get("hrv_last_night_avg")
        if hrv and hrv > 0:
            metrics_by_week[wk]["hrvs"].append(float(hrv))

        sleep_s = payload.get("sleeping_seconds")
        if sleep_s and sleep_s > 0:
            metrics_by_week[wk]["sleep_hours"].append(float(sleep_s) / 3600)

        bb_high = payload.get("body_battery_high")
        if bb_high and bb_high > 0:
            metrics_by_week[wk]["body_battery"].append(float(bb_high))

        stress = payload.get("average_stress")
        if stress and stress > 0:
            metrics_by_week[wk]["stress"].append(float(stress))

    # Build summaries
    all_weeks = sorted(set(list(week_data.keys()) + list(metrics_by_week.keys())))
    summaries: list[WeeklySummary] = []

    for wk in all_weeks:
        wd = week_data.get(wk, {"distances": [], "durations": [], "hrs": [], "elevations": []})
        md = metrics_by_week.get(wk, {"resting_hrs": [], "hrvs": [], "sleep_hours": [], "body_battery": [], "stress": []})

        total_dist = sum(wd["distances"])
        total_dur = sum(wd["durations"])
        run_count = len(wd["distances"])
        longest = max(wd["distances"]) if wd["distances"] else 0

        avg_pace = None
        if total_dist > 0:
            avg_pace = (total_dur / (total_dist / 1000))

        avg_hr = sum(wd["hrs"]) / len(wd["hrs"]) if wd["hrs"] else None
        elev_gain = sum(wd["elevations"])

        # Intensity: simple TRIMP-like score (duration * avg_hr_fraction)
        intensity = 0.0
        if avg_hr and avg_hr > 60:
            hr_fraction = (avg_hr - 60) / 120  # rough scaling
            intensity = total_dur / 60 * hr_fraction

        summary = WeeklySummary(
            iso_week=wk,
            total_distance_m=total_dist,
            total_duration_s=total_dur,
            run_count=run_count,
            longest_run_m=longest,
            avg_pace_s_per_km=avg_pace,
            avg_hr=avg_hr,
            elevation_gain_m=elev_gain,
            avg_resting_hr=_safe_avg(md["resting_hrs"]),
            avg_hrv=_safe_avg(md["hrvs"]),
            avg_sleep_hours=_safe_avg(md["sleep_hours"]),
            avg_body_battery=_safe_avg(md["body_battery"]),
            avg_stress=_safe_avg(md["stress"]),
            intensity_score=intensity,
        )
        summaries.append(summary)

    return summaries


def _safe_avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _detect_trend(summaries: list[WeeklySummary], window: int = 4) -> str:
    """Detect volume trend over the last N weeks."""
    if len(summaries) < window:
        return "stable"

    recent = summaries[-window:]
    volumes = [s.total_distance_m for s in recent]

    if len(volumes) < 2:
        return "stable"

    first_half = sum(volumes[: len(volumes) // 2])
    second_half = sum(volumes[len(volumes) // 2 :])

    if second_half > first_half * 1.15:
        return "increasing"
    elif second_half < first_half * 0.85:
        return "decreasing"
    return "stable"


def extract_features(settings: Settings, user_id: str, days: int = 90) -> TrainingFeatures:
    """Extract training features for a user from their synced data.

    Returns a TrainingFeatures object ready for the AI planner prompt.
    """
    since = date.today() - timedelta(days=days)

    activities = _fetch_activities(settings, user_id, since)
    metrics = _fetch_daily_metrics(settings, user_id, since)

    log.info(
        "features.loaded_data",
        user_id=user_id,
        activity_count=len(activities),
        metric_days=len(metrics),
    )

    weekly_summaries = _compute_weekly_summaries(activities, metrics)

    volumes = [s.total_distance_m for s in weekly_summaries]
    current_vol = volumes[-1] if volumes else 0
    peak_vol = max(volumes) if volumes else 0
    avg_vol = sum(volumes) / len(volumes) if volumes else 0

    trend = _detect_trend(weekly_summaries)

    all_resting_hrs = [
        s.avg_resting_hr for s in weekly_summaries if s.avg_resting_hr is not None
    ]
    avg_rhr = _safe_avg(all_resting_hrs)

    features = TrainingFeatures(
        user_id=user_id,
        computed_at=date.today().isoformat(),
        weeks_available=len(weekly_summaries),
        weekly_summaries=weekly_summaries,
        current_weekly_volume_m=current_vol,
        peak_weekly_volume_m=peak_vol,
        avg_weekly_volume_m=avg_vol,
        trend_direction=trend,
        avg_resting_hr=avg_rhr,
    )

    log.info(
        "features.extracted",
        user_id=user_id,
        weeks=features.weeks_available,
        avg_volume_km=round(avg_vol / 1000, 1),
        trend=trend,
    )

    return features


def features_to_prompt_context(features: TrainingFeatures) -> dict[str, Any]:
    """Convert TrainingFeatures to a dict suitable for AI prompt injection."""
    recent_weeks = features.weekly_summaries[-6:] if features.weekly_summaries else []

    return {
        "weeks_of_data": features.weeks_available,
        "current_weekly_km": round(features.current_weekly_volume_m / 1000, 1),
        "peak_weekly_km": round(features.peak_weekly_volume_m / 1000, 1),
        "avg_weekly_km": round(features.avg_weekly_volume_m / 1000, 1),
        "trend": features.trend_direction,
        "avg_resting_hr": features.avg_resting_hr,
        "estimated_vo2max": features.estimated_vo2max,
        "recent_weeks": [
            {
                "week": s.iso_week,
                "distance_km": round(s.total_distance_m / 1000, 1),
                "runs": s.run_count,
                "longest_km": round(s.longest_run_m / 1000, 1),
                "avg_pace_min_km": (
                    f"{int(s.avg_pace_s_per_km // 60)}:{int(s.avg_pace_s_per_km % 60):02d}"
                    if s.avg_pace_s_per_km
                    else None
                ),
                "avg_hr": round(s.avg_hr) if s.avg_hr else None,
                "avg_hrv": round(s.avg_hrv, 1) if s.avg_hrv else None,
                "avg_sleep_h": round(s.avg_sleep_hours, 1) if s.avg_sleep_hours else None,
                "intensity": round(s.intensity_score, 1),
            }
            for s in recent_weeks
        ],
    }
