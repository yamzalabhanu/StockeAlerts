from adaptive_scoring import get_weight, update_weights, load_weights, save_weights
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
            level = high - (high - low) * fib
        else:
            level = low + (high - low) * fib
        levels.append(level)

    return levels


def _is_near_fib(direction, tech):
    if not FIB_FILTER_ENABLED:
        return True

    price = tech.get("price")
    fib_levels = _compute_fib_levels(direction, tech)

    for level in fib_levels:
        if _near_pct(price, level, FIB_TOLERANCE_PCT):
            return True

    return False


def is_strong_pullback(direction, tech, intraday):
    price = tech.get("price")
    ema21 = tech.get("ema21")
    vwap = tech.get("vwap")

    if not price:
        return False, "No price"

    # EMA/VWAP zone
    near_zone = False
    if ema21 and _near_pct(price, ema21, PULLBACK_ZONE_TOLERANCE_PCT):
        near_zone = True
    if vwap and _near_pct(price, vwap, PULLBACK_ZONE_TOLERANCE_PCT):
        near_zone = True

    if not near_zone:
        return False, "Not near EMA21/VWAP"

    # Fibonacci confirmation
    if not _is_near_fib(direction, tech):
        return False, "Not near Fibonacci level"

    # Trend alignment
    trend5 = tech.get("trend_5m")
    trend15 = tech.get("trend_15m")

    if direction == "CALL" and not (trend5 == "UP" and trend15 == "UP"):
        return False, "Trend not aligned"
    if direction == "PUT" and not (trend5 == "DOWN" and trend15 == "DOWN"):
        return False, "Trend not aligned"

    # Candle strength
    body = intraday.get("body_pct", 0)
    close_pos = intraday.get("close_position", 0)

    if direction == "CALL" and (body < 0.4 or close_pos < 0.6):
        return False, "Weak reclaim candle"
    if direction == "PUT" and (body < 0.4 or close_pos > 0.4):
        return False, "Weak rejection candle"

    if intraday.get("confirmations", 0) < PULLBACK_MIN_CONFIRMATIONS:
        return False, "Low confirmation"

    return True, "Strong pullback + Fibonacci"


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
