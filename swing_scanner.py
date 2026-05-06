import datetime as dt
from typing import Dict, Optional, Tuple

from bot_utils import safe_float
from config import (
    MIN_RISK_REWARD,
    SWING_ATR_STOP_MULTIPLIER,
    SWING_ATR_TARGET_MULTIPLIER,
    SWING_HOLD_DAYS_MAX,
    SWING_HOLD_DAYS_MIN,
    SWING_MIN_SCORE,
    SWING_PULLBACK_TOLERANCE_PCT,
)

# NOTE:
# Existing helper implementations remain unchanged above in the actual repo file.
# This patch adds multi-timeframe confirmation support.


def _mtf_trend_score(direction, tech):
    """
    Multi-timeframe swing confirmation:

    Weekly chart -> overall trend
    Daily chart  -> setup structure
    4H chart     -> entry timing
    """
    score, reasons = 0, []

    weekly = str(tech.get("weekly_trend", "")).upper()
    daily = str(tech.get("daily_trend", "")).upper()
    h4 = str(tech.get("h4_trend", tech.get("trend_4h", ""))).upper()

    bullish = {"BULLISH", "UP", "UPTREND"}
    bearish = {"BEARISH", "DOWN", "DOWNTREND"}

    if direction == "CALL":
        if weekly in bullish:
            score += 12
            reasons.append("weekly trend bullish")

        if daily in bullish:
            score += 10
            reasons.append("daily structure bullish")

        if h4 in bullish:
            score += 8
            reasons.append("4H entry trend aligned")

        aligned = sum([
            weekly in bullish,
            daily in bullish,
            h4 in bullish,
        ])

    else:
        if weekly in bearish:
            score += 12
            reasons.append("weekly trend bearish")

        if daily in bearish:
            score += 10
            reasons.append("daily structure bearish")

        if h4 in bearish:
            score += 8
            reasons.append("4H entry trend aligned")

        aligned = sum([
            weekly in bearish,
            daily in bearish,
            h4 in bearish,
        ])

    # Penalize timeframe conflicts.
    if aligned <= 1:
        score -= 12
        reasons.append("multi-timeframe conflict risk")

    return score, reasons


_old_score_direction = _score_direction


def _score_direction(direction, tech, price, atr, closes):
    score, reasons, stop, target, rr = _old_score_direction(
        direction,
        tech,
        price,
        atr,
        closes,
    )

    mtf_score, mtf_reasons = _mtf_trend_score(direction, tech)

    score += mtf_score
    reasons.extend(mtf_reasons)

    return score, reasons, stop, target, rr
