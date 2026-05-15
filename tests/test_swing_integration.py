import unittest
from unittest.mock import patch

import alert_history

from swing_integration import (
    _hold_days_to_horizon_minutes,
    meets_swing_benchmark,
    process_swing_candidate,
    send_prepared_swing_candidate,
    swing_benchmark_reject_reasons,
    swing_ranking_score,
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
    def setUp(self):
        alert_history._ALERTED_TICKERS_BY_DAY.clear()
        alert_history._LOADED_LOG_DAYS.add(alert_history.alert_day())

    def tearDown(self):
        alert_history._ALERTED_TICKERS_BY_DAY.clear()
        alert_history._LOADED_LOG_DAYS.clear()

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

    def test_process_swing_candidate_can_defer_telegram_until_ranked_scan_selection(self):
        class Bot:
            def send_telegram_msg(self, _message):
                raise AssertionError("deferred swing candidate should not send immediately")

        with patch("swing_integration.score_swing_setup", return_value=self._setup()), \
            patch("swing_integration.build_reasoning_report", return_value=self._reasoning()), \
            patch("swing_integration.log_swing_alert") as log_swing_alert, \
            patch("swing_integration.track_outcome") as track_outcome:
            result = process_swing_candidate(Bot(), "TEST", {}, send_alert=False)

        self.assertIsNotNone(result)
        self.assertIn("ranking_score", result)
        log_swing_alert.assert_not_called()
        track_outcome.assert_not_called()

    def test_send_prepared_swing_candidate_finalizes_deferred_alert(self):
        class Bot:
            def send_telegram_msg(self, _message):
                return True

        setup = self._setup()
        setup["ai_reasoning"] = self._reasoning()

        with patch("swing_integration.log_swing_alert") as log_swing_alert, \
            patch("swing_integration.track_outcome") as track_outcome, \
            patch.dict("swing_integration.SWING_ALERT_CACHE", {}, clear=True):
            sent = send_prepared_swing_candidate(Bot(), "TEST", setup, {}, alert_time=123)

        self.assertTrue(sent)
        log_swing_alert.assert_called_once()
        track_outcome.assert_called_once()

    def test_swing_ranking_prefers_better_quality_setups(self):
        lower = self._setup()
        lower.update({"score": 88, "risk_reward": 1.8, "decision": "A"})
        lower["ai_reasoning"] = {"vision": {"quality": "GOOD"}, "mtf": {"structure": "GOOD_ALIGNMENT"}}

        higher = self._setup()
        higher["ai_reasoning"] = self._reasoning()

        self.assertGreater(swing_ranking_score(higher), swing_ranking_score(lower))

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
            min_dte=7,
            max_dte=14,
            allow_default_fallback=False,
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

    def test_swing_benchmark_accepts_elite_a_plus_call_in_mixed_regime(self):
        reasoning = self._reasoning()
        reasoning["regime"]["regime"] = "MIXED"

        self.assertTrue(meets_swing_benchmark(self._setup(), reasoning))

    def test_swing_benchmark_rejects_non_elite_a_plus_call_in_mixed_regime(self):
        reasoning = self._reasoning()
        reasoning["final_score"] = 99
        reasoning["regime"]["regime"] = "MIXED"

        self.assertFalse(meets_swing_benchmark(self._setup(), reasoning))

    def test_swing_benchmark_accepts_elite_mixed_mtf_with_momentum_confirmation(self):
        setup = self._setup()
        setup["reasons"] = [
            "base breakout through pivot resistance",
            "breakout retest held",
        ]
        reasoning = self._reasoning()
        reasoning["final_score"] = 95
        reasoning["mtf"]["structure"] = "MIXED_ALIGNMENT"
        tech = {"adx": 23, "rel_volume": 1.9}

        self.assertTrue(meets_swing_benchmark(setup, reasoning, tech))

    def test_swing_benchmark_mixed_mtf_override_requires_momentum_confirmation(self):
        reasoning = self._reasoning()
        reasoning["final_score"] = 95
        reasoning["mtf"]["structure"] = "MIXED_ALIGNMENT"
        tech = {"adx": 22, "rel_volume": 1.9, "candle_body_pct": 65}

        self.assertFalse(meets_swing_benchmark(self._setup(), reasoning, tech))

    def test_swing_benchmark_accepts_elite_mixed_mtf_with_strong_candle_body(self):
        reasoning = self._reasoning()
        reasoning["final_score"] = 95
        reasoning["mtf"]["structure"] = "MIXED_ALIGNMENT"
        tech = {"adx": 23, "rel_volume": 1.9, "candle_body_pct": 65}

        self.assertTrue(meets_swing_benchmark(self._setup(), reasoning, tech))

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
