from __future__ import annotations

import datetime as dt
from typing import Any, Dict

from bot_utils import safe_float

OPEN_DRIVE = "OPEN_DRIVE"
TREND_DAY = "TREND_DAY"
PULLBACK = "PULLBACK"
BREAKOUT_BUILDING = "BREAKOUT_BUILDING"
RANGE = "RANGE"
REVERSAL_ATTEMPT = "REVERSAL_ATTEMPT"
SHORT_COVERING = "SHORT_COVERING"
LIQUIDITY_TRAP = "LIQUIDITY_TRAP"
FAKE_BREAKOUT = "FAKE_BREAKOUT"
EXHAUSTION = "EXHAUSTION"

# Normalized phase labels used by the scoring router.  The legacy phase names
# remain unchanged for existing tests/alerts, while these labels make the
# higher-level routing explicit.
TRENDING_UP = "TRENDING_UP"
TRENDING_DOWN = "TRENDING_DOWN"
CHOP = "CHOP"
REVERSAL = "REVERSAL"


PHASES = {
    OPEN_DRIVE,
    TREND_DAY,
    PULLBACK,
    BREAKOUT_BUILDING,
    RANGE,
    REVERSAL_ATTEMPT,
    SHORT_COVERING,
    LIQUIDITY_TRAP,
    FAKE_BREAKOUT,
    EXHAUSTION,
}


def _session_minutes(tech: Dict[str, Any]) -> float | None:
    if tech.get("session_minutes") is not None:
        return safe_float(tech.get("session_minutes"))
    value = tech.get("market_time") or tech.get("latest_price_time")
    if not value:
        return None
    try:
        hour, minute = [int(part) for part in str(value)[:5].split(":")]
        return (hour * 60 + minute) - (9 * 60 + 30)
    except Exception:
        return None


def detect_market_phase(tech: Dict[str, Any] | None, setup: Dict[str, Any] | None = None, market: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Classify the intraday tape phase using structure-first features.

    This complements broad market regime.  It intentionally consumes generic
    keys so tests/replay rows, live technical context, and Vision AI readings can
    all feed it without needing a new data provider.
    """
    tech = tech or {}
    setup = setup or {}
    market = market or {}
    direction = str(setup.get("direction") or tech.get("direction") or "").upper()
    entry_mode = str(setup.get("entry_mode") or "").upper()
    reasons: list[str] = []
    warnings: list[str] = []

    minutes = _session_minutes(tech)
    rel_volume = safe_float(tech.get("rel_volume"), safe_float(tech.get("rel_volume_5m"), 0)) or 0
    adx = safe_float(tech.get("adx"), safe_float((market.get("stats") or {}).get("adx"), 0)) or 0
    atr_extension = safe_float(tech.get("breakout_distance_atr"), safe_float(tech.get("atr_extension"), 0)) or 0
    distance_vwap = safe_float(tech.get("distance_from_vwap"), 0) or 0
    candle_body = safe_float(tech.get("candle_body_pct"), 0) or 0
    wick_ratio = safe_float(tech.get("wick_ratio"), 0) or 0
    consolidation = safe_float(tech.get("consolidation_tightness"), 1) or 1
    trend_5m = str(tech.get("trend_5m") or "").upper()
    trend_15m = str(tech.get("trend_15m") or "").upper()
    trend_bias = str(market.get("bias") or market.get("market_bias") or tech.get("market_bias") or "").upper()

    if setup.get("liquidity_sweep") or tech.get("liquidity_sweep"):
        if setup.get("retest_confirmed") or tech.get("reclaim_confirmed"):
            phase = LIQUIDITY_TRAP
            reasons.append("Liquidity sweep reclaimed/rejected around a key level")
        else:
            phase = FAKE_BREAKOUT
            warnings.append("Liquidity sweep has not reclaimed/rejected cleanly yet")
    elif setup.get("failed_breakout") or tech.get("failed_breakout"):
        phase = FAKE_BREAKOUT
        warnings.append("Failed breakout/breakdown behavior detected")
    elif atr_extension >= 1.8 or (wick_ratio >= 2.0 and rel_volume >= 1.8):
        phase = EXHAUSTION
        warnings.append("Move is extended or showing exhaustion wicks")
    elif minutes is not None and 0 <= minutes <= 20 and rel_volume >= 1.5 and abs(distance_vwap) >= 0.3:
        phase = OPEN_DRIVE
        reasons.append("Opening drive conditions in first 20 minutes")
    elif adx >= 25 or (trend_5m and trend_5m == trend_15m and trend_5m in {"BULLISH", "BEARISH", "UP", "DOWN"}):
        phase = TREND_DAY
        reasons.append("Multi-timeframe trend or ADX supports trend day behavior")
    elif entry_mode in {"RETEST", "PULLBACK"} or setup.get("retest_confirmed"):
        phase = PULLBACK
        reasons.append("Pullback/retest structure is active")
    elif consolidation <= 0.45 and rel_volume >= 1.1:
        phase = BREAKOUT_BUILDING
        reasons.append("Compression with volume suggests breakout is building")
    elif wick_ratio >= 1.5 and candle_body < 35:
        phase = REVERSAL_ATTEMPT
        warnings.append("Wicky candle with small body suggests reversal attempt")
    elif direction == "PUT" and rel_volume >= 2.0 and candle_body >= 60:
        phase = SHORT_COVERING
        reasons.append("High-speed downside/upside squeeze behavior may be short covering")
    else:
        phase = RANGE
        warnings.append("No clean directional phase; assume range until proven otherwise")

    confidence = 55 + min(25, int(rel_volume * 5))
    if phase in {OPEN_DRIVE, TREND_DAY, LIQUIDITY_TRAP}:
        confidence += 10
    if phase in {RANGE, REVERSAL_ATTEMPT}:
        confidence -= 5

    normalized_phase = _normalized_phase(phase, direction, trend_5m, trend_15m, trend_bias)
    routing = phase_routing(normalized_phase, entry_mode)

    return {
        "phase": phase,
        "normalized_phase": normalized_phase,
        "routing": routing,
        "confidence": max(0, min(100, confidence)),
        "reasons": reasons,
        "warnings": warnings,
        "session_minutes": minutes,
    }


def phase_score_adjustment(phase: str, entry_mode: str | None = None) -> int:
    entry_mode = str(entry_mode or "").upper()
    if phase in {TREND_DAY, OPEN_DRIVE}:
        return 10 if entry_mode in {"BREAKOUT", "MOMENTUM", "RETEST"} else 5
    if phase == BREAKOUT_BUILDING:
        return 8
    if phase in {PULLBACK, LIQUIDITY_TRAP}:
        return 10 if entry_mode in {"RETEST", "PULLBACK"} else 4
    if phase == RANGE:
        return -8 if entry_mode in {"BREAKOUT", "MOMENTUM"} else -3
    if phase in {FAKE_BREAKOUT, EXHAUSTION}:
        return -22
    if phase == REVERSAL_ATTEMPT:
        return -10
    return 0


def _normalized_phase(phase: str, direction: str = "", trend_5m: str = "", trend_15m: str = "", trend_bias: str = "") -> str:
    if phase in {OPEN_DRIVE, TREND_DAY, BREAKOUT_BUILDING, PULLBACK}:
        combined = " ".join([direction, trend_5m, trend_15m, trend_bias])
        if any(token in combined for token in ["BEAR", "DOWN", "PUT"]):
            return TRENDING_DOWN
        return TRENDING_UP
    if phase in {RANGE}:
        return CHOP
    if phase in {REVERSAL_ATTEMPT, SHORT_COVERING}:
        return REVERSAL
    if phase in {FAKE_BREAKOUT, EXHAUSTION}:
        return FAKE_BREAKOUT if phase == FAKE_BREAKOUT else EXHAUSTION
    return phase


def phase_routing(normalized_phase: str, entry_mode: str | None = None) -> Dict[str, Any]:
    entry_mode = str(entry_mode or "").upper()
    if normalized_phase in {TRENDING_UP, TRENDING_DOWN}:
        preferred = ["BREAKOUT", "MOMENTUM", "RETEST", "PULLBACK", "ORB_RETEST"]
        threshold_adjustment = -6
        requirements = ["avoid extended candles", "prefer retest or EMA/VWAP hold"]
    elif normalized_phase == CHOP:
        preferred = ["VWAP_RECLAIM", "FADE", "LIQUIDITY_TRAP", "RETEST"]
        threshold_adjustment = 8
        requirements = ["demand reclaim confirmation", "avoid raw breakout chase"]
    elif normalized_phase == REVERSAL:
        preferred = ["VWAP_RECLAIM", "REVERSAL", "LIQUIDITY_TRAP"]
        threshold_adjustment = 4
        requirements = ["require volume expansion", "require reclaim/rejection confirmation"]
    elif normalized_phase in {FAKE_BREAKOUT, EXHAUSTION}:
        preferred = ["WAIT", "FADE_AFTER_CONFIRMATION"]
        threshold_adjustment = 12
        requirements = ["wait for reset/retest", "avoid first signal after trap"]
    else:
        preferred = ["RETEST", "PULLBACK"]
        threshold_adjustment = 0
        requirements = ["wait for clearer phase confirmation"]

    return {
        "preferred_setups": preferred,
        "avoid": ["BREAKOUT_CHASE"] if normalized_phase in {CHOP, FAKE_BREAKOUT, EXHAUSTION} else [],
        "requirements": requirements,
        "entry_mode_aligned": entry_mode in preferred if entry_mode else None,
        "threshold_adjustment": threshold_adjustment,
    }
