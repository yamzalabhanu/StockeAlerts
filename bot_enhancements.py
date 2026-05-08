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
_ORIGINAL_DETECT_ENTRY_MODE_ATTR = "_original_detect_entry_mode_before_enhancements"
_ORIGINAL_RUN_ATTR = "_original_run_before_swing_integration"


def learn_from_outcomes(results):
    return train_from_rows(results)


def apply_enhancements(bot_cls):
    if hasattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR):
        return bot_cls

    original_build_candidate = bot_cls.build_candidate
    original_check_ticker = bot_cls.check_ticker
    original_detect_entry_mode = bot_cls.detect_entry_mode
    original_run = bot_cls.run
    setattr(bot_cls, _ORIGINAL_BUILD_CANDIDATE_ATTR, original_build_candidate)
    setattr(bot_cls, _ORIGINAL_CHECK_TICKER_ATTR, original_check_ticker)
    setattr(bot_cls, _ORIGINAL_DETECT_ENTRY_MODE_ATTR, original_detect_entry_mode)
    setattr(bot_cls, _ORIGINAL_RUN_ATTR, original_run)

    def enhanced_detect_entry_mode(self, setup, tech, intraday_info):
        entry_mode, reason = original_detect_entry_mode(self, setup, tech, intraday_info)
        adaptive_weight = get_weight(entry_mode)
        if adaptive_weight:
            setup["adaptive_weight"] = adaptive_weight
            setup["score"] = round(max(0, min(100, float(setup.get("score", 0) or 0) + adaptive_weight)), 2)
            reason = f"{reason}; adaptive setup weight {adaptive_weight:+.1f}"
        return entry_mode, reason

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

    async def enhanced_run(self):
        print("🚀 Stock Technical AI Bot Running")
        while True:
            try:
                in_intraday_window = self.is_regular_market_hours() and self.is_quality_trading_window()

                if not in_intraday_window:
                    self.maybe_send_daily_learning_report()

                    if not ENABLE_SWING_ALERTS:
                        print("⏸ Outside quality market window | sleeping 600s")
                        await asyncio.sleep(600)
                        continue

                    print("⏳ Outside intraday quality window | running swing scan")

                self.tickers = self.get_auto_watchlist()
                candidates = []

                for ticker in self.tickers:
                    candidate = await self.check_ticker(ticker)
                    if candidate:
                        candidates.append(candidate)

                candidates.sort(key=lambda x: x["ranking_score"], reverse=True)
                selected = candidates[:MAX_ALERTS_PER_SCAN] if RANK_TOP_ALERTS_ONLY else candidates

                sent = 0
                if in_intraday_window and ENABLE_INTRADAY_ALERTS:
                    for c in selected:
                        self.alert(
                            c["ticker"],
                            c["setup"],
                            c["tech"],
                            c["ai"],
                            c.get("intraday"),
                            c.get("entry_mode", "STANDARD"),
                            c.get("mode_reason", ""),
                            c["ranking_score"],
                        )
                        self.mark_alert(c["ticker"], c["setup"]["direction"])
                        sent += 1

                sleep_for = SCAN_INTERVAL_SEC if in_intraday_window else 600
                scan_label = "full scan" if in_intraday_window else "swing scan"
                print(f"✅ {scan_label} complete | candidates={len(candidates)} | sent={sent} | sleeping {sleep_for}s")
                await asyncio.sleep(sleep_for)
            except Exception as e:
                print(f"Scan loop error: {e}")
                await asyncio.sleep(SCAN_INTERVAL_SEC)

    bot_cls.detect_entry_mode = enhanced_detect_entry_mode
    bot_cls.build_candidate = enhanced_build_candidate
    bot_cls.check_ticker = enhanced_check_ticker
    bot_cls.run = enhanced_run
    return bot_cls
