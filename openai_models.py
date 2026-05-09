"""Centralized OpenAI model defaults for market-data reasoning.

The alerting paths use a reasoning-capable model by default because they weigh
multi-factor market context, risk/reward, regime, volume, timing, and option
trade-management tradeoffs before sending or managing alerts.
"""

from __future__ import annotations

from typing import Any

from config import OPENAI_REASONING_EFFORT, OPENAI_REASONING_MODEL


_REASONING_MODEL_PREFIXES = ("gpt-5", "o")


def is_reasoning_model(model: str | None) -> bool:
    """Return True when a model supports explicit reasoning effort."""
    normalized = (model or "").strip().lower()
    return normalized.startswith(_REASONING_MODEL_PREFIXES)


def market_reasoning_model() -> str:
    """Default LLM for alert decisions and market-data analysis."""
    return OPENAI_REASONING_MODEL


def chat_completion_options(
    *,
    model: str | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build Chat Completions options compatible with reasoning models.

    GPT-5/o-series models should be steered with ``reasoning_effort`` rather
    than low temperatures. If the model is overridden to a classic chat model,
    keep any requested temperature behavior.
    """
    selected_model = model or market_reasoning_model()
    options: dict[str, Any] = {"model": selected_model, **kwargs}

    if is_reasoning_model(selected_model):
        effort = (reasoning_effort or OPENAI_REASONING_EFFORT or "").strip()
        if effort:
            options["reasoning_effort"] = effort
    elif temperature is not None:
        options["temperature"] = temperature

    return options
