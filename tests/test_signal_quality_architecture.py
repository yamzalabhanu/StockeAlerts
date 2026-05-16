import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trade_attribution
from probabilistic_quality import classify_score, probabilistic_penalty_profile
from vision_ai import score_chart_structure
from market_phase import CHOP, TRENDING_UP, detect_market_phase


class SignalQualityArchitectureTests(unittest.TestCase):
    def test_probabilistic_profile_softens_former_hard_rejects(self):
        profile = probabilistic_penalty_profile(
            execution={"quality": "BAD"},
            setup_quality={"status": "REJECT"},
            mtf={"structure": "MIXED_ALIGNMENT"},
            vision={"quality": "GOOD"},
        )

        self.assertFalse(profile["hard_reject"])
        self.assertEqual(profile["penalty"], -29)
        self.assertEqual(classify_score(91), "ELITE")
        self.assertEqual(classify_score(73), "GOOD")

    def test_market_phase_adds_normalized_routing(self):
        trend = detect_market_phase(
            {"trend_5m": "BULLISH", "trend_15m": "BULLISH", "rel_volume": 1.5},
            {"direction": "CALL", "entry_mode": "BREAKOUT"},
        )
        chop = detect_market_phase({"rel_volume": 0.8}, {"direction": "CALL", "entry_mode": "BREAKOUT"})

        self.assertEqual(trend["normalized_phase"], TRENDING_UP)
        self.assertTrue(trend["routing"]["entry_mode_aligned"])
        self.assertEqual(chop["normalized_phase"], CHOP)
        self.assertIn("BREAKOUT_CHASE", chop["routing"]["avoid"])

    def test_vision_sequence_memory_rewards_orderly_retest_acceleration(self):
        scored = score_chart_structure(
            {
                "vision_sequence": [
                    {"price": 100, "momentum_score": 40},
                    {"price": 101, "momentum_score": 48, "retest_confirmed": True},
                    {"price": 102, "momentum_score": 58},
                ],
                "candle_body_pct": 65,
                "rel_volume": 2.0,
                "distance_from_vwap": 0.4,
            },
            "CALL",
        )

        self.assertIn("MOMENTUM_ACCELERATION", scored["tags"])
        self.assertIn("SEQUENCE_RETEST_CONFIRMED", scored["tags"])
        self.assertIn(scored["quality"], {"GOOD", "ELITE"})

    def test_setup_attribution_adjustment_uses_win_rate_rr_and_profit_factor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            attribution_file = Path(tmpdir) / "trade_attribution.csv"
            with attribution_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=trade_attribution.FIELDS)
                writer.writeheader()
                for _ in range(7):
                    writer.writerow({"setup_type": "ORB_RETEST_CALL", "result": "WIN", "pnl_r": "1.6", "drawdown_r": "0.4"})
                for _ in range(2):
                    writer.writerow({"setup_type": "ORB_RETEST_CALL", "result": "LOSS", "pnl_r": "-1.0", "drawdown_r": "1.0"})

            with patch.object(trade_attribution, "ATTRIBUTION_FILE", str(attribution_file)):
                stats = trade_attribution.analyze_trade_performance()["setup_stats"]["ORB_RETEST_CALL"]
                adjustment = trade_attribution.setup_attribution_adjustment("ORB_RETEST_CALL", min_trades=5)

        self.assertGreater(stats["win_rate"], 0.7)
        self.assertGreater(stats["profit_factor"], 1.5)
        self.assertGreater(adjustment["adjustment"], 0)


if __name__ == "__main__":
    unittest.main()
