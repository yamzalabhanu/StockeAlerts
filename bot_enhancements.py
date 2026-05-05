from adaptive_scoring import get_weight
from market_regime import regime_adjustment
from bot_utils import pct_diff
from config import *
from ml_learning import get_setup_score, train_from_rows
from ml_sklearn_model import adjust_score_with_logistic

_ORIGINAL_BUILD_CANDIDATE_ATTR = "_original_build_candidate_before_enhancements"

# NOTE: ensure original helper functions remain in file above this section


def learn_from_outcomes(results):
    return train_from_rows(results)


def apply_enhancements(bot_cls):
    if hasattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR):
        return bot_cls

    original_build_candidate = bot_cls.build_candidate

    def enhanced_detect_entry_mode(self, setup, tech, intraday_info):
        return "STANDARD", "ML-driven"

    async def enhanced_build_candidate(self, ticker):
        candidate = await original_build_candidate(self, ticker)
        if not candidate:
            return None

        setup = candidate.get("setup", {})
        direction = setup.get("direction", "ANY")
        entry_mode = candidate.get("entry_mode", "STANDARD")

        base_score = setup.get("score", 0)
        ml_score = get_setup_score(entry_mode, direction, base_score)

        # Logistic regression probability adjustment
        adjusted_score, prob, _ = adjust_score_with_logistic(candidate.get("tech", {}), ml_score)

        setup["ml_score"] = adjusted_score
        setup["score"] = adjusted_score
        setup["ml_probability"] = prob

        return candidate

    bot_cls.detect_entry_mode = enhanced_detect_entry_mode
    bot_cls.build_candidate = enhanced_build_candidate
    return bot_cls
