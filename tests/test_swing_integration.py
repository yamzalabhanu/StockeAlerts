import unittest
from unittest.mock import patch

from swing_integration import (
    _hold_days_to_horizon_minutes,
    meets_swing_benchmark,
    process_swing_candidate,
    swing_benchmark_reject_reasons,
)


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
            "score": 100,
            "entry": 100,
            "stop": 95,
            "target": 120,
            "risk_reward": 4,
            "hold_days": "2-10",
            "reasons": ["test reason"],
        }

    def _reasoning(self):
        return {
            "decision": "A+",
            "final_score": 100,
            "reject_reasons": [],
            "regime": {"regime": "TRENDING_BULL"},
            "execution": {"quality": "GOOD"},
            "setup_quality": {"status": "PASS"},
            "vision": {"quality": "ELITE"},
            "mtf": {"structure": "STRONG_ALIGNMENT"},
            "learning_context": {"alert_type": "SWING", "entry_mode": "SWING", "direction": "CALL"},
        }

    def test_process_swing_candidate_only_returns_when_telegram_send_succeeds(self):
        class Bot:
            def send_telegram_msg(self, _message):
                return False

        with patch("swing_integration.score_swing_setup", return_value=self._setup()), \
            patch("swing_integration.build_reasoning_report", return_value=self._reasoning()), \
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
            patch("swing_integration.build_reasoning_report", return_value=self._reasoning()), \
            patch("swing_integration.log_swing_alert"), \
            patch("swing_integration.track_outcome"):
            result = process_swing_candidate(Bot(), "TEST", {})

        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "CALL")


    def test_process_swing_candidate_uses_entry_for_option_contract_price(self):
        class Bot:
            def send_telegram_msg(self, _message):
                return True

        class OptionContract:
            status = "SKIP"
            recommendation_score = 0

        with patch("swing_integration.score_swing_setup", return_value=self._setup()), \
            patch("swing_integration.build_reasoning_report", return_value=self._reasoning()), \
            patch("swing_integration.analyze_options_flow") as analyze_options_flow, \
            patch("swing_integration.options_flow_to_dict", return_value={}), \
            patch("swing_integration.select_option_contract", return_value=OptionContract()) as select_option_contract, \
            patch("swing_integration.option_to_dict", return_value={"status": "SKIP"}), \
            patch("swing_integration.log_swing_alert"), \
            patch("swing_integration.track_outcome"), \
            patch.dict("swing_integration.SWING_ALERT_CACHE", {}, clear=True):
            analyze_options_flow.return_value.status = "SKIP"
            analyze_options_flow.return_value.bias = "NEUTRAL"
            process_swing_candidate(Bot(), "TEST", {})

        select_option_contract.assert_called_once_with(
            "TEST",
            {"signal": "CALL", "price": 100},
        )

    def test_swing_benchmark_allows_elite_quality_filter_ai_reject_risk(self):
        reasoning = self._reasoning()
        reasoning["reject_reasons"] = ["Setup failed elite quality filters"]
        reasoning["setup_quality"]["status"] = "REJECT"

        self.assertTrue(meets_swing_benchmark(self._setup(), reasoning))

    def test_swing_benchmark_still_rejects_blocking_ai_reject_risks(self):
        reasoning = self._reasoning()
        reasoning["reject_reasons"] = ["Poor liquidity/execution quality"]

        self.assertFalse(meets_swing_benchmark(self._setup(), reasoning))

    def test_swing_benchmark_accepts_elite_directional_criteria(self):
        for direction in ("CALL", "PUT"):
            setup = self._setup()
            setup["direction"] = direction
            reasoning = self._reasoning()
            reasoning["learning_context"]["direction"] = direction
            reasoning["regime"]["regime"] = "TRENDING_BULL" if direction == "CALL" else "TRENDING_BEAR"

            self.assertTrue(meets_swing_benchmark(setup, reasoning))

    def test_swing_benchmark_accepts_a_plus_scores_above_threshold(self):
        reasoning = self._reasoning()
        reasoning["final_score"] = 92

        self.assertTrue(meets_swing_benchmark(self._setup(), reasoning))

    def test_swing_benchmark_accepts_high_quality_a_setup(self):
        setup = self._setup()
        setup["risk_reward"] = 1.8
        reasoning = self._reasoning()
        reasoning["decision"] = "A"
        reasoning["final_score"] = 88
        reasoning["mtf"]["structure"] = "GOOD_ALIGNMENT"
        reasoning["vision"]["quality"] = "GOOD"

        self.assertTrue(meets_swing_benchmark(setup, reasoning))

    def test_swing_benchmark_reject_reasons_explain_missing_criteria(self):
        reasoning = self._reasoning()
        reasoning["final_score"] = 86
        reasoning["execution"]["quality"] = "BAD"

        reasons = swing_benchmark_reject_reasons(self._setup(), reasoning)

        self.assertTrue(any("score 86" in reason for reason in reasons))
        self.assertTrue(any("execution BAD" in reason for reason in reasons))

    def test_swing_benchmark_rejects_near_miss_criteria(self):
        near_misses = (
            ("final_score", 87),
            ("regime.regime", "TRENDING_BEAR"),
            ("mtf.structure", "MIXED_ALIGNMENT"),
            ("execution.quality", "BAD"),
            ("vision.quality", "NEUTRAL"),
        )

        for path, value in near_misses:
            with self.subTest(path=path):
                reasoning = self._reasoning()
                target = reasoning
                keys = path.split(".")
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value

                self.assertFalse(meets_swing_benchmark(self._setup(), reasoning))


if __name__ == "__main__":
    unittest.main()
