import unittest

from trade_management_ai import EXIT, HOLD, SCALE, TRIM, analyze_exit_conditions
from price_projection import predict_2day_move


class TradeManagementAITests(unittest.TestCase):
    def test_scales_winner_when_continuation_volume_regime_and_projection_align(self):
        decision = analyze_exit_conditions(
            {
                "direction": "CALL",
                "unrealized_rr": 1.2,
                "entry_projection_confidence": 78,
            },
            {
                "adx": 31,
                "trend_strength": 84,
                "momentum_slope": 0.9,
                "rel_volume": 2.3,
                "volume_trend": "expanding",
                "projection_direction": "BULLISH",
                "projection_confidence": 82,
                "rsi": 64,
                "distance_from_vwap": 1.1,
                "candle_body_pct": 62,
            },
            {"regime": "TRENDING_BULL"},
        )

        self.assertEqual(decision["action"], SCALE)
        self.assertGreaterEqual(decision["scores"]["trend_continuation"], 75)
        self.assertLess(decision["scores"]["projection_decay"], 30)

    def test_trims_when_volume_fades_and_exhaustion_builds(self):
        decision = analyze_exit_conditions(
            {
                "direction": "LONG",
                "unrealized_rr": 2.2,
                "max_unrealized_rr": 2.6,
                "entry_projection_confidence": 80,
            },
            {
                "adx": 24,
                "trend_strength": 58,
                "momentum_slope": 0.1,
                "rel_volume": 0.55,
                "volume_trend": "falling",
                "projection_direction": "BULLISH",
                "projection_confidence": 58,
                "rsi": 72,
                "distance_from_vwap": 3.5,
                "candle_body_pct": 24,
            },
            {"regime": "TRENDING_BULL"},
        )

        self.assertEqual(decision["action"], TRIM)
        self.assertGreaterEqual(decision["scores"]["exhaustion"], 45)
        self.assertTrue(decision["warnings"])

    def test_exits_when_projection_flips_and_regime_conflicts(self):
        decision = analyze_exit_conditions(
            {
                "direction": "CALL",
                "unrealized_rr": 0.4,
                "entry_projection_confidence": 82,
            },
            {
                "adx": 26,
                "trend_strength": 44,
                "momentum_slope": -0.8,
                "rel_volume": 1.1,
                "projection_direction": "BEARISH",
                "projection_confidence": 48,
                "rsi": 49,
            },
            {"regime": "TRENDING_BEAR"},
        )

        self.assertEqual(decision["action"], EXIT)
        self.assertGreaterEqual(decision["scores"]["projection_decay"], 45)

    def test_holds_when_edge_is_still_intact_without_scale_rr(self):
        decision = analyze_exit_conditions(
            {"direction": "PUT", "unrealized_rr": 0.3},
            {
                "adx": 27,
                "trend_strength": 72,
                "momentum_slope": -0.3,
                "rel_volume": 1.6,
                "projection_direction": "BEARISH",
                "projection_confidence": 70,
                "rsi": 42,
            },
            {"regime": "TRENDING_BEAR"},
        )

        self.assertEqual(decision["action"], HOLD)

    def test_projection_reports_decay_when_confidence_drops_or_direction_flips(self):
        projection = predict_2day_move(
            {
                "price": 100,
                "atr14": 2,
                "rsi": 40,
                "adx": 28,
                "rel_volume": 1.8,
            },
            {
                "regime": {"regime": "TRENDING_BEAR"},
                "previous_projection": {"direction": "BULLISH", "confidence": 90},
            },
        )

        self.assertEqual(projection["direction"], "BEARISH")
        self.assertTrue(projection["direction_flip"])
        self.assertGreaterEqual(projection["projection_decay"], 65)


if __name__ == "__main__":
    unittest.main()
