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


if __name__ == "__main__":
    unittest.main()
