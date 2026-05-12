import datetime as dt
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config import MARKET_TZ
from bot_technical import StockTechnicalBase


def _trend_bars(closes):
    return [{"open": close, "high": close + 0.1, "low": close - 0.1, "close": close, "volume": 1000} for close in closes]


class IntradayMorningContextTests(unittest.TestCase):
    def test_timeframe_trend_detects_morning_15m_bearish_trend_before_21_bars(self):
        bot = StockTechnicalBase([])
        bars = _trend_bars([100, 99.6, 99.2, 98.8, 98.4, 98.0, 97.6, 97.2])

        self.assertEqual(bot.timeframe_trend(bars), "BEARISH")

    def test_timeframe_trend_detects_morning_15m_bullish_trend_before_21_bars(self):
        bot = StockTechnicalBase([])
        bars = _trend_bars([97.2, 97.6, 98.0, 98.4, 98.8, 99.2, 99.6, 100.0])

        self.assertEqual(bot.timeframe_trend(bars), "BULLISH")

    def test_get_technical_context_uses_intraday_last_5_candles_for_retest_checks(self):
        bot = StockTechnicalBase(["TEST"])
        day = dt.date(2026, 5, 12)
        daily = [
            SimpleNamespace(high=100 + (i * 0.1), low=95 + (i * 0.1), close=98 + (i * 0.1), volume=1_000_000)
            for i in range(220)
        ]
        session_start = dt.datetime.combine(day, dt.time(9, 30), tzinfo=MARKET_TZ)
        minute = []
        for i in range(45):
            close = 100 - (i * 0.05)
            minute.append(
                SimpleNamespace(
                    timestamp=int((session_start + dt.timedelta(minutes=i)).astimezone(dt.timezone.utc).timestamp() * 1000),
                    open=close + 0.03,
                    high=close + 0.08,
                    low=close - 0.08,
                    close=close,
                    volume=10_000 + i,
                )
            )

        with patch.object(bot, "get_latest_trading_day", return_value=day), \
            patch.object(bot, "get_aggs", side_effect=[daily, minute]):
            tech = bot.get_technical_context("TEST")

        expected_closes = [bar.close for bar in minute[-5:]]
        self.assertEqual(tech["last_5_closes"], expected_closes)
        self.assertEqual(tech["last_5_intraday_closes"], expected_closes)
        self.assertNotEqual(tech["last_5_closes"], [bar.close for bar in daily[-5:]])


if __name__ == "__main__":
    unittest.main()
