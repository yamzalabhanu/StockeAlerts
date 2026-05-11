import unittest
from unittest.mock import patch

from bot_enhancements import high_quality_alert_cap, is_etf_alert, select_top_high_quality_alerts


class RankedAlertSelectionTests(unittest.TestCase):
    def _candidate(self, ticker, score):
        return {"ticker": ticker, "ranking_score": score}

    def test_selects_top_two_etfs_and_top_three_stocks_after_full_pool_is_ranked(self):
        alert_pool = [
            self._candidate("LOW", 10),
            self._candidate("SPY", 95),
            self._candidate("QQQ", 90),
            self._candidate("IWM", 85),
            self._candidate("TOP", 100),
            self._candidate("SECOND", 80),
            self._candidate("THIRD", 70),
            self._candidate("FOURTH", 60),
        ]

        selected = select_top_high_quality_alerts(alert_pool)

        self.assertEqual(
            [candidate["ticker"] for candidate in selected],
            ["TOP", "SPY", "QQQ", "SECOND", "THIRD"],
        )

    def test_does_not_backfill_missing_etfs_with_extra_stock_alerts(self):
        alert_pool = [
            self._candidate("TOP", 100),
            self._candidate("SECOND", 90),
            self._candidate("THIRD", 80),
            self._candidate("FOURTH", 70),
            self._candidate("FIFTH", 60),
        ]

        selected = select_top_high_quality_alerts(alert_pool)

        self.assertEqual(
            [candidate["ticker"] for candidate in selected],
            ["TOP", "SECOND", "THIRD"],
        )

    def test_identifies_known_etf_alert_symbols(self):
        self.assertTrue(is_etf_alert(self._candidate("SPY", 100)))
        self.assertTrue(is_etf_alert(self._candidate("XLK", 100)))
        self.assertFalse(is_etf_alert(self._candidate("AAPL", 100)))

    @patch("bot_enhancements.MAX_ALERTS_PER_SCAN", 5)
    @patch("bot_enhancements.MAX_HIGH_QUALITY_ALERTS_PER_SCAN", 12)
    def test_alert_cap_never_exceeds_top_five_hard_cap(self):
        self.assertEqual(high_quality_alert_cap(), 5)

    @patch("bot_enhancements.MAX_ALERTS_PER_SCAN", 5)
    @patch("bot_enhancements.MAX_HIGH_QUALITY_ALERTS_PER_SCAN", 3)
    def test_alert_cap_can_be_lowered_for_quieter_scans(self):
        self.assertEqual(high_quality_alert_cap(), 3)


if __name__ == "__main__":
    unittest.main()
