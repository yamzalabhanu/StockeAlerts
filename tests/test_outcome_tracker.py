import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import outcome_tracker


class OutcomeTrackerAuthorizationTests(unittest.TestCase):
    def setUp(self):
        outcome_tracker._outcome_tracking_disabled_reason = None

    def tearDown(self):
        outcome_tracker._outcome_tracking_disabled_reason = None

    def _track(self, ticker="TEST"):
        return outcome_tracker.track_outcome(
            ticker=ticker,
            direction="CALL",
            entry=100,
            stop=95,
            target=110,
            alert_time_iso="2026-05-12T14:30:00+00:00",
        )

    def test_disables_outcome_tracking_after_polygon_timeframe_entitlement_error(self):
        class Client:
            calls = 0

            def list_aggs(self, **_kwargs):
                self.calls += 1
                raise Exception(
                    '{"status":"NOT_AUTHORIZED","message":"Your plan doesn\'t include this data timeframe."}'
                )

        client = Client()

        with patch.object(outcome_tracker, "client", client), \
            patch.object(outcome_tracker, "ENABLE_OUTCOME_TRACKING", True, create=True), \
            patch.object(outcome_tracker, "OUTCOME_TRACKING_SKIP_UNAUTHORIZED", True, create=True), \
            patch("builtins.print") as printed:
            self.assertIsNone(self._track("NXPI"))
            self.assertIsNone(self._track("ALAB"))

        self.assertEqual(client.calls, 1)
        printed.assert_called_once()
        self.assertIn("Outcome tracking disabled for this run", printed.call_args.args[0])
        self.assertIn("Polygon API plan", printed.call_args.args[0])

    def test_can_disable_outcome_tracking_without_fetching_polygon(self):
        class Client:
            def list_aggs(self, **_kwargs):
                raise AssertionError("Polygon should not be called when outcome tracking is disabled")

        with patch.object(outcome_tracker, "client", Client()), \
            patch.object(outcome_tracker, "ENABLE_OUTCOME_TRACKING", False, create=True):
            self.assertIsNone(self._track())


    def test_records_enriched_trade_context_fields(self):
        class Bar:
            timestamp = 1770733860000  # 2026-02-10 14:31:00 UTC / 09:31 ET
            high = 111
            low = 99

        class Client:
            def list_aggs(self, **_kwargs):
                return [Bar()]

        appended = []

        with patch.object(outcome_tracker, "client", Client()), \
            patch.object(outcome_tracker, "ENABLE_OUTCOME_TRACKING", True, create=True), \
            patch.object(outcome_tracker, "append_outcome_row", lambda _path, row: appended.append(row)), \
            patch.object(outcome_tracker, "refresh_learning_model", lambda: {}):
            row = outcome_tracker.track_outcome(
                ticker="AAPL",
                direction="CALL",
                entry=100,
                stop=95,
                target=110,
                alert_time_iso="2026-02-10T14:30:00+00:00",
                setup_context={
                    "market_phase": "TREND_CONTINUATION",
                    "tech": {
                        "breakout_distance_atr": 0.8,
                        "wick_ratio": 1.2,
                        "candle_body_pct": 64,
                        "distance_from_vwap": 0.7,
                        "distance_from_ema21": 1.1,
                        "rel_volume": 2.4,
                    },
                    "option_contract": {
                        "spread_pct": 8.5,
                        "volume": 1200,
                        "open_interest": 5400,
                    },
                    "sector_relative_strength": "XLK +1.2% vs SPY",
                    "ai": {"verdict": "BUY", "reason": "Clean continuation."},
                },
            )

        self.assertEqual(row["result"], "WIN")
        self.assertEqual(row["market_phase"], "TREND_CONTINUATION")
        self.assertEqual(row["time_of_day_bucket"], "OPENING_30")
        self.assertEqual(row["atr_extension"], 0.8)
        self.assertEqual(row["wick_ratio"], 1.2)
        self.assertEqual(row["candle_body_pct"], 64)
        self.assertEqual(row["distance_from_vwap"], 0.7)
        self.assertEqual(row["distance_from_ema21"], 1.1)
        self.assertEqual(row["rel_volume"], 2.4)
        self.assertEqual(row["spread_pct"], 8.5)
        self.assertEqual(row["option_volume"], 1200)
        self.assertEqual(row["open_interest"], 5400)
        self.assertEqual(row["sector_relative_strength"], "XLK +1.2% vs SPY")
        self.assertEqual(row["deep_ai_approval"], "BUY")
        self.assertEqual(appended[0], row)

    def test_non_entitlement_errors_still_log_per_ticker(self):
        class Client:
            def list_aggs(self, **_kwargs):
                raise RuntimeError("temporary network error")

        with patch.object(outcome_tracker, "client", Client()), \
            patch.object(outcome_tracker, "ENABLE_OUTCOME_TRACKING", True, create=True), \
            patch.object(outcome_tracker, "OUTCOME_TRACKING_SKIP_UNAUTHORIZED", True, create=True), \
            patch("builtins.print") as printed:
            self.assertIsNone(self._track("FTNT"))

        printed.assert_called_once_with("FTNT: outcome fetch error temporary network error")
        self.assertIsNone(outcome_tracker._outcome_tracking_disabled_reason)


if __name__ == "__main__":
    unittest.main()
