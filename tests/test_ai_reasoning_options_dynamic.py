import unittest
from unittest.mock import patch

from ai_reasoning_engine import build_reasoning_report


class DynamicOptionsReasoningTests(unittest.TestCase):
    def test_reasoning_includes_ticker_adaptive_technical_and_options_thesis(self):
        setup = {
            "direction": "CALL",
            "score": 82,
            "risk_reward": 2.1,
            "entry": 101.5,
            "target": 106.0,
            "stop": 99.5,
            "options_flow": {
                "status": "OK",
                "bias": "BULLISH",
                "score": 82,
                "dealer_gamma_state": "SHORT_GAMMA",
                "gamma_squeeze": True,
                "signals": [
                    {"name": "delta_imbalance", "direction": "BULLISH"},
                    {"name": "gamma_squeeze_conditions", "direction": "BULLISH"},
                ],
            },
            "option_contract": {
                "status": "OK",
                "contract_symbol": "O:TEST260619C00105000",
                "spread_pct": 6.5,
                "volume": 1250,
                "open_interest": 3400,
                "recommendation_score": 88,
                "delta": 0.48,
                "dte": 32,
                "implied_volatility": 0.62,
            },
        }
        tech = {
            "price": 101.5,
            "ema9": 100.8,
            "ema21": 99.9,
            "ema50": 98.7,
            "vwap": 100.2,
            "orb_high": 101.0,
            "relative_volume": 2.4,
            "atr_extension": 0.7,
        }

        with patch("ai_reasoning_engine.detect_market_regime", return_value={"regime": "TRENDING_BULL", "confidence": 75}), \
            patch("ai_reasoning_engine.analyze_multi_timeframe_structure", return_value={"structure": "GOOD_ALIGNMENT", "aligned_timeframes": 2}), \
            patch("ai_reasoning_engine.evaluate_execution_quality", return_value={"quality": "GOOD", "strengths": ["tight spread", "strong tape"]}), \
            patch("ai_reasoning_engine.evaluate_setup_quality", return_value={"status": "PASS", "reasons": ["clean breakout"]}), \
            patch("ai_reasoning_engine.score_chart_structure", return_value={"quality": "GOOD", "warnings": []}), \
            patch("ai_reasoning_engine.score_adjustment", return_value=0), \
            patch("ai_reasoning_engine.priority_bonus", return_value=0):
            report = build_reasoning_report("TEST", setup, tech, bot=None, trade_type="INTRADAY")

        narrative = report["narrative"]
        self.assertIn("Take-trade thesis", narrative)
        self.assertIn("Ticker-adaptive technical read", narrative)
        self.assertIn("Options analysis", narrative)
        self.assertIn("Options confirmation", narrative)
        self.assertIn("price 101.50 is stacked above fast/mid EMAs", narrative)
        self.assertIn("Options flow confirms CALL bias", narrative)
        self.assertGreater(report["options_analysis"]["score_adjustment"], 0)
        self.assertTrue(any("Options analysis adjusted score" in reason for reason in report["reasons"]))

    def test_reasoning_starts_with_human_readable_trade_summary(self):
        setup = {
            "direction": "PUT",
            "score": 88,
            "risk_reward": 2.67,
            "options_flow": {"status": "OK", "bias": "BULLISH", "score": 28},
            "option_contract": {"status": "SKIP", "reason": "No option passed filters"},
        }

        with patch("ai_reasoning_engine.detect_market_regime", return_value={"regime": "TRENDING_BEAR", "confidence": 85}), \
            patch("ai_reasoning_engine.analyze_multi_timeframe_structure", return_value={"structure": "GOOD_ALIGNMENT", "aligned_timeframes": 3}), \
            patch("ai_reasoning_engine.evaluate_execution_quality", return_value={"quality": "WARNING", "warnings": ["Weak candle body"]}), \
            patch("ai_reasoning_engine.evaluate_setup_quality", return_value={"status": "REJECT", "warnings": ["Breakout directly into resistance"]}), \
            patch("ai_reasoning_engine.score_chart_structure", return_value={"quality": "ELITE", "warnings": []}), \
            patch("ai_reasoning_engine.score_adjustment", return_value=0), \
            patch("ai_reasoning_engine.priority_bonus", return_value=0):
            report = build_reasoning_report("ARKF", setup, {}, bot=None, trade_type="SWING")

        narrative = report["narrative"]
        self.assertTrue(narrative.startswith("Best human-readable conclusion"))
        self.assertIn("This is a bearish ARKF put idea with strong technical alignment", narrative)
        self.assertIn("Practical interpretation", narrative)
        self.assertIn("Bias: Bearish", narrative)
        self.assertIn("Chart quality: Very strong", narrative)
        self.assertIn("Market support: Strong", narrative)
        self.assertIn("Options confirmation: Weak/conflicting", narrative)
        self.assertIn("Entry quality: Not ideal", narrative)
        self.assertIn("Best action: Wait for cleaner confirmation or a better option contract", narrative)
        self.assertIn("One-sentence summary", narrative)
        self.assertIn("Detailed model diagnostics", narrative)

    def test_options_conflict_adds_warning_and_negative_adjustment(self):
        setup = {
            "direction": "CALL",
            "score": 82,
            "risk_reward": 2.0,
            "options_flow": {"status": "OK", "bias": "BEARISH", "score": 78},
            "option_contract": {"status": "OK", "spread_pct": 20, "volume": 10, "open_interest": 20, "recommendation_score": 40},
        }

        with patch("ai_reasoning_engine.detect_market_regime", return_value={"regime": "UNKNOWN"}), \
            patch("ai_reasoning_engine.analyze_multi_timeframe_structure", return_value={"structure": "GOOD_ALIGNMENT"}), \
            patch("ai_reasoning_engine.evaluate_execution_quality", return_value={"quality": "GOOD", "strengths": []}), \
            patch("ai_reasoning_engine.evaluate_setup_quality", return_value={"status": "PASS", "reasons": []}), \
            patch("ai_reasoning_engine.score_chart_structure", return_value={"quality": "GOOD", "warnings": []}), \
            patch("ai_reasoning_engine.score_adjustment", return_value=0), \
            patch("ai_reasoning_engine.priority_bonus", return_value=0):
            report = build_reasoning_report("TEST", setup, {}, bot=None, trade_type="INTRADAY")

        self.assertLess(report["options_analysis"]["score_adjustment"], 0)
        self.assertTrue(any("Options flow conflicts" in warning for warning in report["warnings"]))
        self.assertIn("Options cautions", report["narrative"])


if __name__ == "__main__":
    unittest.main()
