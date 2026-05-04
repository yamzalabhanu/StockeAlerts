from adaptive_scoring import get_weight, update_weights, load_weights, save_weights
from market_regime import regime_adjustment
from bot_utils import pct_diff
from config import *

_ORIGINAL_BUILD_CANDIDATE_ATTR = "_original_build_candidate_before_enhancements"
_ORIGINAL_DETECT_ENTRY_MODE_ATTR = "_original_detect_entry_mode_before_enhancements"


def _near_pct(price, level, tolerance_pct):
    if price is None or level is None:
        return False
    diff = abs(pct_diff(price, level) or 999)
    return diff <= tolerance_pct


def _is_true_breakout_retest(direction, tech, tolerance_pct=0.45):
    price = tech.get("price")
    if direction == "CALL":
        levels = [("ORB high", tech.get("orb_high")), ("premarket high", tech.get("premarket_high")), ("previous day high", tech.get("prev_high")), ("recent high", tech.get("recent_high"))]
    else:
        levels = [("ORB low", tech.get("orb_low")), ("premarket low", tech.get("premarket_low")), ("previous day low", tech.get("prev_low")), ("recent low", tech.get("recent_low"))]

    for name, level in levels:
        if _near_pct(price, level, tolerance_pct):
            return True, name
    return False, None


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

    return True, "Strong pullback"


def apply_enhancements(bot_cls):
    if hasattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR):
        return bot_cls

    original_build_candidate = bot_cls.build_candidate

    def enhanced_detect_entry_mode(self, setup, tech, intraday_info):
        direction = setup["direction"]
        reasons_text = " ".join(setup.get("reasons", [])).lower()
        confirmations = int(intraday_info.get("confirmations", 0) or 0)
        rel_vol = float(intraday_info.get("rel_volume_5m", 0) or 0)
        trigger_dist = float(intraday_info.get("trigger_distance_pct", 0) or 0)

        true_retest, level = _is_true_breakout_retest(direction, tech)
        valid_pullback, pb_reason = is_strong_pullback(direction, tech, intraday_info)

        if setup.get("retest_confirmed") and true_retest:
            return "RETEST", f"Retest near {level}"

        if valid_pullback:
            return "PULLBACK", pb_reason

        if "breakout" in reasons_text and rel_vol >= 1.5 and confirmations >= 3:
            return "BREAKOUT", "Strong breakout"

        if confirmations >= 3:
            return "MOMENTUM", "Momentum continuation"

        return "STANDARD", "Weak setup"

    async def enhanced_build_candidate(self, ticker):
        candidate = await original_build_candidate(self, ticker)
        if not candidate:
            return None

        setup = candidate["setup"]
        mode = candidate.get("entry_mode")

        if A_PLUS_MODE:
            if mode == "PULLBACK" and setup["score"] < A_PLUS_PULLBACK_MIN_SCORE:
                return None
            if mode == "BREAKOUT" and setup["score"] < A_PLUS_BREAKOUT_MIN_SCORE:
                return None
            if mode == "MOMENTUM" and setup["score"] < A_PLUS_MOMENTUM_MIN_SCORE:
                return None

        reg_adj = regime_adjustment(mode, self.get_market_bias())
        adaptive_bonus = get_weight(mode)

        candidate["ranking_score"] += reg_adj.score_adjustment + adaptive_bonus

        return candidate

    bot_cls.detect_entry_mode = enhanced_detect_entry_mode
    bot_cls.build_candidate = enhanced_build_candidate
    return bot_cls


def learn_from_outcomes(outcomes):
    weights = load_weights()

    for row in outcomes:
        entry_mode = row.get("entry_mode")
        result = row.get("result")
        if not entry_mode or result not in {"WIN", "LOSS"}:
            continue
        weights = update_weights(entry_mode, result)

    return weights
