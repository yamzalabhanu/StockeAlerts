"""Centralized OpenAI model defaults for market-data reasoning.

The alerting paths use a two-tier model strategy so broad ticker scans stay on
an efficient reasoning model while only the highest-confidence setups receive
premium-model review.
"""

from __future__ import annotations

from typing import Any, Mapping

from config import (
    OPENAI_HIGH_QUALITY_MIN_SCORE,
    OPENAI_HIGH_QUALITY_MODEL,
    OPENAI_REASONING_EFFORT,
    OPENAI_REASONING_MODEL,
    OPENAI_SCAN_MODEL,
)


_REASONING_MODEL_PREFIXES = ("gpt-5", "o")
_HIGH_QUALITY_TIERS = {"A+"}


def is_reasoning_model(model: str | None) -> bool:
    """Return True when a model supports explicit reasoning effort."""
    normalized = (model or "").strip().lower()
    return normalized.startswith(_REASONING_MODEL_PREFIXES)


def _safe_score(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _setup_value(setup: Mapping[str, Any] | None, *keys: str) -> Any:
    if not setup:
        return None
    for key in keys:
        value = setup.get(key)
        if value not in (None, ""):
            return value
    return None


def is_high_quality_setup(
    setup: Mapping[str, Any] | None = None,
    *,
    score: float | int | str | None = None,
    tier: str | None = None,
) -> bool:
    """Return True when a setup qualifies for premium GPT-5.5 review.

    A setup is promoted only when its numeric score is at least the configured
    high-quality threshold (95 by default) or its tier/decision is explicitly
    A+. Everything else stays on the scan model for broad all-ticker coverage.
    """
    numeric_score = _safe_score(score)
    if numeric_score is None:
        numeric_score = _safe_score(
            _setup_value(setup, "final_score", "score", "ml_score", "recommendation_score")
        )

    if numeric_score is not None and numeric_score >= OPENAI_HIGH_QUALITY_MIN_SCORE:
        return True

    selected_tier = tier or _setup_value(setup, "tier", "decision", "setup_quality", "grade")
    if isinstance(selected_tier, str) and selected_tier.strip().upper() in _HIGH_QUALITY_TIERS:
        return True

    return False


def market_reasoning_model(
    setup: Mapping[str, Any] | None = None,
    *,
    score: float | int | str | None = None,
    tier: str | None = None,
) -> str:
    """Choose the LLM for market-data analysis.

    Broad all-ticker scans use GPT-5.3. Only score >=95 or A+ setups are routed
    to GPT-5.5 for premium confirmation. ``OPENAI_REASONING_MODEL`` remains a
    backward-compatible override if operators still set it explicitly.
    """
    if is_high_quality_setup(setup, score=score, tier=tier):
        return OPENAI_HIGH_QUALITY_MODEL
    return OPENAI_REASONING_MODEL or OPENAI_SCAN_MODEL


def chat_completion_options(
    *,
    model: str | None = None,
    setup: Mapping[str, Any] | None = None,
    score: float | int | str | None = None,
    tier: str | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build Chat Completions options compatible with reasoning models.

    GPT-5/o-series models should be steered with ``reasoning_effort`` rather
    than low temperatures. If the model is overridden to a classic chat model,
    keep any requested temperature behavior.
    """
    selected_model = model or market_reasoning_model(setup, score=score, tier=tier)
    options: dict[str, Any] = {"model": selected_model, **kwargs}

    if is_reasoning_model(selected_model):
        effort = (reasoning_effort or OPENAI_REASONING_EFFORT or "").strip()
        if effort:
            options["reasoning_effort"] = effort
    elif temperature is not None:
        options["temperature"] = temperature

    return options
