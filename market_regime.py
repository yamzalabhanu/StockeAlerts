from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class RegimeAdjustment:
    regime: str
    score_adjustment: int
    min_score_adjustment: int
    reason: str


def classify_market_regime(market: Dict) -> str:
    """Classify market as TREND, MIXED, or CHOP from ETF bias counts.

    Expected market shape:
    {
        "bias": "BULLISH" | "BEARISH" | "NEUTRAL",
        "bullish_count": int,
        "bearish_count": int,
        "details": [...]
    }
    """
    bullish = int(market.get("bullish_count", 0) or 0)
    bearish = int(market.get("bearish_count", 0) or 0)
    bias = market.get("bias", "NEUTRAL")
    spread = abs(bullish - bearish)

    if bias in {"BULLISH", "BEARISH"} and spread >= 2:
        return "TREND"
    if bias == "NEUTRAL" or spread == 0:
        return "CHOP"
    return "MIXED"


def regime_adjustment(entry_mode: str, market: Dict) -> RegimeAdjustment:
    """Return scoring/threshold adjustments by market regime and entry mode."""
    regime = classify_market_regime(market)
    entry_mode = (entry_mode or "STANDARD").upper()

    if regime == "TREND":
        if entry_mode in {"BREAKOUT", "MOMENTUM"}:
            return RegimeAdjustment(regime, 12, -5, "Trend day: favor breakout/momentum setups")
        if entry_mode == "RETEST":
            return RegimeAdjustment(regime, 8, -3, "Trend day: retests remain high quality")
        return RegimeAdjustment(regime, 5, 0, "Trend day: modest setup boost")

    if regime == "CHOP":
        if entry_mode in {"BREAKOUT", "MOMENTUM"}:
            return RegimeAdjustment(regime, -15, 8, "Chop day: penalize breakout/momentum chasing")
        if entry_mode in {"RETEST", "PULLBACK"}:
            return RegimeAdjustment(regime, 5, 0, "Chop day: prefer retest/pullback entries")
        return RegimeAdjustment(regime, -8, 5, "Chop day: stricter filtering")

    # MIXED
    if entry_mode == "RETEST":
        return RegimeAdjustment(regime, 6, 0, "Mixed market: retest entries preferred")
    if entry_mode == "MOMENTUM":
        return RegimeAdjustment(regime, -4, 3, "Mixed market: momentum needs extra confirmation")
    return RegimeAdjustment(regime, 0, 0, "Mixed market: no major adjustment")
