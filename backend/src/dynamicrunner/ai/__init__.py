"""Gemini AI client wrapper with cost guardrails and structured output.

Wraps google-genai to provide:
- Structured JSON output enforcement via response_schema
- Token usage tracking and cost logging
- Per-call hard token limits
- agent_runs audit logging to Supabase
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from google import genai
from google.genai import types

from dynamicrunner.config import Settings

log = structlog.get_logger(__name__)

# Approximate pricing per 1M tokens (Gemini 2.5 Pro as of 2026)
INPUT_COST_PER_M = 1.25
OUTPUT_COST_PER_M = 10.00
# Hard limits
MAX_INPUT_TOKENS = 100_000
MAX_OUTPUT_TOKENS = 32_000


@dataclass
class GeminiResponse:
    """Structured response from a Gemini call."""

    content: dict[str, Any] | None
    raw_text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    model: str
    success: bool
    error: str | None = None


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * INPUT_COST_PER_M) + (
        output_tokens / 1_000_000 * OUTPUT_COST_PER_M
    )


def call_gemini(
    settings: Settings,
    *,
    system_prompt: str,
    user_prompt: str,
    response_schema: dict[str, Any] | None = None,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
) -> GeminiResponse:
    """Make a structured call to Gemini with cost tracking.

    Args:
        settings: App settings with GEMINI_API_KEY.
        system_prompt: System instruction for the model.
        user_prompt: The user message content.
        response_schema: Optional JSON Schema to enforce structured output.
        max_output_tokens: Hard cap on output tokens.

    Returns:
        GeminiResponse with parsed content, token usage, and cost.
    """
    if not settings.gemini_api_key:
        return GeminiResponse(
            content=None,
            raw_text="",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_usd=0,
            latency_ms=0,
            model=settings.gemini_model,
            success=False,
            error="GEMINI_API_KEY not configured",
        )

    client = genai.Client(api_key=settings.gemini_api_key)

    config_kwargs: dict[str, Any] = {
        "max_output_tokens": max_output_tokens,
        "temperature": 0.4,
    }

    if response_schema:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_schema

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        **config_kwargs,
    )

    start = time.monotonic()

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=user_prompt,
            config=config,
        )
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        log.error("gemini.call_failed", error=str(exc), latency_ms=latency)
        return GeminiResponse(
            content=None,
            raw_text="",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            cost_usd=0,
            latency_ms=latency,
            model=settings.gemini_model,
            success=False,
            error=str(exc),
        )

    latency = int((time.monotonic() - start) * 1000)

    # Extract token counts from usage metadata
    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count if usage else 0
    output_tokens = usage.candidates_token_count if usage else 0
    total_tokens = usage.total_token_count if usage else 0
    cost = _estimate_cost(input_tokens, output_tokens)

    raw_text = response.text or ""

    # Try to parse as JSON
    parsed: dict[str, Any] | None = None
    try:
        parsed = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        pass

    log.info(
        "gemini.call_complete",
        model=settings.gemini_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost, 4),
        latency_ms=latency,
        parsed_ok=parsed is not None,
    )

    return GeminiResponse(
        content=parsed,
        raw_text=raw_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_usd=cost,
        latency_ms=latency,
        model=settings.gemini_model,
        success=parsed is not None,
    )


def log_agent_run(
    settings: Settings,
    *,
    user_id: str,
    agent_type: str,
    prompt_version: str,
    response: GeminiResponse,
    plan_id: str | None = None,
) -> None:
    """Persist an agent run record to Supabase for audit/cost tracking."""
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    payload = {
        "user_id": user_id,
        "payload": {
            "agent_type": agent_type,
            "prompt_version": prompt_version,
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cost_usd": response.cost_usd,
            "latency_ms": response.latency_ms,
            "success": response.success,
            "error": response.error,
            "plan_id": plan_id,
        },
    }

    try:
        resp = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/agent_runs",
            headers=headers,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("gemini.audit_log_failed", error=str(exc), user_id=user_id)
