import unittest

from swing_integration import _hold_days_to_horizon_minutes


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


if __name__ == "__main__":
    unittest.main()
