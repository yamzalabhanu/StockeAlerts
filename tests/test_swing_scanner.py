import unittest

import swing_scanner


class SwingScannerConfigTests(unittest.TestCase):
    def test_pullback_tolerance_is_defined_from_config(self):
        self.assertEqual(swing_scanner.SWING_PULLBACK_TOLERANCE_PCT, 1.0)

    def test_structure_score_uses_pullback_tolerance_without_name_error(self):
        score, reasons = swing_scanner._structure_score(
            "CALL",
            {"recent_high": 110, "prev_high": 109},
            price=100.5,
            ema20=100,
            ema50=95,
        )

        self.assertGreaterEqual(score, 12)
        self.assertIn("EMA20 pullback zone", reasons)

    def test_institutional_price_action_rewards_high_quality_call_setup(self):
        tech = {
            "price": 121,
            "atr14": 3,
            "ema9": 119,
            "ema21": 116,
            "ema50": 110,
            "dma50": 110,
            "prev_high": 118,
            "previous_recent_high": 118,
            "prev_low": 112,
            "previous_recent_low": 112,
            "recent_high": 122,
            "recent_low": 114,
            "daily_highs": [105, 109, 112, 115, 118, 119, 120, 121, 121.5, 122],
            "daily_lows": [95, 98, 101, 104, 107, 116, 117, 118, 119, 120],
            "daily_volumes": [2_000_000] * 5 + [1_000_000] * 5,
            "last_5_lows": [116.9, 117.2, 118.1, 118.4, 119.0],
            "last_5_highs": [119, 120, 121, 121.5, 122],
            "last_5_closes": [117, 118, 119, 120, 121],
            "rel_volume": 0.8,
        }

        score, reasons = swing_scanner._institutional_price_action_score(
            "CALL",
            tech,
            price=121,
            atr=3,
            closes=tech["last_5_closes"],
            ema20=116,
            ema50=110,
        )

        self.assertGreaterEqual(score, 80)
        self.assertIn("HH/HL bullish market structure", reasons)
        self.assertIn("9/21/50 EMA bullish stage alignment", reasons)
        self.assertIn("base breakout through pivot resistance", reasons)
        self.assertIn("breakout retest held", reasons)
        self.assertIn("volume dry-up during base", reasons)
        self.assertIn("VCP volatility contraction", reasons)

    def test_format_swing_alert_does_not_present_skip_as_option_recommendation(self):
        message = swing_scanner.format_swing_alert(
            "TEST",
            {
                "direction": "CALL",
                "tier": "A",
                "score": 90,
                "entry": 100,
                "stop": 95,
                "target": 110,
                "risk_reward": 2,
                "hold_days": "2-10",
                "reasons": ["benchmark"],
                "option_contract": {
                    "status": "SKIP",
                    "reason": "No option passed filters",
                },
            },
        )

        self.assertNotIn("Option Recommendation: SKIP", message)
        self.assertNotIn("No option passed filters", message)
        self.assertNotIn("Recommended Contract", message)

    def test_atr_extension_and_failed_reclaim_penalize_late_breakouts(self):
        tech = {
            "price": 130,
            "ema21": 100,
            "last_5_closes": [99, 98],
            "failed_reclaim": True,
        }

        score, reasons = swing_scanner._institutional_price_action_score(
            "CALL",
            tech,
            price=130,
            atr=10,
            closes=[95, 96, 97, 98, 99],
            ema20=100,
            ema50=95,
        )

        self.assertLessEqual(score, -25)
        self.assertIn("extended 3.0 ATR from EMA", reasons)
        self.assertIn("failed reclaim / rejection at key level", reasons)


if __name__ == "__main__":
    unittest.main()
