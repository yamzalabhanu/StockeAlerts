import unittest

from alert_formatting import format_predicted_price_move, format_recommended_option_contract


class AlertFormattingTests(unittest.TestCase):
    def test_predicted_price_move_formats_call_target_and_stop_risk(self):
        line = format_predicted_price_move("CALL", 100, 112, 96)

        self.assertIn("Predicted Price Move", line)
        self.assertIn("+$12.00", line)
        self.assertIn("+12.00%", line)
        self.assertIn("Stop Risk +$4.00", line)

    def test_predicted_price_move_formats_put_directional_target(self):
        line = format_predicted_price_move("PUT", 100, 92, 104)

        self.assertIn("+$8.00", line)
        self.assertIn("+8.00%", line)
        self.assertIn("toward $92.00", line)

    def test_recommended_option_contract_includes_details_and_estimated_move(self):
        block = format_recommended_option_contract(
            {
                "status": "OK",
                "contract_symbol": "O:XYZTESTC00105000",
                "option_type": "CALL",
                "strike": 105,
                "expiry": "2099-01-15",
                "dte": 14,
                "bid": 2.4,
                "ask": 2.7,
                "mid": 2.55,
                "spread_pct": 11.76,
                "volume": 5000,
                "open_interest": 12000,
                "volume_oi_ratio": 0.417,
                "recommendation_score": 74.2,
                "delta": 0.47,
                "theta": -0.07,
                "implied_volatility": 0.62,
            },
            direction="CALL",
            entry=101,
            target=112,
        )

        self.assertIn("Recommended Contract", block)
        self.assertIn("O:XYZTESTC00105000", block)
        self.assertIn("Strike $105.00", block)
        self.assertIn("Est. Contract Move", block)
        self.assertIn("delta-only", block)


if __name__ == "__main__":
    unittest.main()
