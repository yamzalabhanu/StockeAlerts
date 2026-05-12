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
