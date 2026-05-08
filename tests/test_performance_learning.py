import unittest

from performance_learning import DEFAULT_FORECAST_ACCURACY, DEFAULT_WIN_RATE, build_learning_model, get_setup_learning
from swing_scanner import format_swing_alert


class PerformanceLearningFallbackTests(unittest.TestCase):
    def test_missing_learning_history_uses_neutral_baseline_not_zero(self):
        learning = get_setup_learning(
            {"alert_type": "SWING", "entry_mode": "SWING", "direction": "CALL"},
            model={"buckets": {}},
        )

        self.assertEqual(learning["key"], "BASELINE")
        self.assertEqual(learning["stats"]["win_rate"], DEFAULT_WIN_RATE)
        self.assertEqual(learning["stats"]["forecast_accuracy"], DEFAULT_FORECAST_ACCURACY)

    def test_incomplete_zero_move_rows_do_not_force_zero_forecast(self):
        model = build_learning_model([
            {
                "alert_type": "SWING",
                "entry_mode": "SWING",
                "direction": "CALL",
                "entry": 100,
                "target": 110,
                "result": "OPEN_OR_BREAKEVEN",
                "max_gain_pct": 0,
                "max_loss_pct": 0,
                "forecast_accuracy_pct": 0,
            }
        ])

        self.assertEqual(model["buckets"]["ALL"]["forecast_accuracy"], DEFAULT_FORECAST_ACCURACY)
        self.assertEqual(model["buckets"]["ALL"]["forecast_accuracy_samples"], 0)

    def test_swing_alert_history_line_does_not_display_zero_for_missing_stats(self):
        message = format_swing_alert(
            "TEST",
            {
                "direction": "CALL",
                "tier": "A+",
                "score": 95,
                "entry": 100,
                "stop": 95,
                "target": 115,
                "risk_reward": 3,
                "hold_days": "2-10",
                "reasons": ["benchmark"],
                "ai_reasoning": {"decision": "A+", "final_score": 95},
            },
        )

        self.assertIn("WR 50.0%", message)
        self.assertIn("Forecast 50.0%", message)


if __name__ == "__main__":
    unittest.main()
