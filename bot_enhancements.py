from adaptive_scoring import get_weight
from market_regime import regime_adjustment
from bot_utils import pct_diff
from config import *

_ORIGINAL_BUILD_CANDIDATE_ATTR = "_original_build_candidate_before_enhancements"


def _near_pct(price, level, tolerance_pct):
    if price is None or level is None:
        return False
    diff = abs(pct_diff(price, level) or 999)
    return diff <= tolerance_pct


def _compute_fib_levels(direction, tech):
    high = tech.get("recent_high")
    low = tech.get("recent_low")
    if not high or not low:
        return []

    levels = []
    for fib in FIB_LEVELS:
        if direction == "CALL":
            levels.append(high - (high - low) * fib)
        else:
            levels.append(low + (high - low) * fib)
    return levels


def _sr_levels(tech, direction):
    return [
        tech.get("ema21"), tech.get("vwap"),
        tech.get("orb_high") if direction == "CALL" else tech.get("orb_low"),
        tech.get("premarket_high") if direction == "CALL" else tech.get("premarket_low"),
        tech.get("prev_high") if direction == "CALL" else tech.get("prev_low"),
        tech.get("recent_high") if direction == "CALL" else tech.get("recent_low")
    ]


def _fib_confluence(direction, tech):
    if not FIB_FILTER_ENABLED:
        return True

    price = tech.get("price")
    fib_levels = _compute_fib_levels(direction, tech)

    sr_levels = _sr_levels(tech, direction)

    confluence = 0

    for fib in fib_levels:
        if not _near_pct(price, fib, FIB_TOLERANCE_PCT):
            continue

        for sr in sr_levels:
            if _near_pct(fib, sr, FIB_CONFLUENCE_TOLERANCE_PCT):
                confluence += 1

    return confluence >= FIB_MIN_CONFLUENCE_COUNT


def is_strong_pullback(direction, tech, intraday):
    price = tech.get("price")
    ema21 = tech.get("ema21")
    vwap = tech.get("vwap")

    if not price:
        return False, "No price"

    near_zone = False
    if ema21 and _near_pct(price, ema21, PULLBACK_ZONE_TOLERANCE_PCT):
        near_zone = True
    if vwap and _near_pct(price, vwap, PULLBACK_ZONE_TOLERANCE_PCT):
        near_zone = True

    if not near_zone:
        return False, "Not near EMA21/VWAP"

    if not _fib_confluence(direction, tech):
        return False, "No Fib + SR confluence"

    trend5 = tech.get("trend_5m")
    trend15 = tech.get("trend_15m")

    if direction == "CALL" and not (trend5 == "UP" and trend15 == "UP"):
        return False, "Trend not aligned"
    if direction == "PUT" and not (trend5 == "DOWN" and trend15 == "DOWN"):
        return False, "Trend not aligned"

    body = intraday.get("body_pct", 0)
    close_pos = intraday.get("close_position", 0)

    if direction == "CALL" and (body < 0.4 or close_pos < 0.6):
        return False, "Weak reclaim candle"
    if direction == "PUT" and (body < 0.4 or close_pos > 0.4):
        return False, "Weak rejection candle"

    if intraday.get("confirmations", 0) < PULLBACK_MIN_CONFIRMATIONS:
        return False, "Low confirmation"

    return True, "A+ Pullback (Fib + SR confluence)"


def apply_enhancements(bot_cls):
    if hasattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR):
        return bot_cls

    original_build_candidate = bot_cls.build_candidate

    def enhanced_detect_entry_mode(self, setup, tech, intraday_info):
        direction = setup["direction"]

        valid_pullback, reason = is_strong_pullback(direction, tech, intraday_info)
        if valid_pullback:
            return "PULLBACK", reason

        return "STANDARD", "Weak setup"

    async def enhanced_build_candidate(self, ticker):
        candidate = await original_build_candidate(self, ticker)
        if not candidate:
            return None

        setup = candidate["setup"]
        mode = candidate.get("entry_mode")

        if A_PLUS_MODE and mode == "PULLBACK":
            if setup["score"] < A_PLUS_PULLBACK_MIN_SCORE:
                return None

        return candidate

    bot_cls.detect_entry_mode = enhanced_detect_entry_mode
    bot_cls.build_candidate = enhanced_build_candidate
    return bot_cls
