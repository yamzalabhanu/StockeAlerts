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


def _compute_fib_extensions(direction, tech):
    if not FIB_EXTENSION_ENABLED:
        return []

    high = tech.get("recent_high")
    low = tech.get("recent_low")

    if not high or not low:
        return []

    extensions = []
    for ext in FIB_EXTENSION_LEVELS:
        if direction == "CALL":
            extensions.append(high + (high - low) * (ext - 1))
        else:
            extensions.append(low - (high - low) * (ext - 1))

    return extensions


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

    # MTF confluence (proxy using PDH/PDL overlap)
    if MTF_FIB_CONFLUENCE_ENABLED:
        for fib in fib_levels:
            if _near_pct(fib, tech.get("prev_high") or tech.get("prev_low"), MTF_FIB_TOLERANCE_PCT):
                confluence += 1

    return confluence >= FIB_MIN_CONFLUENCE_COUNT


def _entry_timing_ok(direction, tech, intraday):
    if not FIB_ENTRY_ZONE_ENABLED:
        return True

    price = tech.get("price")
    fib_levels = _compute_fib_levels(direction, tech)

    in_zone = any(_near_pct(price, fib, FIB_ENTRY_ZONE_TOLERANCE_PCT) for fib in fib_levels)

    if not in_zone:
        return False

    if FIB_ENTRY_REQUIRE_RECLAIM:
        body = intraday.get("body_pct", 0)
        close_pos = intraday.get("close_position", 0)

        if direction == "CALL" and (body < 0.4 or close_pos < 0.6):
            return False
        if direction == "PUT" and (body < 0.4 or close_pos > 0.4):
            return False

    return intraday.get("confirmations", 0) >= FIB_ENTRY_MIN_CONFIRMATIONS


def is_strong_pullback(direction, tech, intraday):
    price = tech.get("price")
    ema21 = tech.get("ema21")
    vwap = tech.get("vwap")

    if not price:
        return False, "No price"

    if not (ema21 and _near_pct(price, ema21, PULLBACK_ZONE_TOLERANCE_PCT) or
            vwap and _near_pct(price, vwap, PULLBACK_ZONE_TOLERANCE_PCT)):
        return False, "Not near EMA/VWAP"

    if not _fib_confluence(direction, tech):
        return False, "No Fib confluence"

    if not _entry_timing_ok(direction, tech, intraday):
        return False, "Bad entry timing"

    trend5 = tech.get("trend_5m")
    trend15 = tech.get("trend_15m")

    if direction == "CALL" and not (trend5 == "UP" and trend15 == "UP"):
        return False, "Trend not aligned"
    if direction == "PUT" and not (trend5 == "DOWN" and trend15 == "DOWN"):
        return False, "Trend not aligned"

    return True, "A+ Pullback (Full Fib System)"


def apply_enhancements(bot_cls):
    if hasattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR):
        return bot_cls

    original_build_candidate = bot_cls.build_candidate

    def enhanced_detect_entry_mode(self, setup, tech, intraday_info):
        direction = setup["direction"]

        valid, reason = is_strong_pullback(direction, tech, intraday_info)
        if valid:
            return "PULLBACK", reason

        return "STANDARD", "Weak setup"

    async def enhanced_build_candidate(self, ticker):
        candidate = await original_build_candidate(self, ticker)
        if not candidate:
            return None

        # Add fib extension targets
        if FIB_EXTENSION_ENABLED:
            candidate["fib_targets"] = _compute_fib_extensions(candidate["setup"]["direction"], candidate["tech"])

        return candidate

    bot_cls.detect_entry_mode = enhanced_detect_entry_mode
    bot_cls.build_candidate = enhanced_build_candidate
    return bot_cls
