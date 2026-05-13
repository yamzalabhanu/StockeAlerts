import unittest
from unittest.mock import patch

from ai_reasoning_engine import build_reasoning_report
from execution_quality import evaluate_execution_quality
from setup_filters import evaluate_setup_quality


class EarlySessionGraceTests(unittest.TestCase):
    def test_execution_and_setup_filters_warn_instead_of_rejecting_early_session(self):
        tech = {
            "early_session_setup": True,
            "rel_volume": 0.5,
            "candle_body_pct": 20,
            "distance_from_vwap": 0.5,
        }

        execution = evaluate_execution_quality(tech)
        setup = evaluate_setup_quality(tech, "CALL")

        self.assertEqual(execution["quality"], "WARNING")
        self.assertIn("Early-session liquidity data still forming", execution["warnings"])
        self.assertEqual(setup["status"], "WARNING")
        self.assertIn("Early-session setup structure still forming", setup["warnings"])

    def test_reasoning_allows_early_session_liquidity_and_setup_rejects_for_buffered_score(self):
        with patch("ai_reasoning_engine.detect_market_regime", return_value={"regime": "UNKNOWN"}), \
            patch("ai_reasoning_engine.analyze_multi_timeframe_structure", return_value={"structure": "GOOD_ALIGNMENT"}), \
            patch("ai_reasoning_engine.evaluate_execution_quality", return_value={"quality": "BAD", "warnings": ["wide spread"]}), \
            patch("ai_reasoning_engine.evaluate_setup_quality", return_value={"status": "REJECT", "warnings": ["weak retest"]}), \
            patch("ai_reasoning_engine.score_chart_structure", return_value={"quality": "GOOD", "warnings": []}), \
            patch("ai_reasoning_engine.score_adjustment", return_value=0), \
            patch("ai_reasoning_engine.priority_bonus", return_value=0), \
            patch("ai_reasoning_engine.MIN_SCORE", 95), \
            patch("ai_reasoning_engine.EARLY_SESSION_MIN_SCORE_BUFFER", 10):
            report = build_reasoning_report(
                ticker="TEST",
                setup={"direction": "CALL", "score": 85, "risk_reward": 2.0, "early_session_setup": True},
                tech={"early_session_setup": True},
                bot=None,
                trade_type="INTRADAY",
            )

        self.assertNotIn("Poor liquidity/execution quality", report["reject_reasons"])
        self.assertNotIn("Setup failed elite quality filters", report["reject_reasons"])
        self.assertTrue(any("Early-session liquidity warning allowed" in w for w in report["warnings"]))
        self.assertTrue(any("Early-session setup warning allowed" in w for w in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
