import unittest
from unittest.mock import patch

from ai_reasoning_engine import build_reasoning_report
from bot import StockTechnicalAIBot


class IntradayHighQualityConfigTests(unittest.TestCase):
    def _build_report(self):
        with patch("ai_reasoning_engine.detect_market_regime", return_value={"regime": "UNKNOWN"}), \
            patch("ai_reasoning_engine.analyze_multi_timeframe_structure", return_value={"structure": "MIXED_ALIGNMENT"}), \
            patch("ai_reasoning_engine.evaluate_execution_quality", return_value={"quality": "WARNING", "warnings": ["execution caution"]}), \
            patch("ai_reasoning_engine.evaluate_setup_quality", return_value={"status": "WARNING", "warnings": ["setup caution"]}), \
            patch("ai_reasoning_engine.score_chart_structure", return_value={"quality": "GOOD", "warnings": []}), \
            patch("ai_reasoning_engine.score_adjustment", return_value=0), \
            patch("ai_reasoning_engine.priority_bonus", return_value=0):
            return build_reasoning_report(
                ticker="TEST",
                setup={"direction": "CALL", "score": 95, "risk_reward": 2.0},
                tech={},
                bot=None,
                trade_type="INTRADAY",
            )

    def test_high_quality_intraday_allows_warning_mtf_execution_and_setup(self):
        report = self._build_report()

        self.assertEqual(report["final_score"], 100)
        self.assertEqual(report["decision"], "A+")
        self.assertTrue(
            any("Mixed multi-timeframe alignment allowed" in warning for warning in report["warnings"])
        )
        self.assertTrue(
            any("Execution warning allowed" in warning for warning in report["warnings"])
        )
        self.assertTrue(
            any("Setup warning allowed" in warning for warning in report["warnings"])
        )

    @patch("bot.MIN_SCORE", 95)
    def test_intraday_override_requires_configured_high_quality_score(self):
        bot = StockTechnicalAIBot.__new__(StockTechnicalAIBot)
        ai = {"verdict": "WAIT", "confidence": 0, "risk_reward": 1.5, "entry_timing": "GOOD"}
        intraday_info = {"confirmations": 3}

        passes, reason = bot.ai_passes_gate(
            ai,
            {"score": 95},
            intraday_info,
            "BREAKOUT",
        )
        self.assertTrue(passes)
        self.assertIn("high-quality intraday", reason)

        passes, reason = bot.ai_passes_gate(
            ai,
            {"score": 94},
            intraday_info,
            "BREAKOUT",
        )
        self.assertFalse(passes)


if __name__ == "__main__":
    unittest.main()
