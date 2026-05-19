import datetime as dt
import json
import unittest
from unittest.mock import patch

import requests

import bot_technical
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

    def test_realtime_trade_auth_failure_disables_overlay_for_run_without_key_leak(self):
        bot = StockTechnicalBase(["SPY"])
        bot_technical._realtime_stock_lookup_disabled_reason = None

        try:
            with patch.object(bot_technical, "POLYGON_API_KEY", "secret-key"), patch.object(
                bot_technical, "REALTIME_STOCK_OVERLAY_ENABLED", True
            ), patch.object(
                bot_technical, "REALTIME_STOCK_OVERLAY_SKIP_UNAUTHORIZED", True
            ), patch.object(
                bot,
                "_request_polygon_json",
                side_effect=Exception(
                    "403 Client Error: Forbidden for url: "
                    "https://api.polygon.io/v2/last/trade/SPY?apiKey=secret-key"
                ),
            ) as request, patch("builtins.print") as printed:
                self.assertIsNone(bot.get_realtime_stock_trade("SPY"))
                self.assertIsNone(bot.get_realtime_stock_trade("QQQ"))

            self.assertEqual(request.call_count, 1)
            printed.assert_called_once()
            message = printed.call_args.args[0]
            self.assertIn("Realtime stock trade overlay disabled for this run", message)
            self.assertNotIn("secret-key", message)
            self.assertNotIn("apiKey=", message)
        finally:
            bot_technical._realtime_stock_lookup_disabled_reason = None


    def test_polygon_json_retries_timeout_then_succeeds(self):
        bot = StockTechnicalBase(["SPY"])

        timeout = requests.exceptions.Timeout("timed out")
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"ok": True}

        with patch("bot_technical.requests.get", side_effect=[timeout, response]) as get, patch(
            "bot_technical.time.sleep"
        ) as sleeper:
            payload = bot._request_polygon_json("https://api.polygon.io/test", params={})

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(get.call_count, 2)
        sleeper.assert_called_once()

    def test_polygon_json_raises_after_json_decode_retries(self):
        bot = StockTechnicalBase(["SPY"])

        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = json.JSONDecodeError("bad json", "{}", 1)

        with patch("bot_technical.requests.get", return_value=response) as get, patch(
            "bot_technical.time.sleep"
        ) as sleeper:
            with self.assertRaises(json.JSONDecodeError):
                bot._request_polygon_json("https://api.polygon.io/test", params={})

        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleeper.call_count, 2)

    def test_realtime_trade_non_auth_error_redacts_api_key_but_does_not_disable(self):
        bot = StockTechnicalBase(["SPY"])
        bot_technical._realtime_stock_lookup_disabled_reason = None

        try:
            with patch.object(bot_technical, "POLYGON_API_KEY", "secret-key"), patch.object(
                bot_technical, "REALTIME_STOCK_OVERLAY_ENABLED", True
            ), patch.object(
                bot,
                "_request_polygon_json",
                side_effect=RuntimeError(
                    "500 Server Error for url: "
                    "https://api.polygon.io/v2/last/trade/SPY?apiKey=secret-key"
                ),
            ), patch("builtins.print") as printed:
                self.assertIsNone(bot.get_realtime_stock_trade("SPY"))

            printed.assert_called_once()
            message = printed.call_args.args[0]
            self.assertIn("SPY: realtime trade lookup skipped", message)
            self.assertIn("apiKey=<redacted>", message)
            self.assertNotIn("secret-key", message)
            self.assertIsNone(bot_technical._realtime_stock_lookup_disabled_reason)
        finally:
            bot_technical._realtime_stock_lookup_disabled_reason = None


if __name__ == "__main__":
    unittest.main()
