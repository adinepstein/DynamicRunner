"""Pure-Python guardrails for training plan validation.

Enforces PRD Section 10.4 rules. Used by both Planner and Adapter agents
to validate generated/modified plans before persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class GuardrailResult:
    """Result of running guardrails on a plan."""

    passed: bool
    failures: list[str]
    warnings: list[str]


# Hard workout types that should not be scheduled back-to-back
HARD_TYPES = frozenset({
    "intervals", "threshold", "tempo", "race_pace",
    "long", "hill_repeats", "fartlek",
})

# Workout types that count as "rest" or "easy"
EASY_TYPES = frozenset({"easy", "recovery", "rest", "cross_training"})


def validate_plan(plan_output: dict[str, Any]) -> GuardrailResult:
    """Run all guardrail checks on a plan output.

    Args:
        plan_output: The full plan output dict matching plan-output.schema.json.

    Returns:
        GuardrailResult with pass/fail and detailed messages.
    """
    failures: list[str] = []
    warnings: list[str] = []

    workouts = plan_output.get("workouts", [])

    if not workouts:
        failures.append("Plan contains no workouts")
        return GuardrailResult(passed=False, failures=failures, warnings=warnings)

    # Run individual checks
    failures.extend(check_weekly_volume_increase(workouts))
    failures.extend(check_no_back_to_back_hard(workouts))
    failures.extend(check_long_run_cap(workouts))
    failures.extend(check_taper(plan_output))

    # Warnings (non-blocking)
    warnings.extend(check_rest_day_frequency(workouts))
    warnings.extend(check_workout_completeness(workouts))

    return GuardrailResult(
        passed=len(failures) == 0,
        failures=failures,
        warnings=warnings,
    )


def check_weekly_volume_increase(workouts: list[dict[str, Any]]) -> list[str]:
    """Every week's volume must grow <=10% vs prior week (except deloads)."""
    failures: list[str] = []

    # Group workouts by ISO week
    weekly_volume: dict[str, float] = {}
    for w in workouts:
        wtype = w.get("type", "")
        if wtype == "rest":
            continue
        sched_date = w.get("scheduledDate", "")
        if not sched_date:
            continue

        try:
            d = date.fromisoformat(sched_date)
        except ValueError:
            continue

        iso = d.isocalendar()
        week_key = f"{iso[0]}-W{iso[1]:02d}"

        # Estimate distance from duration and type (rough heuristic)
        duration_s = w.get("estimatedDurationSec", 0) or 0
        # Use distance from structure if available, else estimate from duration
        structure = w.get("structure", {})
        distance_m = _estimate_distance(structure, duration_s, wtype)
        weekly_volume[week_key] = weekly_volume.get(week_key, 0) + distance_m

    sorted_weeks = sorted(weekly_volume.keys())

    for i in range(1, len(sorted_weeks)):
        prev_vol = weekly_volume[sorted_weeks[i - 1]]
        curr_vol = weekly_volume[sorted_weeks[i]]

        if prev_vol == 0:
            continue

        increase_pct = (curr_vol - prev_vol) / prev_vol * 100

        # Allow deload weeks (significant decrease)
        if increase_pct < 0:
            continue

        if increase_pct > 10:
            # Check if it's a recovery week following a deload
            if i >= 2:
                prev_prev = weekly_volume[sorted_weeks[i - 2]]
                if prev_vol < prev_prev * 0.8:
                    # Coming back from deload — allow up to 15%
                    if increase_pct <= 15:
                        continue

            failures.append(
                f"Week {sorted_weeks[i]}: volume increase {increase_pct:.1f}% "
                f"exceeds 10% limit (prev={prev_vol:.0f}m, curr={curr_vol:.0f}m)"
            )

    return failures


def check_no_back_to_back_hard(workouts: list[dict[str, Any]]) -> list[str]:
    """No two hard workouts on consecutive days."""
    failures: list[str] = []

    # Sort by date
    dated_workouts = []
    for w in workouts:
        sched = w.get("scheduledDate", "")
        if not sched:
            continue
        try:
            d = date.fromisoformat(sched)
            dated_workouts.append((d, w))
        except ValueError:
            continue

    dated_workouts.sort(key=lambda x: x[0])

    for i in range(1, len(dated_workouts)):
        prev_date, prev_w = dated_workouts[i - 1]
        curr_date, curr_w = dated_workouts[i]

        # Only check consecutive days
        if (curr_date - prev_date).days != 1:
            continue

        prev_type = prev_w.get("type", "")
        curr_type = curr_w.get("type", "")

        if prev_type in HARD_TYPES and curr_type in HARD_TYPES:
            failures.append(
                f"Back-to-back hard days: {prev_date.isoformat()} ({prev_type}) "
                f"→ {curr_date.isoformat()} ({curr_type})"
            )

    return failures


def check_long_run_cap(workouts: list[dict[str, Any]]) -> list[str]:
    """Long run must be <=35% of weekly volume."""
    failures: list[str] = []

    # Group by week
    weekly_data: dict[str, list[dict[str, Any]]] = {}
    for w in workouts:
        sched = w.get("scheduledDate", "")
        if not sched:
            continue
        try:
            d = date.fromisoformat(sched)
        except ValueError:
            continue

        iso = d.isocalendar()
        week_key = f"{iso[0]}-W{iso[1]:02d}"
        if week_key not in weekly_data:
            weekly_data[week_key] = []
        weekly_data[week_key].append(w)

    for week_key, week_workouts in weekly_data.items():
        total_duration = 0
        max_long_duration = 0

        for w in week_workouts:
            wtype = w.get("type", "")
            if wtype == "rest":
                continue
            dur = w.get("estimatedDurationSec", 0) or 0
            total_duration += dur
            if wtype == "long":
                max_long_duration = max(max_long_duration, dur)

        if total_duration > 0 and max_long_duration > 0:
            ratio = max_long_duration / total_duration
            if ratio > 0.35:
                failures.append(
                    f"Week {week_key}: long run is {ratio*100:.0f}% of weekly volume "
                    f"(max 35%)"
                )

    return failures


def check_taper(plan_output: dict[str, Any]) -> list[str]:
    """Validate taper: week -2 ~70% of peak, race week ~50%."""
    failures: list[str] = []

    plan = plan_output.get("plan", {})
    race_date_str = plan.get("raceDate")
    if not race_date_str:
        return failures

    try:
        race_date = date.fromisoformat(race_date_str)
    except ValueError:
        return failures

    workouts = plan_output.get("workouts", [])
    if not workouts:
        return failures

    # Group durations by ISO week
    weekly_duration: dict[str, int] = {}
    for w in workouts:
        if w.get("type") == "rest":
            continue
        sched = w.get("scheduledDate", "")
        if not sched:
            continue
        try:
            d = date.fromisoformat(sched)
        except ValueError:
            continue
        iso = d.isocalendar()
        wk = f"{iso[0]}-W{iso[1]:02d}"
        weekly_duration[wk] = weekly_duration.get(wk, 0) + (w.get("estimatedDurationSec", 0) or 0)

    if len(weekly_duration) < 4:
        return failures

    peak_duration = max(weekly_duration.values())

    # Find race week
    race_iso = race_date.isocalendar()
    race_week = f"{race_iso[0]}-W{race_iso[1]:02d}"

    if race_week in weekly_duration and peak_duration > 0:
        race_week_ratio = weekly_duration[race_week] / peak_duration
        if race_week_ratio > 0.6:
            failures.append(
                f"Race week ({race_week}) is {race_week_ratio*100:.0f}% of peak "
                f"(should be ~50%, max 60%)"
            )

    return failures


def check_rest_day_frequency(workouts: list[dict[str, Any]]) -> list[str]:
    """Warning: ensure at least 1 rest day per week."""
    warnings: list[str] = []

    weekly_rest: dict[str, int] = {}
    for w in workouts:
        sched = w.get("scheduledDate", "")
        if not sched:
            continue
        try:
            d = date.fromisoformat(sched)
        except ValueError:
            continue
        iso = d.isocalendar()
        wk = f"{iso[0]}-W{iso[1]:02d}"
        if w.get("type") == "rest":
            weekly_rest[wk] = weekly_rest.get(wk, 0) + 1
        else:
            weekly_rest.setdefault(wk, 0)

    for wk, rest_count in weekly_rest.items():
        if rest_count == 0:
            warnings.append(f"Week {wk}: no rest days scheduled")

    return warnings


def check_workout_completeness(workouts: list[dict[str, Any]]) -> list[str]:
    """Warning: check that workouts have required fields."""
    warnings: list[str] = []

    for i, w in enumerate(workouts):
        if not w.get("scheduledDate"):
            warnings.append(f"Workout {i}: missing scheduledDate")
        if not w.get("type"):
            warnings.append(f"Workout {i}: missing type")
        if not w.get("title"):
            warnings.append(f"Workout {i}: missing title")

    return warnings


def _estimate_distance(structure: dict[str, Any], duration_s: int, workout_type: str) -> float:
    """Rough distance estimate in meters from workout structure/duration/type.

    Uses average paces per type as heuristic when no explicit distance available.
    """
    # Pace estimates in m/s per workout type
    pace_map = {
        "easy": 2.5,       # ~6:40/km
        "recovery": 2.3,   # ~7:15/km
        "long": 2.5,       # ~6:40/km
        "tempo": 3.2,      # ~5:12/km
        "threshold": 3.3,  # ~5:03/km
        "intervals": 3.8,  # ~4:23/km (but includes rest)
        "race_pace": 3.5,  # ~4:46/km
        "hill_repeats": 2.8,
        "fartlek": 3.0,
    }

    pace = pace_map.get(workout_type, 2.5)
    return duration_s * pace
