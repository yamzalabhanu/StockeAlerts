import asyncio

from adaptive_scoring import get_weight
from market_regime import regime_adjustment
from bot_utils import pct_diff
from config import *
from ml_learning import get_setup_score, train_from_rows
from ml_sklearn_model import adjust_score_with_logistic
from swing_integration import process_swing_candidate

_ORIGINAL_BUILD_CANDIDATE_ATTR = "_original_build_candidate_before_enhancements"
_ORIGINAL_CHECK_TICKER_ATTR = "_original_check_ticker_before_swing_integration"


def learn_from_outcomes(results):
    return train_from_rows(results)


def apply_enhancements(bot_cls):
    if hasattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR):
        return bot_cls

    original_build_candidate = bot_cls.build_candidate
    original_check_ticker = bot_cls.check_ticker
    setattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR, original_build_candidate)
    setattr(bot_cls, _ORIGINAL_CHECK_TICKER_ATTR, original_check_ticker)

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

        adjusted_score, prob, _ = adjust_score_with_logistic(candidate.get("tech", {}), ml_score)

        setup["ml_score"] = adjusted_score
        setup["score"] = adjusted_score
        setup["ml_probability"] = prob

        return candidate

    async def enhanced_check_ticker(self, ticker):
        try:
            await asyncio.sleep(0.15)

            tech = self.get_technical_context(ticker)
            if not tech:
                return None

            # Swing scan runs before intraday quality-window gate.
            # This allows 2-10 day swing setup alerts outside scalp windows.
            try:
                process_swing_candidate(self, ticker, tech)
            except Exception as e:
                print(f"{ticker}: swing scan error: {e}")

            if not ENABLE_INTRADAY_ALERTS:
                return None

            if not self.is_regular_market_hours() or not self.is_quality_trading_window():
                return None

            return await self.build_candidate(ticker)
        except Exception as e:
            print(f"{ticker}: error {e}")
            return None

    bot_cls.detect_entry_mode = enhanced_detect_entry_mode
    bot_cls.build_candidate = enhanced_build_candidate
    bot_cls.check_ticker = enhanced_check_ticker
    return bot_cls
