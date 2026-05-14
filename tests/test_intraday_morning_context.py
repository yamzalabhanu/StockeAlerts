import datetime as dt
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config import MARKET_TZ
from bot_technical import StockTechnicalBase


def _trend_bars(closes):
    return [
        {
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": 1000,
        }
        for close in closes
    ]


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
            SimpleNamespace(
                high=100 + (i * 0.1),
                low=95 + (i * 0.1),
                close=98 + (i * 0.1),
                volume=1_000_000,
            )
            for i in range(220)
        ]
        session_start = dt.datetime.combine(day, dt.time(9, 30), tzinfo=MARKET_TZ)
        minute = []
        for i in range(45):
            close = 100 - (i * 0.05)
            minute.append(
                SimpleNamespace(
                    timestamp=int(
                        (session_start + dt.timedelta(minutes=i))
                        .astimezone(dt.timezone.utc)
                        .timestamp()
                        * 1000
                    ),
                    open=close + 0.03,
                    high=close + 0.08,
                    low=close - 0.08,
                    close=close,
                    volume=10_000 + i,
                )
            )

        with patch.object(
            bot, "get_latest_trading_day", return_value=day
        ), patch.object(bot, "get_aggs", side_effect=[daily, minute]):
            tech = bot.get_technical_context("TEST")

        expected_closes = [bar.close for bar in minute[-5:]]
        self.assertEqual(tech["last_5_closes"], expected_closes)
        self.assertEqual(tech["last_5_intraday_closes"], expected_closes)
        self.assertNotEqual(tech["last_5_closes"], [bar.close for bar in daily[-5:]])
        self.assertEqual(tech["regular_bars_count"], 45)
        self.assertEqual(tech["latest_regular_time"], "10:14")
        self.assertTrue(tech["early_session_setup"])


    def test_get_technical_context_overlays_fresh_realtime_trade_when_minutes_lag(self):
        bot = StockTechnicalBase(["TEST"])
        day = dt.date(2026, 5, 12)
        daily = [
            SimpleNamespace(high=100, low=95, close=98, volume=1_000_000)
            for _ in range(220)
        ]
        session_start = dt.datetime.combine(day, dt.time(9, 30), tzinfo=MARKET_TZ)
        minute = []
        for i in range(30):
            close = 100 + (i * 0.05)
            minute.append(
                SimpleNamespace(
                    timestamp=int(
                        (session_start + dt.timedelta(minutes=i))
                        .astimezone(dt.timezone.utc)
                        .timestamp()
                        * 1000
                    ),
                    open=close - 0.03,
                    high=close + 0.08,
                    low=close - 0.08,
                    close=close,
                    volume=10_000 + i,
                )
            )

        realtime_trade = {
            "price": 104.25,
            "timestamp": dt.datetime.combine(day, dt.time(10, 5), tzinfo=MARKET_TZ),
            "size": 250,
        }

        with patch.object(
            bot, "get_latest_trading_day", return_value=day
        ), patch.object(bot, "get_aggs", side_effect=[daily, minute]), patch.object(
            bot, "get_realtime_stock_trade", return_value=realtime_trade
        ), patch.object(
            bot, "_eligible_realtime_overlay", return_value=True
        ):
            tech = bot.get_technical_context("TEST")

        self.assertEqual(tech["price"], 104.25)
        self.assertTrue(tech["realtime_overlay_active"])
        self.assertEqual(tech["intraday_data_source"], "realtime_trade_overlay")
        self.assertEqual(tech["latest_regular_time"], "09:59")
        self.assertEqual(tech["latest_price_time"], "10:05")
        self.assertEqual(tech["last_5_closes"][-1], 104.25)
        self.assertEqual(tech["recent_high"], 104.25)

    def test_get_technical_context_adds_extended_hours_bias_for_early_session(self):
        bot = StockTechnicalBase(["TEST"])
        day = dt.date(2026, 5, 12)
        previous_day = dt.date(2026, 5, 11)
        daily = [
            SimpleNamespace(high=100, low=95, close=98, volume=1_000_000)
            for _ in range(219)
        ] + [SimpleNamespace(high=101, low=96, close=100, volume=1_000_000)]

        minute = []
        afterhours_start = dt.datetime.combine(
            previous_day, dt.time(16, 0), tzinfo=MARKET_TZ
        )
        for i, close in enumerate([100.5, 101.0, 101.8, 102.2, 102.8, 103.2]):
            minute.append(
                SimpleNamespace(
                    timestamp=int(
                        (afterhours_start + dt.timedelta(minutes=i))
                        .astimezone(dt.timezone.utc)
                        .timestamp()
                        * 1000
                    ),
                    open=close - 0.1,
                    high=close + 0.2,
                    low=close - 0.2,
                    close=close,
                    volume=30_000,
                )
            )

        premarket_start = dt.datetime.combine(day, dt.time(8, 0), tzinfo=MARKET_TZ)
        for i, close in enumerate([103.5, 104.0, 104.5, 105.0, 105.2]):
            minute.append(
                SimpleNamespace(
                    timestamp=int(
                        (premarket_start + dt.timedelta(minutes=i))
                        .astimezone(dt.timezone.utc)
                        .timestamp()
                        * 1000
                    ),
                    open=close - 0.1,
                    high=close + 0.2,
                    low=close - 0.2,
                    close=close,
                    volume=25_000,
                )
            )

        session_start = dt.datetime.combine(day, dt.time(9, 30), tzinfo=MARKET_TZ)
        for i, close in enumerate([105.4, 105.7, 106.0, 106.2, 106.4, 106.6]):
            minute.append(
                SimpleNamespace(
                    timestamp=int(
                        (session_start + dt.timedelta(minutes=i))
                        .astimezone(dt.timezone.utc)
                        .timestamp()
                        * 1000
                    ),
                    open=close - 0.05,
                    high=close + 0.1,
                    low=close - 0.1,
                    close=close,
                    volume=40_000,
                )
            )

        with patch.object(
            bot, "get_latest_trading_day", return_value=day
        ), patch.object(bot, "get_aggs", side_effect=[daily, minute]):
            tech = bot.get_technical_context("TEST")

        self.assertEqual(tech["extended_bias"], "BULLISH")
        self.assertGreater(tech["extended_bias_score"], 0)
        self.assertEqual(tech["afterhours_volume"], 180_000)
        self.assertEqual(tech["premarket_volume"], 125_000)
        self.assertGreater(tech["extended_hours_change_pct"], 0)
        self.assertIn("extended move", tech["extended_bias_reason"])

    def test_extended_hours_bias_rewards_matching_setup_and_penalizes_conflict(self):
        bot = StockTechnicalBase([])
        base_tech = {
            "ticker": "TEST",
            "price": 106,
            "vwap": 105,
            "ema9": 105.5,
            "ema21": 105,
            "ema50": 104,
            "dma20": 100,
            "dma50": 99,
            "dma200": 98,
            "trend_5m": "BULLISH",
            "trend_15m": "BULLISH",
            "prev_high": 101,
            "prev_low": 96,
            "premarket_high": 105,
            "premarket_low": 99,
            "recent_high": 106.5,
            "recent_low": 104,
            "orb_high": 105.5,
            "orb_low": 104,
            "current_volume": 200_000,
            "avg_20_volume": 100_000,
            "last_5_closes": [105, 105.3, 105.6, 105.8, 106],
            "last_5_highs": [105.2, 105.5, 105.8, 106, 106.2],
            "last_5_lows": [104.8, 105.1, 105.4, 105.6, 105.8],
            "extended_bias": "BULLISH",
            "extended_bias_score": 4,
            "extended_bias_reason": "gap/extended move +2.00%; extended EMA alignment bullish",
        }

        with patch.object(
            bot,
            "get_market_bias",
            return_value={
                "bias": "NEUTRAL",
                "details": [],
                "bullish_count": 0,
                "bearish_count": 0,
            },
        ), patch.object(
            bot,
            "get_sector_confirmation",
            return_value=("NO_SECTOR_ETF", "no sector ETF mapping"),
        ), patch.object(
            bot, "relative_strength_vs_spy", return_value="NEUTRAL"
        ), patch.object(
            bot, "get_market_regime", return_value="MIXED"
        ):
            bullish = bot.score_call_setup(dict(base_tech))
            conflicted = bot.score_put_setup(dict(base_tech))

        self.assertTrue(
            any(
                "extended-hours bias bullish" in reason for reason in bullish["reasons"]
            )
        )
        self.assertTrue(
            any(
                "extended-hours bias against PUTs" in reason
                for reason in conflicted["reasons"]
            )
        )


if __name__ == "__main__":
    unittest.main()
