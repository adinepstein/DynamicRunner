"""Planner agent — generates a complete training plan via Gemini.

Orchestrates:
1. Load athlete state (features + profile)
2. Load prompt template
3. Call Gemini with structured output
4. Validate against guardrails
5. Persist plan + workouts atomically
6. Log agent run
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import structlog

from dynamicrunner.ai import GeminiResponse, call_gemini, log_agent_run
from dynamicrunner.config import Settings
from dynamicrunner.features import extract_features, features_to_prompt_context

log = structlog.get_logger(__name__)

PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompts"
PROMPT_VERSION = "v1"


@dataclass
class PlanResult:
    """Result of a plan generation attempt."""

    success: bool
    plan_id: str | None = None
    error: str | None = None
    guardrail_failures: list[str] | None = None
    gemini_response: GeminiResponse | None = None


def _load_prompt(filename: str) -> str:
    path = PROMPT_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text()


def _build_user_prompt(
    athlete_profile: dict[str, Any],
    features_context: dict[str, Any],
    race_goal: dict[str, Any],
) -> str:
    """Build the user message for the planner with all athlete context."""
    return json.dumps(
        {
            "today": date.today().isoformat(),
            "athlete_profile": athlete_profile,
            "training_features": features_context,
            "race_goal": race_goal,
        },
        indent=2,
    )


def _get_athlete_profile(settings: Settings, user_id: str) -> dict[str, Any]:
    """Fetch athlete profile from Supabase."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    resp = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/profiles",
        params={
            "user_id": f"eq.{user_id}",
            "select": "athlete_profile,timezone,units",
        },
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return {}
    return rows[0].get("athlete_profile") or {}


def _get_race_goal(athlete_profile: dict[str, Any]) -> dict[str, Any]:
    """Extract race goal from athlete profile."""
    return athlete_profile.get("raceGoal", {})


def _validate_guardrails(plan_output: dict[str, Any]) -> list[str]:
    """Validate the plan output against guardrails. Returns list of failures."""
    failures: list[str] = []

    critique = plan_output.get("selfCritique", {})

    if not critique.get("weeklyVolumeIncreaseOk"):
        failures.append("weeklyVolumeIncreaseOk: weekly volume increase exceeds 10%")

    if not critique.get("tapersCorrectly"):
        failures.append("tapersCorrectly: taper does not follow correct volume reduction")

    if not critique.get("noBackToBackHard"):
        failures.append("noBackToBackHard: consecutive hard days detected")

    if not critique.get("longRunCapOk"):
        failures.append("longRunCapOk: long run exceeds 35% of weekly volume")

    # Structural checks
    workouts = plan_output.get("workouts", [])
    if not workouts:
        failures.append("No workouts in plan output")

    plan = plan_output.get("plan", {})
    if not plan.get("methodology"):
        failures.append("Missing methodology")
    if not plan.get("raceDate"):
        failures.append("Missing raceDate")
    if not plan.get("weeklyStructure"):
        failures.append("Missing weeklyStructure")

    return failures


def _persist_plan(
    settings: Settings, user_id: str, plan_output: dict[str, Any]
) -> str:
    """Atomically persist plan + workouts to Supabase. Returns plan_id."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    # Archive any existing active plan
    httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/plans",
        params={"user_id": f"eq.{user_id}", "status": "eq.active"},
        headers={**headers, "Prefer": "return=minimal"},
        json={"status": "abandoned"},
        timeout=10,
    )

    # Insert new plan
    plan_data = plan_output.get("plan", {})
    plan_payload = {
        "user_id": user_id,
        "status": "active",
        "payload": plan_data,
    }

    resp = httpx.post(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/plans",
        headers=headers,
        json=plan_payload,
        timeout=10,
    )
    resp.raise_for_status()
    plan_row = resp.json()
    plan_id = plan_row[0]["id"] if isinstance(plan_row, list) else plan_row["id"]

    # Insert workouts in batches
    workouts = plan_output.get("workouts", [])
    workout_rows = []
    for w in workouts:
        workout_rows.append({
            "user_id": user_id,
            "plan_id": plan_id,
            "scheduled_date": w["scheduledDate"],
            "payload": w,
        })

    chunk_size = 50
    batch_headers = {**headers, "Prefer": "return=minimal"}
    for i in range(0, len(workout_rows), chunk_size):
        chunk = workout_rows[i : i + chunk_size]
        resp = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/workouts",
            headers=batch_headers,
            json=chunk,
            timeout=30,
        )
        resp.raise_for_status()

    log.info("planner.persisted", user_id=user_id, plan_id=plan_id, workouts=len(workout_rows))

    # Mark onboarding as completed
    httpx.patch(
        f"{settings.supabase_url.rstrip('/')}/rest/v1/profiles",
        params={"user_id": f"eq.{user_id}"},
        headers={**headers, "Prefer": "return=minimal"},
        json={"onboarding_completed": True},
        timeout=10,
    )

    return plan_id


def generate_plan(settings: Settings, user_id: str) -> PlanResult:
    """Generate a complete training plan for a user.

    This is the main entry point for plan generation. It:
    1. Loads athlete data and training features
    2. Calls Gemini with the planner prompt
    3. Validates guardrails
    4. Persists the plan (with one retry on guardrail failure)
    5. Logs the agent run

    Returns a PlanResult with success/failure info.
    """
    log.info("planner.start", user_id=user_id)

    # 1. Load athlete state
    try:
        athlete_profile = _get_athlete_profile(settings, user_id)
        race_goal = _get_race_goal(athlete_profile)

        if not race_goal or not race_goal.get("date"):
            return PlanResult(
                success=False,
                error="No race goal configured. Complete onboarding first.",
            )

        features = extract_features(settings, user_id, days=90)
        features_context = features_to_prompt_context(features)
    except Exception as exc:
        log.error("planner.data_load_failed", user_id=user_id, error=str(exc))
        return PlanResult(success=False, error=f"Failed to load athlete data: {exc}")

    # 2. Load prompts
    try:
        system_prompt = _load_prompt("planner.system.v1.md")
        fewshots = _load_prompt("planner.fewshots.v1.md")
    except FileNotFoundError as exc:
        return PlanResult(success=False, error=str(exc))

    user_prompt = _build_user_prompt(athlete_profile, features_context, race_goal)
    full_user_prompt = f"{fewshots}\n\n---\n\nNow generate a plan for this athlete:\n\n{user_prompt}"

    # 3. Call Gemini (with one retry on failure)
    gemini_resp: GeminiResponse | None = None
    for attempt in range(2):
        gemini_resp = call_gemini(
            settings,
            system_prompt=system_prompt,
            user_prompt=full_user_prompt,
        )

        if not gemini_resp.success or gemini_resp.content is None:
            log.warning(
                "planner.gemini_failed",
                attempt=attempt + 1,
                error=gemini_resp.error,
            )
            if attempt == 0:
                continue
            log_agent_run(
                settings,
                user_id=user_id,
                agent_type="planner",
                prompt_version=PROMPT_VERSION,
                response=gemini_resp,
            )
            return PlanResult(
                success=False,
                error=gemini_resp.error or "Gemini returned invalid response",
                gemini_response=gemini_resp,
            )

        # 4. Validate guardrails
        failures = _validate_guardrails(gemini_resp.content)
        if failures:
            log.warning(
                "planner.guardrail_failures",
                attempt=attempt + 1,
                failures=failures,
            )
            if attempt == 0:
                full_user_prompt += (
                    f"\n\n[RETRY] Your previous attempt failed guardrails: {failures}. "
                    "Please fix these issues and regenerate."
                )
                continue
            log_agent_run(
                settings,
                user_id=user_id,
                agent_type="planner",
                prompt_version=PROMPT_VERSION,
                response=gemini_resp,
            )
            return PlanResult(
                success=False,
                error="Plan failed guardrails after retry",
                guardrail_failures=failures,
                gemini_response=gemini_resp,
            )

        break

    assert gemini_resp is not None and gemini_resp.content is not None

    # 5. Persist plan
    try:
        plan_id = _persist_plan(settings, user_id, gemini_resp.content)
    except Exception as exc:
        log.error("planner.persist_failed", user_id=user_id, error=str(exc))
        log_agent_run(
            settings,
            user_id=user_id,
            agent_type="planner",
            prompt_version=PROMPT_VERSION,
            response=gemini_resp,
        )
        return PlanResult(
            success=False,
            error=f"Failed to persist plan: {exc}",
            gemini_response=gemini_resp,
        )

    # 6. Log agent run
    log_agent_run(
        settings,
        user_id=user_id,
        agent_type="planner",
        prompt_version=PROMPT_VERSION,
        response=gemini_resp,
        plan_id=plan_id,
    )

    log.info(
        "planner.complete",
        user_id=user_id,
        plan_id=plan_id,
        cost_usd=gemini_resp.cost_usd,
    )

    return PlanResult(
        success=True,
        plan_id=plan_id,
        gemini_response=gemini_resp,
    )
