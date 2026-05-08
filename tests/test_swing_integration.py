import unittest
from unittest.mock import patch

from swing_integration import _hold_days_to_horizon_minutes, process_swing_candidate


class SwingIntegrationHoldDaysTests(unittest.TestCase):
    def test_hold_day_range_uses_maximum_day_for_horizon(self):
        self.assertEqual(_hold_days_to_horizon_minutes("2-10"), 10 * 24 * 60)

    def test_hold_day_text_range_uses_maximum_day_for_horizon(self):
        self.assertEqual(_hold_days_to_horizon_minutes("2-10 days"), 10 * 24 * 60)

    def test_numeric_hold_days_still_supported(self):
        self.assertEqual(_hold_days_to_horizon_minutes(5), 5 * 24 * 60)

    def test_invalid_hold_days_falls_back_to_default(self):
        self.assertEqual(
            _hold_days_to_horizon_minutes("unknown", default_days=7),
            7 * 24 * 60,
        )


class SwingIntegrationTelegramSendTests(unittest.TestCase):
    def _setup(self):
        return {
            "direction": "CALL",
            "tier": "A+",
            "score": 90,
            "entry": 100,
            "stop": 95,
            "target": 120,
            "risk_reward": 4,
            "hold_days": "2-10",
            "reasons": ["test reason"],
        }

    def test_process_swing_candidate_only_returns_when_telegram_send_succeeds(self):
        class Bot:
            def send_telegram_msg(self, _message):
                return False

        with patch("swing_integration.score_swing_setup", return_value=self._setup()), \
            patch("swing_integration.build_reasoning_report", return_value={}), \
            patch("swing_integration.log_swing_alert") as log_swing_alert, \
            patch("swing_integration.track_outcome") as track_outcome:
            result = process_swing_candidate(Bot(), "TEST", {})

        self.assertIsNone(result)
        log_swing_alert.assert_not_called()
        track_outcome.assert_not_called()

    def test_process_swing_candidate_returns_setup_when_telegram_send_succeeds(self):
        class Bot:
            def send_telegram_msg(self, _message):
                return True

        with patch("swing_integration.score_swing_setup", return_value=self._setup()), \
            patch("swing_integration.build_reasoning_report", return_value={}), \
            patch("swing_integration.log_swing_alert"), \
            patch("swing_integration.track_outcome"):
            result = process_swing_candidate(Bot(), "TEST", {})

        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "CALL")


if __name__ == "__main__":
    unittest.main()
