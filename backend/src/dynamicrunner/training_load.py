"""Training load computation (CTL, ATL, TSB, ACWR) from daily metrics."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx

from dynamicrunner.config import Settings


def compute_training_load(
    settings: Settings, user_id: str, days: int = 42
) -> dict[str, Any]:
    """Compute training load metrics over the specified window.

    Returns daily CTL (chronic), ATL (acute), TSB (freshness), and ACWR
    values for chart rendering.
    """
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    since = (date.today() - timedelta(days=days + 30)).isoformat()

    # Fetch daily metrics for a wider window to bootstrap exponential averages
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/daily_metrics",
        params={
            "user_id": f"eq.{user_id}",
            "metric_date": f"gte.{since}",
            "select": "metric_date,payload",
            "order": "metric_date.asc",
        },
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()

    # Also fetch activities for TRIMP estimation
    resp_act = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/activities",
        params={
            "user_id": f"eq.{user_id}",
            "activity_date": f"gte.{since}",
            "select": "activity_date,payload",
            "order": "activity_date.asc",
        },
        headers=headers,
        timeout=15,
    )
    resp_act.raise_for_status()
    activities = resp_act.json()

    # Build daily training impulse (TRIMP proxy)
    daily_impulse: dict[str, float] = {}
    for act in activities:
        act_date = act.get("activity_date", "")[:10]
        payload = act.get("payload") or {}
        trimp = _estimate_trimp(payload)
        daily_impulse[act_date] = daily_impulse.get(act_date, 0) + trimp

    # Calculate exponential moving averages
    ctl = 0.0  # Chronic (42-day)
    atl = 0.0  # Acute (7-day)
    ctl_decay = 1 / 42
    atl_decay = 1 / 7

    chart_data: list[dict[str, Any]] = []
    start_date = date.today() - timedelta(days=days)

    # Bootstrap with earlier data
    bootstrap_start = date.today() - timedelta(days=days + 30)
    current = bootstrap_start
    while current <= date.today():
        d_str = current.isoformat()
        impulse = daily_impulse.get(d_str, 0.0)
        ctl = ctl + ctl_decay * (impulse - ctl)
        atl = atl + atl_decay * (impulse - atl)

        if current >= start_date:
            tsb = ctl - atl
            acwr = atl / ctl if ctl > 0 else 0.0
            chart_data.append({
                "date": d_str,
                "ctl": round(ctl, 1),
                "atl": round(atl, 1),
                "tsb": round(tsb, 1),
                "acwr": round(acwr, 2),
                "impulse": round(impulse, 1),
            })
        current += timedelta(days=1)

    # Also return HRV data for the HRV chart
    hrv_data: list[dict[str, Any]] = []
    all_hrv: list[float] = []

    for row in rows:
        payload = row.get("payload") or {}
        hrv = payload.get("hrv_last_night_avg")
        if hrv and hrv > 0:
            all_hrv.append(float(hrv))

    hrv_baseline = sum(all_hrv) / len(all_hrv) if all_hrv else None
    hrv_sd = _std_dev(all_hrv) if len(all_hrv) > 2 else None

    for row in rows:
        metric_date = row.get("metric_date", "")[:10]
        payload = row.get("payload") or {}
        hrv = payload.get("hrv_last_night_avg")
        rhr = payload.get("resting_hr")
        sleep_s = payload.get("sleeping_seconds")

        try:
            d = date.fromisoformat(metric_date)
        except ValueError:
            continue

        if d < start_date:
            continue

        hrv_data.append({
            "date": metric_date,
            "hrv": hrv,
            "rhr": rhr,
            "sleep_hours": round(sleep_s / 3600, 1) if sleep_s else None,
        })

    return {
        "training_load": chart_data,
        "hrv": hrv_data,
        "hrv_baseline": round(hrv_baseline, 1) if hrv_baseline else None,
        "hrv_sd": round(hrv_sd, 1) if hrv_sd else None,
    }


def _estimate_trimp(payload: dict[str, Any]) -> float:
    """Estimate training impulse from activity payload.

    Uses a simplified TRIMP formula: duration_minutes * intensity_factor.
    """
    duration_s = payload.get("duration") or payload.get("movingDuration") or 0
    duration_min = duration_s / 60

    avg_hr = payload.get("averageHR") or payload.get("avgHr") or 0
    max_hr = payload.get("maxHR") or payload.get("maxHr") or 0

    if avg_hr > 0 and max_hr > 0:
        # HR-based intensity
        hr_fraction = avg_hr / max_hr
        intensity = hr_fraction * 2  # Scale factor
    else:
        # Fallback: moderate intensity assumption
        intensity = 1.0

    return duration_min * intensity


def _std_dev(values: list[float]) -> float:
    """Simple standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return variance ** 0.5
