"""Adapter agent — makes minimal patches to an existing plan via Gemini Flash.

Orchestrates:
1. Load context (recent activities, metrics, checkins, upcoming workouts)
2. Run deterministic rules engine
3. Call Gemini Flash with adapter prompt + rules decisions
4. Validate and apply patches
5. Log agent run
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

import httpx
import structlog

from dynamicrunner.adaptation import RuleDecision, RulesContext, run_rules
from dynamicrunner.ai import GeminiResponse, call_gemini, log_agent_run
from dynamicrunner.config import Settings

log = structlog.get_logger(__name__)

ADAPTER_PROMPT_VERSION = "v1"


def _load_upcoming_workouts(
    settings: Settings, user_id: str, days: int = 14
) -> list[dict[str, Any]]:
    """Load upcoming workouts for the next N days."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    start = date.today().isoformat()

    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
        params={
            "user_id": f"eq.{user_id}",
            "scheduled_date": f"gte.{start}",
            "select": "id,scheduled_date,payload",
            "order": "scheduled_date.asc",
        },
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _load_recent_activities(
    settings: Settings, user_id: str, days: int = 7
) -> list[dict[str, Any]]:
    """Load recent activities."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    since = (date.today() - timedelta(days=days)).isoformat()

    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/activities",
        params={
            "user_id": f"eq.{user_id}",
            "activity_date": f"gte.{since}",
            "select": "garmin_activity_id,activity_date,payload",
            "order": "activity_date.desc",
        },
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _load_recent_metrics(
    settings: Settings, user_id: str, days: int = 7
) -> list[dict[str, Any]]:
    """Load recent daily metrics."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    since = (date.today() - timedelta(days=days)).isoformat()

    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/daily_metrics",
        params={
            "user_id": f"eq.{user_id}",
            "metric_date": f"gte.{since}",
            "select": "metric_date,payload",
            "order": "metric_date.desc",
        },
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _load_recent_checkins(
    settings: Settings, user_id: str, days: int = 7
) -> list[dict[str, Any]]:
    """Load recent check-ins."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/checkins",
        params={
            "user_id": f"eq.{user_id}",
            "select": "workout_id,payload,created_at",
            "order": "created_at.desc",
            "limit": "10",
        },
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _compute_baselines(
    settings: Settings, user_id: str
) -> tuple[float | None, float | None]:
    """Compute 28-day HRV and RHR baselines."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    since = (date.today() - timedelta(days=28)).isoformat()

    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/daily_metrics",
        params={
            "user_id": f"eq.{user_id}",
            "metric_date": f"gte.{since}",
            "select": "payload",
        },
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()

    hrvs: list[float] = []
    rhrs: list[float] = []

    for row in rows:
        payload = row.get("payload", {})
        hrv = payload.get("hrv_last_night_avg")
        if hrv and hrv > 0:
            hrvs.append(float(hrv))
        rhr = payload.get("resting_hr")
        if rhr and rhr > 0:
            rhrs.append(float(rhr))

    hrv_baseline = sum(hrvs) / len(hrvs) if hrvs else None
    rhr_baseline = sum(rhrs) / len(rhrs) if rhrs else None

    return hrv_baseline, rhr_baseline


def _build_adapter_prompt(
    rules_decisions: list[RuleDecision],
    upcoming_workouts: list[dict[str, Any]],
    recent_activities: list[dict[str, Any]],
    recent_metrics: list[dict[str, Any]],
    recent_checkins: list[dict[str, Any]],
    hrv_baseline: float | None,
    rhr_baseline: float | None,
) -> str:
    """Build the user prompt for the adapter agent."""
    return json.dumps({
        "today": date.today().isoformat(),
        "rulesEngineDecisions": [asdict(d) for d in rules_decisions],
        "upcoming_workouts": [
            {
                "id": w["id"],
                "scheduledDate": w.get("payload", {}).get("scheduledDate", w.get("scheduled_date")),
                "type": w.get("payload", {}).get("type"),
                "title": w.get("payload", {}).get("title"),
                "status": w.get("payload", {}).get("status", "planned"),
            }
            for w in upcoming_workouts[:14]
        ],
        "recent_activities": [
            {
                "date": a.get("activity_date"),
                "type": (a.get("payload") or {}).get("activityType", {}).get("typeKey"),
                "distance_m": (a.get("payload") or {}).get("distance"),
                "duration_s": (a.get("payload") or {}).get("duration"),
                "avg_hr": (a.get("payload") or {}).get("averageHR"),
            }
            for a in recent_activities[:10]
        ],
        "recent_metrics": [
            {
                "date": m.get("metric_date"),
                "resting_hr": (m.get("payload") or {}).get("resting_hr"),
                "hrv": (m.get("payload") or {}).get("hrv_last_night_avg"),
                "sleep_hours": round((m.get("payload") or {}).get("sleeping_seconds", 0) / 3600, 1)
                if (m.get("payload") or {}).get("sleeping_seconds")
                else None,
                "body_battery": (m.get("payload") or {}).get("body_battery_high"),
                "stress": (m.get("payload") or {}).get("average_stress"),
            }
            for m in recent_metrics[:7]
        ],
        "recent_checkins": [
            {
                "feeling": (c.get("payload") or {}).get("feeling"),
                "rpe": (c.get("payload") or {}).get("rpe"),
            }
            for c in recent_checkins[:5]
        ],
        "baselines": {
            "hrv_28d_avg": round(hrv_baseline, 1) if hrv_baseline else None,
            "rhr_28d_avg": round(rhr_baseline, 1) if rhr_baseline else None,
        },
    }, indent=2)


def _apply_patches(
    settings: Settings, user_id: str, patches: list[dict[str, Any]]
) -> int:
    """Apply adapter patches to workouts. Returns count applied."""
    if not patches:
        return 0

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    applied = 0
    for patch in patches:
        op = patch.get("op")
        workout_id = patch.get("workoutId")
        if not workout_id:
            continue

        # Fetch current workout
        resp = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
            params={
                "id": f"eq.{workout_id}",
                "user_id": f"eq.{user_id}",
                "select": "id,payload,scheduled_date",
            },
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            continue

        row = rows[0]
        payload = row.get("payload", {})
        update: dict[str, Any] = {}

        if op == "move":
            new_date = patch.get("newDate")
            if new_date:
                payload["scheduledDate"] = new_date
                payload["movedReason"] = "missed"
                payload["agentReason"] = patch.get("reason", "")
                update["scheduled_date"] = new_date
                update["payload"] = payload

        elif op == "modify":
            if patch.get("newStructure"):
                payload["structure"] = patch["newStructure"]
            if patch.get("newTitle"):
                payload["title"] = patch["newTitle"]
            if patch.get("newEstimatedDurationSec"):
                payload["estimatedDurationSec"] = patch["newEstimatedDurationSec"]
            payload["agentReason"] = patch.get("reason", "")
            update["payload"] = payload

        elif op == "replace":
            if patch.get("newType"):
                payload["type"] = patch["newType"]
            if patch.get("newStructure"):
                payload["structure"] = patch["newStructure"]
            if patch.get("newTitle"):
                payload["title"] = patch["newTitle"]
            payload["agentReason"] = patch.get("reason", "")
            update["payload"] = payload

        elif op == "insert_rest":
            payload["type"] = "rest"
            payload["title"] = "Recovery day (auto-adjusted)"
            payload["estimatedDurationSec"] = 0
            payload["structure"] = {"mainSteps": []}
            payload["agentReason"] = patch.get("reason", "")
            update["payload"] = payload

        elif op == "skip":
            payload["status"] = "skipped"
            payload["agentReason"] = patch.get("reason", "")
            update["payload"] = payload

        if update:
            resp = httpx.patch(
                f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
                params={"id": f"eq.{workout_id}", "user_id": f"eq.{user_id}"},
                headers=headers,
                json=update,
                timeout=10,
            )
            resp.raise_for_status()
            applied += 1

    return applied


def run_adaptation(settings: Settings, user_id: str) -> dict[str, Any]:
    """Run the full adaptation pipeline for a user.

    1. Load context
    2. Run deterministic rules
    3. Call Gemini Flash adapter (if needed)
    4. Apply patches
    5. Log agent run

    Returns summary of what was done.
    """
    log.info("adapter.start", user_id=user_id)

    # 1. Load context
    upcoming = _load_upcoming_workouts(settings, user_id)
    activities = _load_recent_activities(settings, user_id)
    metrics = _load_recent_metrics(settings, user_id)
    checkins = _load_recent_checkins(settings, user_id)
    hrv_baseline, rhr_baseline = _compute_baselines(settings, user_id)

    # 2. Run deterministic rules
    context = RulesContext(
        user_id=user_id,
        today=date.today(),
        upcoming_workouts=upcoming,
        recent_activities=activities,
        daily_metrics=metrics,
        checkins=checkins,
        hrv_baseline=hrv_baseline,
        rhr_baseline=rhr_baseline,
    )
    rules_decisions = run_rules(context)

    log.info("adapter.rules_done", user_id=user_id, decisions=len(rules_decisions))

    # Apply rules decisions directly as patches
    rules_patches = _rules_to_patches(rules_decisions)
    rules_applied = _apply_patches(settings, user_id, rules_patches)

    # 3. Call Gemini adapter (only if we have data and an API key)
    adapter_patches: list[dict[str, Any]] = []
    gemini_resp: GeminiResponse | None = None
    summary = ""

    if settings.gemini_api_key and (activities or metrics):
        from pathlib import Path
        prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "adapter.system.v1.md"
        system_prompt = prompt_path.read_text() if prompt_path.exists() else ""

        user_prompt = _build_adapter_prompt(
            rules_decisions, upcoming, activities, metrics, checkins,
            hrv_baseline, rhr_baseline,
        )

        gemini_resp = call_gemini(
            settings,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=4000,
        )

        if gemini_resp.success and gemini_resp.content:
            content = gemini_resp.content
            no_change = content.get("noChangeNeeded", False)
            summary = content.get("summary", "")

            if not no_change:
                adapter_patches = content.get("patches", [])
                _apply_patches(settings, user_id, adapter_patches)

        log_agent_run(
            settings,
            user_id=user_id,
            agent_type="adapter",
            prompt_version=ADAPTER_PROMPT_VERSION,
            response=gemini_resp,
        )
    else:
        if rules_decisions:
            summary = f"Applied {len(rules_decisions)} automatic adjustment(s) based on your recent data."
        else:
            summary = "No changes needed — your training load and recovery signals look on track."

    # 4. Store adaptation summary in agent_runs for the feed
    if summary and not gemini_resp:
        _log_rules_only_run(settings, user_id, rules_decisions, summary)

    result = {
        "user_id": user_id,
        "rules_decisions": len(rules_decisions),
        "rules_applied": rules_applied,
        "adapter_patches": len(adapter_patches),
        "summary": summary,
    }

    log.info("adapter.complete", **result)
    return result


def _rules_to_patches(decisions: list[RuleDecision]) -> list[dict[str, Any]]:
    """Convert RuleDecisions to adapter-output-compatible patches."""
    patches: list[dict[str, Any]] = []
    for d in decisions:
        patch: dict[str, Any] = {
            "op": _action_to_op(d.action),
            "workoutId": d.workout_id,
            "reason": d.reason,
        }
        if d.new_date:
            patch["newDate"] = d.new_date
        if d.new_type:
            patch["newType"] = d.new_type
        patches.append(patch)
    return patches


def _action_to_op(action: str) -> str:
    """Map rule action to adapter op."""
    mapping = {
        "move": "move",
        "modify": "modify",
        "downgrade": "replace",
        "insert_rest": "insert_rest",
        "skip": "skip",
    }
    return mapping.get(action, "modify")


def _log_rules_only_run(
    settings: Settings,
    user_id: str,
    decisions: list[RuleDecision],
    summary: str,
) -> None:
    """Log a rules-only adaptation run (no Gemini call)."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    httpx.post(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/agent_runs",
        headers=headers,
        json={
            "user_id": user_id,
            "payload": {
                "agent_type": "adapter_rules_only",
                "decisions": len(decisions),
                "summary": summary,
                "rules": [d.rule for d in decisions],
            },
        },
        timeout=10,
    )
