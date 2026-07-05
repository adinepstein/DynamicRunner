"""Deterministic rules engine for plan adaptation.

Implements PRD Section 12 rules as pure functions. Called before the Adapter
agent to handle clear-cut cases without needing AI judgement.

Rules:
- Missed workout → move to next day (unless it creates back-to-back hard)
- HRV drop → downgrade hard to easy
- Sleep deficit → reduce volume
- RHR elevated → force easy until normalized
- ACWR breach → cap at zone 2
- Back-to-back hard prevention
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


@dataclass
class RuleDecision:
    """A single decision made by the rules engine."""

    rule: str
    workout_id: str
    action: str  # move, modify, insert_rest, skip, downgrade
    reason: str
    new_date: str | None = None
    new_type: str | None = None
    signal_values: dict[str, Any] = field(default_factory=dict)


@dataclass
class RulesContext:
    """All data needed for the rules engine to make decisions."""

    user_id: str
    today: date
    upcoming_workouts: list[dict[str, Any]]  # next 14 days
    recent_activities: list[dict[str, Any]]  # last 7 days
    daily_metrics: list[dict[str, Any]]  # last 7 days
    checkins: list[dict[str, Any]]  # last 7 days
    hrv_baseline: float | None = None  # 28-day average
    rhr_baseline: float | None = None  # 28-day average


HARD_TYPES = frozenset({
    "intervals", "threshold", "tempo", "race_pace",
    "long", "hill_repeats", "fartlek", "hills",
})


def run_rules(context: RulesContext) -> list[RuleDecision]:
    """Run all deterministic rules and return decisions.

    Rules are evaluated in priority order. Later rules respect
    earlier decisions (e.g., won't move a workout to a day already
    occupied by a previous move).
    """
    decisions: list[RuleDecision] = []

    decisions.extend(rule_missed_workout(context))
    decisions.extend(rule_rhr_elevated(context))
    decisions.extend(rule_hrv_drop(context))
    decisions.extend(rule_sleep_deficit(context))
    decisions.extend(rule_acwr_breach(context))
    decisions.extend(rule_feeling_wrecked(context))

    return decisions


def rule_missed_workout(context: RulesContext) -> list[RuleDecision]:
    """If a workout was missed yesterday, move it to today (if possible)."""
    decisions: list[RuleDecision] = []

    yesterday = context.today - timedelta(days=1)

    # Find workouts scheduled for yesterday that weren't completed
    for w in context.upcoming_workouts:
        payload = w.get("payload", {})
        sched = payload.get("scheduledDate", "")
        if not sched:
            continue

        try:
            sched_date = date.fromisoformat(sched)
        except ValueError:
            continue

        if sched_date != yesterday:
            continue

        if payload.get("status") == "completed":
            continue
        if payload.get("type") == "rest":
            continue

        # Check if there's already a workout today
        today_str = context.today.isoformat()
        today_has_hard = any(
            _is_hard(wo.get("payload", {}))
            for wo in context.upcoming_workouts
            if wo.get("payload", {}).get("scheduledDate") == today_str
        )

        is_hard = _is_hard(payload)

        # Don't create back-to-back hard days
        if is_hard and today_has_hard:
            decisions.append(RuleDecision(
                rule="missed_workout_skip",
                workout_id=w["id"],
                action="skip",
                reason=f"Missed {payload.get('type', 'workout')} on {sched} — "
                       f"cannot reschedule today (back-to-back hard). Marked as skipped.",
            ))
        else:
            decisions.append(RuleDecision(
                rule="missed_workout_move",
                workout_id=w["id"],
                action="move",
                reason=f"Missed {payload.get('type', 'workout')} on {sched} — "
                       f"moved to today ({today_str}) since recovery signals allow it.",
                new_date=today_str,
            ))

    return decisions


def rule_rhr_elevated(context: RulesContext) -> list[RuleDecision]:
    """RHR elevated >7 bpm above baseline for 2+ days → force easy."""
    decisions: list[RuleDecision] = []

    if context.rhr_baseline is None:
        return decisions

    threshold = context.rhr_baseline + 7
    elevated_days = 0

    for m in context.daily_metrics[-3:]:
        payload = m.get("payload", {})
        rhr = payload.get("resting_hr")
        if rhr and rhr > threshold:
            elevated_days += 1

    if elevated_days < 2:
        return decisions

    # Downgrade all hard workouts in next 3 days to easy
    for w in context.upcoming_workouts:
        payload = w.get("payload", {})
        sched = payload.get("scheduledDate", "")
        if not sched:
            continue

        try:
            sched_date = date.fromisoformat(sched)
        except ValueError:
            continue

        days_out = (sched_date - context.today).days
        if days_out < 0 or days_out > 3:
            continue

        if _is_hard(payload):
            decisions.append(RuleDecision(
                rule="rhr_elevated",
                workout_id=w["id"],
                action="downgrade",
                reason=f"RHR elevated ({elevated_days} days above baseline of "
                       f"{context.rhr_baseline:.0f} bpm). Downgrading to easy run "
                       f"until normalized.",
                new_type="easy",
                signal_values={"rhr_baseline": context.rhr_baseline, "elevated_days": elevated_days},
            ))

    return decisions


def rule_hrv_drop(context: RulesContext) -> list[RuleDecision]:
    """HRV trending down >1 SD for 3+ days → downgrade 1-2 hard workouts."""
    decisions: list[RuleDecision] = []

    if context.hrv_baseline is None:
        return decisions

    # Simple SD approximation: 15% of baseline
    sd_estimate = context.hrv_baseline * 0.15
    low_threshold = context.hrv_baseline - sd_estimate

    low_days = 0
    recent_hrv_values: list[float] = []

    for m in context.daily_metrics[-5:]:
        payload = m.get("payload", {})
        hrv = payload.get("hrv_last_night_avg")
        if hrv and hrv > 0:
            recent_hrv_values.append(hrv)
            if hrv < low_threshold:
                low_days += 1

    if low_days < 3:
        return decisions

    avg_recent = sum(recent_hrv_values) / len(recent_hrv_values) if recent_hrv_values else 0

    # Downgrade next 2 hard workouts
    downgraded = 0
    for w in context.upcoming_workouts:
        if downgraded >= 2:
            break

        payload = w.get("payload", {})
        sched = payload.get("scheduledDate", "")
        if not sched:
            continue

        try:
            sched_date = date.fromisoformat(sched)
        except ValueError:
            continue

        if sched_date < context.today:
            continue

        if _is_hard(payload):
            decisions.append(RuleDecision(
                rule="hrv_drop",
                workout_id=w["id"],
                action="downgrade",
                reason=f"HRV trending low ({avg_recent:.0f} ms vs {context.hrv_baseline:.0f} ms "
                       f"baseline, {low_days} days below threshold). "
                       f"Reducing intensity to protect recovery.",
                new_type="easy",
                signal_values={"hrv_baseline": context.hrv_baseline, "avg_recent": avg_recent},
            ))
            downgraded += 1

    return decisions


def rule_sleep_deficit(context: RulesContext) -> list[RuleDecision]:
    """Sleep averaging <6h for 5+ days → reduce volume on next hard workout."""
    decisions: list[RuleDecision] = []

    low_sleep_days = 0
    for m in context.daily_metrics[-5:]:
        payload = m.get("payload", {})
        sleep_s = payload.get("sleeping_seconds")
        if sleep_s and sleep_s < 6 * 3600:
            low_sleep_days += 1

    if low_sleep_days < 3:
        return decisions

    # Find next hard workout and reduce duration by 25%
    for w in context.upcoming_workouts:
        payload = w.get("payload", {})
        sched = payload.get("scheduledDate", "")
        if not sched:
            continue

        try:
            sched_date = date.fromisoformat(sched)
        except ValueError:
            continue

        if sched_date < context.today:
            continue

        if _is_hard(payload):
            decisions.append(RuleDecision(
                rule="sleep_deficit",
                workout_id=w["id"],
                action="modify",
                reason=f"Sleep averaging under 6 hours for {low_sleep_days} of the last "
                       f"5 nights. Reducing duration by 25% to account for "
                       f"accumulated fatigue.",
                signal_values={"low_sleep_days": low_sleep_days},
            ))
            break

    return decisions


def rule_acwr_breach(context: RulesContext) -> list[RuleDecision]:
    """ACWR >1.5 → cap next 3 days at zone 2."""
    decisions: list[RuleDecision] = []

    # Simple ACWR estimation from recent vs chronic load
    # Using daily metrics stress as proxy
    recent_load = 0.0
    days_with_data = 0

    for m in context.daily_metrics:
        payload = m.get("payload", {})
        stress = payload.get("average_stress", 0) or 0
        days_with_data += 1
        recent_load += stress

    if days_with_data < 5:
        return decisions

    # Very rough ACWR proxy
    avg_recent = recent_load / min(days_with_data, 7)
    # Assume chronic is ~70% of recent on average (baseline assumption)
    chronic_estimate = avg_recent * 0.7

    if chronic_estimate == 0:
        return decisions

    acwr = avg_recent / chronic_estimate

    if acwr <= 1.5:
        return decisions

    # Cap next 3 days at easy
    capped = 0
    for w in context.upcoming_workouts:
        if capped >= 3:
            break

        payload = w.get("payload", {})
        sched = payload.get("scheduledDate", "")
        if not sched:
            continue

        try:
            sched_date = date.fromisoformat(sched)
        except ValueError:
            continue

        days_out = (sched_date - context.today).days
        if days_out < 0 or days_out > 3:
            continue

        if _is_hard(payload):
            decisions.append(RuleDecision(
                rule="acwr_breach",
                workout_id=w["id"],
                action="downgrade",
                reason=f"Training load ratio elevated (ACWR ~{acwr:.1f}). "
                       f"Capping intensity at zone 2 for the next 3 days to "
                       f"reduce injury risk.",
                new_type="easy",
                signal_values={"acwr": acwr},
            ))
            capped += 1

    return decisions


def rule_feeling_wrecked(context: RulesContext) -> list[RuleDecision]:
    """User reported 'wrecked' or 'sore' on 2+ check-ins → insert rest or reduce."""
    decisions: list[RuleDecision] = []

    bad_feeling_count = 0
    for c in context.checkins:
        payload = c.get("payload", {})
        feeling = payload.get("feeling", "")
        if feeling in ("wrecked", "sore"):
            bad_feeling_count += 1

    if bad_feeling_count < 2:
        return decisions

    # Convert next hard workout to rest
    for w in context.upcoming_workouts:
        payload = w.get("payload", {})
        sched = payload.get("scheduledDate", "")
        if not sched:
            continue

        try:
            sched_date = date.fromisoformat(sched)
        except ValueError:
            continue

        if sched_date < context.today:
            continue

        if _is_hard(payload):
            decisions.append(RuleDecision(
                rule="feeling_wrecked",
                workout_id=w["id"],
                action="insert_rest",
                reason=f"You reported feeling 'wrecked' or 'sore' on {bad_feeling_count} "
                       f"recent check-ins. Inserting a recovery day to let your body "
                       f"adapt before the next hard effort.",
                signal_values={"bad_feeling_count": bad_feeling_count},
            ))
            break

    return decisions


def _is_hard(payload: dict[str, Any]) -> bool:
    """Check if a workout payload represents a hard session."""
    return payload.get("type", "") in HARD_TYPES
