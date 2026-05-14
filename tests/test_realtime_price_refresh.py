import datetime as dt
import unittest
from unittest.mock import patch

from config import MARKET_TZ
from bot import StockTechnicalAIBot
from bot_technical import StockTechnicalBase


class _FixedDateTime(dt.datetime):
    fixed_now = None

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.fixed_now.replace(tzinfo=None)
        return cls.fixed_now.astimezone(tz)


class RealtimePriceRefreshTests(unittest.TestCase):
    def test_overlay_accepts_fresh_trade_in_same_minute_by_default(self):
        bot = StockTechnicalBase(["TEST"])
        day = dt.date(2026, 5, 12)
        _FixedDateTime.fixed_now = dt.datetime.combine(
            day, dt.time(10, 19, 30), tzinfo=MARKET_TZ
        )
        latest_regular_ts = dt.datetime.combine(
            day, dt.time(10, 19), tzinfo=MARKET_TZ
        )
        trade = {
            "price": 55.54,
            "timestamp": dt.datetime.combine(day, dt.time(10, 19, 20), tzinfo=MARKET_TZ),
        }

        with patch("bot_technical.dt.datetime", _FixedDateTime):
            self.assertTrue(bot._eligible_realtime_overlay(trade, latest_regular_ts))

    def test_alert_refresh_replaces_stale_display_price_with_fresh_trade(self):
        bot = StockTechnicalAIBot(["SLB"])
        day = dt.date(2026, 5, 12)
        _FixedDateTime.fixed_now = dt.datetime.combine(
            day, dt.time(10, 19, 30), tzinfo=MARKET_TZ
        )
        tech = {
            "price": 55.85,
            "latest_price_time": "10:18",
            "intraday_data_source": "minute_aggregate",
            "intraday_data_delay_sec": 90,
            "realtime_overlay_active": False,
        }
        trade = {
            "price": 55.54,
            "timestamp": dt.datetime.combine(day, dt.time(10, 19, 20), tzinfo=MARKET_TZ),
            "size": 100,
        }

        with patch("bot.dt.datetime", _FixedDateTime), patch.object(
            bot, "get_realtime_stock_trade", return_value=trade
        ):
            refreshed = bot.refresh_alert_price("SLB", tech)

        self.assertEqual(refreshed["price"], 55.54)
        self.assertEqual(refreshed["latest_price_time"], "10:19")
        self.assertEqual(refreshed["intraday_data_source"], "realtime_trade_alert_refresh")
        self.assertTrue(refreshed["realtime_overlay_active"])
        self.assertEqual(refreshed["intraday_data_delay_sec"], 10)


if __name__ == "__main__":
    unittest.main()
