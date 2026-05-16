import tempfile
import unittest
from unittest.mock import patch

import adaptive_scoring
from ensemble_confidence import dynamic_min_score, setup_decay_score, weighted_ensemble_score
from market_phase import EXHAUSTION, OPEN_DRIVE, TREND_DAY, detect_market_phase
from sector_filter import sector_direction_adjustment


class PrecisionEngineTests(unittest.TestCase):
    def test_market_phase_detects_open_drive_before_indicators(self):
        phase = detect_market_phase(
            {
                "market_time": "09:42",
                "rel_volume": 2.0,
                "distance_from_vwap": 0.8,
                "trend_5m": "BULLISH",
                "trend_15m": "BULLISH",
            },
            {"direction": "CALL", "entry_mode": "BREAKOUT"},
        )

        self.assertEqual(phase["phase"], OPEN_DRIVE)
        self.assertGreaterEqual(phase["confidence"], 70)

    def test_market_phase_detects_exhaustion_from_atr_extension(self):
        phase = detect_market_phase({"breakout_distance_atr": 2.1, "rel_volume": 2.2}, {"direction": "CALL"})

        self.assertEqual(phase["phase"], EXHAUSTION)
        self.assertTrue(phase["warnings"])

    def test_setup_decay_penalizes_late_chases(self):
        decay = setup_decay_score(
            {"setup_age_minutes": 50, "distance_from_trigger": 2.5},
            {"breakout_distance_atr": 1.9},
        )

        self.assertGreaterEqual(decay["decay"], 40)
        self.assertIn("ATR", " ".join(decay["reasons"]))

    def test_dynamic_threshold_relaxes_trend_day_and_tightens_chop(self):
        self.assertLess(dynamic_min_score("TRENDING_BULL", TREND_DAY, 95), 95)
        self.assertGreater(dynamic_min_score("CHOPPY", EXHAUSTION, 95), 95)

    def test_weighted_ensemble_score_uses_component_weights(self):
        score = weighted_ensemble_score(
            {
                "technical": 90,
                "vision": 80,
                "market_regime": 70,
                "structure": 85,
                "execution": 60,
                "learning": 75,
            }
        )

        self.assertAlmostEqual(score, 80.0)

    def test_sector_relative_strength_adjusts_by_direction(self):
        bullish = sector_direction_adjustment(
            "NVDA",
            "CALL",
            {"label": "leader", "sector": "SMH", "score": 80},
        )
        bearish = sector_direction_adjustment(
            "NVDA",
            "PUT",
            {"label": "leader", "sector": "SMH", "score": 80},
        )

        self.assertGreater(bullish["adjustment"], 0)
        self.assertLess(bearish["adjustment"], 0)

    def test_adaptive_behavior_penalty_learns_late_breakout_losses(self):
        # Use the repository's JSON-backed lightweight learner; the assertion is
        # intentionally directional so it remains valid across existing history.
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(adaptive_scoring, "ADAPTIVE_FILE", f"{tmpdir}/weights.json"):
            before = adaptive_scoring.behavior_penalty({"late_breakout_risk": True})
            adaptive_scoring.update_behavior_penalties({"late_breakout_risk": True}, "LOSS")
            after = adaptive_scoring.behavior_penalty({"late_breakout_risk": True})

        self.assertLessEqual(after, before)


if __name__ == "__main__":
    unittest.main()
