import asyncio

from adaptive_scoring import get_weight
from market_regime import regime_adjustment
from bot_utils import pct_diff
from config import *
from ml_learning import get_setup_score, train_from_rows
from ml_sklearn_model import adjust_score_with_logistic
from swing_integration import process_swing_candidate
from alert_history import alerted_tickers_today, mark_alerted_today, was_alerted_today

_ORIGINAL_BUILD_CANDIDATE_ATTR = "_original_build_candidate_before_enhancements"
_ORIGINAL_CHECK_TICKER_ATTR = "_original_check_ticker_before_swing_integration"
_ORIGINAL_DETECT_ENTRY_MODE_ATTR = "_original_detect_entry_mode_before_enhancements"
_ORIGINAL_RUN_ATTR = "_original_run_before_swing_integration"


def learn_from_outcomes(results):
    return train_from_rows(results)


def high_quality_alert_cap(daily_sent_count=0):
    """Return the ranked-alert cap after per-scan and daily trade limits."""
    configured_cap = max(0, int(MAX_HIGH_QUALITY_ALERTS_PER_SCAN))
    hard_cap = max(0, int(MAX_ALERTS_PER_SCAN))
    daily_remaining = max(0, int(MAX_TRADES_PER_TRADING_DAY) - int(daily_sent_count or 0))
    return min(configured_cap, hard_cap, daily_remaining)


def _candidate_ticker(candidate):
    return str(candidate.get("ticker", "")).upper()


def is_etf_alert(candidate):
    """Return True when a ranked alert candidate is one of the tracked ETFs."""
    return _candidate_ticker(candidate) in set(ETF_ALERT_SYMBOLS)


def select_top_high_quality_alerts(alert_pool, excluded_tickers=None, daily_sent_count=None):
    """Rank a completed scan and return capped intraday and swing alerts.

    The scanner should finish evaluating every ticker before this selection runs.
    It sends no more than five intraday alerts and five swing-trade alerts per
    scan by default, while suppressing tickers that already alerted today,
    avoiding multiple alerts for the same ticker in the same ranked batch, and
    respecting the market-day trade cap.
    """
    excluded = {str(ticker).upper() for ticker in (excluded_tickers or set())}
    if daily_sent_count is None:
        daily_sent_count = len(excluded)
    remaining_daily_slots = high_quality_alert_cap(daily_sent_count)
    if remaining_daily_slots <= 0:
        return []
    ranked_alerts = sorted(
        alert_pool,
        key=lambda x: x.get("ranking_score", 0),
        reverse=True,
    )
    per_type_caps = {
        "INTRADAY": max(0, int(MAX_INTRADAY_ALERTS_PER_SCAN)),
        "SWING": max(0, int(MAX_SWING_ALERTS_PER_SCAN)),
    }
    selected_counts = {alert_type: 0 for alert_type in per_type_caps}
    selected = []
    selected_tickers = set()

    for candidate in ranked_alerts:
        ticker = _candidate_ticker(candidate)
        alert_type = str(candidate.get("alert_type", "INTRADAY")).upper()
        if not ticker or ticker in excluded or ticker in selected_tickers:
            continue
        if alert_type not in per_type_caps:
            continue
        if selected_counts[alert_type] >= per_type_caps[alert_type]:
            continue

        selected.append(candidate)
        selected_tickers.add(ticker)
        selected_counts[alert_type] += 1

    selected.sort(key=lambda x: x.get("ranking_score", 0), reverse=True)
    return selected[:remaining_daily_slots]


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

            if was_alerted_today(ticker):
                print(f"{ticker}: skipped, alert already sent today")
                return None

            tech = self.get_technical_context(ticker)
            if not tech:
                return None

            # Swing scan runs before intraday quality-window gate so high-quality
            # swing setups can alert/route immediately (no end-of-scan batching).
            try:
                if ENABLE_SWING_ALERTS:
                    swing_setup = process_swing_candidate(
                        self,
                        ticker,
                        tech,
                        send_alert=True,
                    )
                    if swing_setup:
                        self._swing_alerts_sent_this_scan = getattr(self, "_swing_alerts_sent_this_scan", 0) + 1
            except Exception as e:
                print(f"{ticker}: swing scan error: {e}")

            if not ENABLE_INTRADAY_ALERTS:
                return None

            if not tech.get("intraday_available", True):
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
                self.maybe_manage_option_positions()
                in_intraday_window = self.is_regular_market_hours() and self.is_quality_trading_window()

                if not in_intraday_window:
                    self.maybe_send_daily_learning_report()

                    if not ENABLE_SWING_ALERTS:
                        print("⏸ Outside quality market window | sleeping 600s")
                        await self.sleep_with_option_management(600)
                        continue

                    print("⏳ Outside intraday quality window | running swing scan")

                self.tickers = self.get_auto_watchlist()
                self._swing_alerts_sent_this_scan = 0
                intraday_sent = 0

                for ticker in self.tickers:
                    if intraday_sent >= max(0, int(MAX_INTRADAY_ALERTS_PER_SCAN)):
                        print("⏸ Intraday per-scan cap reached; skipping remaining intraday candidates")
                        break
                    candidate = await self.check_ticker(ticker)
                    if candidate:
                        alert_sent = self.alert(
                            candidate["ticker"],
                            candidate["setup"],
                            candidate["tech"],
                            candidate["ai"],
                            candidate.get("intraday"),
                            candidate.get("entry_mode", "STANDARD"),
                            candidate.get("mode_reason", ""),
                            candidate["ranking_score"],
                        )
                        if alert_sent:
                            self.mark_alert(candidate["ticker"], candidate["setup"]["direction"])
                            mark_alerted_today(candidate["ticker"])
                            intraday_sent += 1

                sleep_for = SCAN_INTERVAL_SEC if in_intraday_window else 600
                scan_label = "full scan" if in_intraday_window else "swing scan"
                print(
                    f"✅ {scan_label} complete | intraday_sent={intraday_sent} | "
                    f"swing_sent={self._swing_alerts_sent_this_scan} | sleeping {sleep_for}s"
                )
                await self.sleep_with_option_management(sleep_for)
            except Exception as e:
                print(f"Scan loop error: {e}")
                await self.sleep_with_option_management(SCAN_INTERVAL_SEC)

    bot_cls.detect_entry_mode = enhanced_detect_entry_mode
    bot_cls.build_candidate = enhanced_build_candidate
    bot_cls.check_ticker = enhanced_check_ticker
    bot_cls.run = enhanced_run
    return bot_cls
