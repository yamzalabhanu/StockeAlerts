from adaptive_scoring import get_weight, update_weights, load_weights, save_weights
from market_regime import regime_adjustment
from bot_utils import pct_diff


_ORIGINAL_BUILD_CANDIDATE_ATTR = "_original_build_candidate_before_enhancements"
_ORIGINAL_DETECT_ENTRY_MODE_ATTR = "_original_detect_entry_mode_before_enhancements"


def _near_pct(price, level, tolerance_pct):
    if price is None or level is None:
        return False
    diff = abs(pct_diff(price, level) or 999)
    return diff <= tolerance_pct


def _is_true_breakout_retest(direction, tech, tolerance_pct=0.45):
    """True retest = retest of ORB/PM/PD/recent breakout/breakdown level.

    EMA/VWAP touches are classified as PULLBACK instead.
    """
    price = tech.get("price")
    if direction == "CALL":
        levels = [
            ("ORB high", tech.get("orb_high")),
            ("premarket high", tech.get("premarket_high")),
            ("previous day high", tech.get("prev_high")),
            ("recent high", tech.get("recent_high")),
        ]
    else:
        levels = [
            ("ORB low", tech.get("orb_low")),
            ("premarket low", tech.get("premarket_low")),
            ("previous day low", tech.get("prev_low")),
            ("recent low", tech.get("recent_low")),
        ]

    for name, level in levels:
        if _near_pct(price, level, tolerance_pct):
            return True, name
    return False, None


def _is_intraday_pullback(direction, tech, tolerance_pct=0.65):
    """Pullback = EMA/VWAP reclaim/rejection during intraday move."""
    price = tech.get("price")
    levels = [("EMA21", tech.get("ema21")), ("VWAP", tech.get("vwap")), ("EMA9", tech.get("ema9"))]

    for name, level in levels:
        if not _near_pct(price, level, tolerance_pct):
            continue
        if direction == "CALL" and price >= level * 0.995:
            return True, name
        if direction == "PUT" and price <= level * 1.005:
            return True, name
    return False, None


def apply_enhancements(bot_cls):
    """Patch StockTechnicalAIBot with adaptive/regime ranking and cleaner entry modes."""
    if hasattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR):
        return bot_cls

    original_build_candidate = bot_cls.build_candidate
    original_detect_entry_mode = bot_cls.detect_entry_mode
    setattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR, original_build_candidate)
    setattr(bot_cls, _ORIGINAL_DETECT_ENTRY_MODE_ATTR, original_detect_entry_mode)

    def enhanced_detect_entry_mode(self, setup, tech, intraday_info):
        direction = setup["direction"]
        reasons_text = " ".join(setup.get("reasons", [])).lower()
        confirmations = int(intraday_info.get("confirmations", 0) or 0)
        rel_vol = float(intraday_info.get("rel_volume_5m", 0) or 0)
        trigger_dist = float(intraday_info.get("trigger_distance_pct", 0) or 0)

        true_retest, retest_level = _is_true_breakout_retest(direction, tech)
        pullback, pullback_level = _is_intraday_pullback(direction, tech)

        # Important: do not classify EMA/VWAP pullbacks as RETEST.
        if setup.get("retest_confirmed") and true_retest:
            return "RETEST", f"True breakout/breakdown retest near {retest_level}"

        if pullback:
            return "PULLBACK", f"Intraday pullback/reclaim near {pullback_level}; not a true breakout retest"

        if "breakout" in reasons_text or "breakdown" in reasons_text:
            if rel_vol >= 1.5 and confirmations >= 3 and trigger_dist <= 1.25:
                return "BREAKOUT", "Breakout with volume and intraday confirmation"

        if confirmations >= 3 and 0.75 <= trigger_dist <= 2.0:
            return "MOMENTUM", "Continuation/momentum entry within allowed extension"

        return "STANDARD", "General confirmed setup"

    async def enhanced_build_candidate(self, ticker):
        candidate = await original_build_candidate(self, ticker)
        if not candidate:
            return None

        entry_mode = candidate.get("entry_mode") or candidate.get("setup", {}).get("entry_mode", "STANDARD")
        market = self.get_market_bias()

        reg_adj = regime_adjustment(entry_mode, market)
        adaptive_bonus = get_weight(entry_mode)

        candidate["market_regime"] = reg_adj.regime
        candidate["regime_reason"] = reg_adj.reason
        candidate["regime_score_adjustment"] = reg_adj.score_adjustment
        candidate["adaptive_score_adjustment"] = adaptive_bonus
        candidate["ranking_score"] = (
            float(candidate.get("ranking_score", 0))
            + float(reg_adj.score_adjustment)
            + float(adaptive_bonus)
        )

        print(
            f"{ticker}: regime={reg_adj.regime} adj={reg_adj.score_adjustment} | "
            f"adaptive={adaptive_bonus} | final_rank={candidate['ranking_score']:.1f}"
        )
        return candidate

    bot_cls.detect_entry_mode = enhanced_detect_entry_mode
    bot_cls.build_candidate = enhanced_build_candidate
    return bot_cls


def learn_from_outcomes(outcomes):
    """Update adaptive weights from outcome rows that include entry_mode/result."""
    weights = load_weights()

    for row in outcomes:
        entry_mode = row.get("entry_mode")
        result = row.get("result")
        if not entry_mode or result not in {"WIN", "LOSS"}:
            continue
        weights = update_weights(entry_mode, result)

    return weights
