from adaptive_scoring import get_weight
from market_regime import regime_adjustment
from bot_utils import pct_diff
from config import *
from ml_learning import get_setup_score, train_from_rows

_ORIGINAL_BUILD_CANDIDATE_ATTR = "_original_build_candidate_before_enhancements"

# (existing functions unchanged above)


def learn_from_outcomes(results):
    """Compatibility layer for replay -> now uses ML training"""
    return train_from_rows(results)


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

        setup = candidate.get("setup", {})
        direction = setup.get("direction", "ANY")
        entry_mode = candidate.get("entry_mode", "STANDARD")

        # Apply ML adaptive scoring
        base_score = setup.get("score", 0)
        ml_score = get_setup_score(entry_mode, direction, base_score)
        setup["ml_score"] = ml_score
        setup["score"] = ml_score

        # Add fib extension targets
        if FIB_EXTENSION_ENABLED:
            candidate["fib_targets"] = _compute_fib_extensions(direction, candidate["tech"])

        return candidate

    bot_cls.detect_entry_mode = enhanced_detect_entry_mode
    bot_cls.build_candidate = enhanced_build_candidate
    return bot_cls
