import datetime as dt
import unittest
from types import SimpleNamespace

from bot_technical import StockTechnicalBase
from swing_scanner import score_swing_setup


class DailySwingContextTests(unittest.TestCase):
    def _daily_bars(self, count=220):
        bars = []
        base_day = dt.date(2025, 1, 1)
        for i in range(count):
            close = 100 + i * 0.5
            bars.append(
                SimpleNamespace(
                    close=close,
                    high=close + 1,
                    low=close - 1,
                    volume=1_000_000 + i * 1_000,
                    timestamp=int(dt.datetime.combine(base_day, dt.time()).timestamp() * 1000),
                )
            )
        return bars

    def test_daily_context_has_swing_indicator_inputs_without_intraday_bars(self):
        bot = StockTechnicalBase(["TEST"])
        context = bot.build_daily_technical_context(
            "TEST",
            self._daily_bars(),
            dt.date(2025, 12, 31),
        )

        self.assertFalse(context["intraday_available"])
        self.assertEqual(len(context["daily_closes"]), 220)
        self.assertEqual(len(context["last_60_closes"]), 60)
        self.assertEqual(context["daily_trend"], "BULLISH")
        self.assertIsNotNone(context["rel_volume"])

    def test_daily_context_can_generate_swing_setup(self):
        bot = StockTechnicalBase(["TEST"])
        context = bot.build_daily_technical_context(
            "TEST",
            self._daily_bars(),
            dt.date(2025, 12, 31),
        )

        setup = score_swing_setup(context)

        self.assertIsNotNone(setup)
        self.assertEqual(setup["direction"], "CALL")
        self.assertGreaterEqual(setup["score"], 85)


if __name__ == "__main__":
    unittest.main()
