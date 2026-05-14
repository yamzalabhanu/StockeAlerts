import unittest
from unittest.mock import patch

from bot_enhancements import high_quality_alert_cap, is_etf_alert, select_top_high_quality_alerts


class RankedAlertSelectionTests(unittest.TestCase):
    def _candidate(self, ticker, score, alert_type="INTRADAY"):
        return {"ticker": ticker, "ranking_score": score, "alert_type": alert_type}

    def test_selects_top_five_intraday_and_top_five_swing_after_full_pool_is_ranked(self):
        alert_pool = [
            self._candidate("LOW", 10, "INTRADAY"),
            self._candidate("TOP", 100, "INTRADAY"),
            self._candidate("SECOND", 90, "INTRADAY"),
            self._candidate("THIRD", 80, "INTRADAY"),
            self._candidate("FOURTH", 70, "INTRADAY"),
            self._candidate("FIFTH", 60, "INTRADAY"),
            self._candidate("SIXTH", 50, "INTRADAY"),
            self._candidate("SW1", 95, "SWING"),
            self._candidate("SW2", 85, "SWING"),
            self._candidate("SW3", 75, "SWING"),
            self._candidate("SW4", 65, "SWING"),
            self._candidate("SW5", 55, "SWING"),
            self._candidate("SW6", 45, "SWING"),
        ]

        selected = select_top_high_quality_alerts(alert_pool)

        self.assertEqual(
            [candidate["ticker"] for candidate in selected],
            ["TOP", "SW1", "SECOND", "SW2", "THIRD", "SW3", "FOURTH", "SW4", "FIFTH", "SW5"],
        )

    def test_excludes_tickers_that_already_alerted_today(self):
        alert_pool = [
            self._candidate("TOP", 100),
            self._candidate("SECOND", 90),
            self._candidate("THIRD", 80),
        ]

        selected = select_top_high_quality_alerts(alert_pool, excluded_tickers={"TOP"})

        self.assertEqual(
            [candidate["ticker"] for candidate in selected],
            ["SECOND", "THIRD"],
        )

    def test_keeps_only_highest_ranked_alert_for_duplicate_ticker_in_same_scan(self):
        alert_pool = [
            self._candidate("DUP", 100, "INTRADAY"),
            self._candidate("DUP", 90, "SWING"),
            self._candidate("NEXT", 80, "SWING"),
        ]

        selected = select_top_high_quality_alerts(alert_pool)

        self.assertEqual(
            [(candidate["ticker"], candidate["alert_type"]) for candidate in selected],
            [("DUP", "INTRADAY"), ("NEXT", "SWING")],
        )

    def test_identifies_known_etf_alert_symbols(self):
        self.assertTrue(is_etf_alert(self._candidate("SPY", 100)))
        self.assertTrue(is_etf_alert(self._candidate("XLK", 100)))
        self.assertFalse(is_etf_alert(self._candidate("AAPL", 100)))

    @patch("bot_enhancements.MAX_ALERTS_PER_SCAN", 10)
    @patch("bot_enhancements.MAX_HIGH_QUALITY_ALERTS_PER_SCAN", 12)
    def test_alert_cap_never_exceeds_total_per_type_hard_cap(self):
        self.assertEqual(high_quality_alert_cap(), 10)

    @patch("bot_enhancements.MAX_ALERTS_PER_SCAN", 5)
    @patch("bot_enhancements.MAX_HIGH_QUALITY_ALERTS_PER_SCAN", 3)
    def test_alert_cap_can_be_lowered_for_quieter_scans(self):
        self.assertEqual(high_quality_alert_cap(), 3)

    @patch("bot_enhancements.MAX_TRADES_PER_TRADING_DAY", 10)
    @patch("bot_enhancements.MAX_ALERTS_PER_SCAN", 10)
    @patch("bot_enhancements.MAX_HIGH_QUALITY_ALERTS_PER_SCAN", 10)
    def test_daily_trade_cap_limits_remaining_ranked_alerts(self):
        alert_pool = [
            self._candidate("ONE", 100),
            self._candidate("TWO", 90),
            self._candidate("THREE", 80),
        ]

        selected = select_top_high_quality_alerts(alert_pool, daily_sent_count=8)

        self.assertEqual([candidate["ticker"] for candidate in selected], ["ONE", "TWO"])

    @patch("bot_enhancements.MAX_TRADES_PER_TRADING_DAY", 10)
    def test_daily_trade_cap_blocks_ranked_alerts_after_ten_trades(self):
        alert_pool = [self._candidate("ONE", 100)]

        selected = select_top_high_quality_alerts(alert_pool, daily_sent_count=10)

        self.assertEqual(selected, [])


if __name__ == "__main__":
    unittest.main()
