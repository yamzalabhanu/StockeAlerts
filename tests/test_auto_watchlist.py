import datetime as dt
import unittest
from unittest.mock import patch

import bot_technical
from bot_technical import StockTechnicalBase


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class AutoWatchlistTests(unittest.TestCase):
    def test_historical_watchlist_uses_active_tickers_and_grouped_daily_aggs(self):
        bot = StockTechnicalBase(["BASE"])
        responses = [
            _Response(
                {
                    "results": [
                        {"ticker": "AAA"},
                        {"ticker": "BBB"},
                        {"ticker": "CCC"},
                    ]
                }
            ),
            _Response(
                {
                    "results": [
                        {"T": "AAA", "o": 10, "c": 11, "h": 11.25, "v": 3_000_000},
                        {"T": "BBB", "o": 20, "c": 20.10, "h": 20.50, "v": 5_000_000},
                        {"T": "CCC", "o": 6, "c": 7, "h": 7.10, "v": 8_000_000},
                        {"T": "ZZZ", "o": 30, "c": 35, "h": 36, "v": 9_000_000},
                    ]
                }
            ),
        ]

        with patch.object(bot_technical, "MIN_AUTO_VOLUME", 2_000_000), patch.object(
            bot_technical, "MIN_AUTO_CHANGE_PCT", 2.0
        ), patch.object(bot_technical, "MIN_STOCK_PRICE", 8), patch.object(
            bot_technical, "AUTO_WATCHLIST_LIMIT", 10
        ), patch.object(
            bot_technical.requests, "get", side_effect=responses
        ) as get:
            watchlist = bot.get_auto_watchlist(dt.date(2025, 1, 15))

        self.assertEqual(watchlist, ["BASE", "AAA"])
        self.assertIn("AAA", bot.state)
        self.assertEqual(
            get.call_args_list[0].kwargs["params"]["date"],
            "2025-01-15",
        )
        self.assertIn(
            "/v2/aggs/grouped/locale/us/market/stocks/2025-01-15",
            get.call_args_list[1].args[0],
        )

    def test_watchlist_adds_extended_hours_and_previous_day_options_activity(self):
        bot = StockTechnicalBase(["BASE"])
        premarket_ts = int(
            dt.datetime(2025, 1, 15, 8, 0, tzinfo=bot_technical.MARKET_TZ).timestamp()
            * 1000
        )
        responses = [
            _Response({"results": [{"ticker": "AAA"}]}),
            _Response(
                {
                    "results": [
                        {"T": "AAA", "o": 10, "c": 10.05, "h": 10.10, "v": 100_000}
                    ]
                }
            ),
            _Response({"results": [{"T": "AAA", "c": 10}]}),
            _Response({"results": [{"t": premarket_ts, "c": 10.50, "v": 650_000}]}),
            _Response(
                {
                    "results": [
                        {
                            "day": {"volume": 800},
                            "open_interest": 4_000,
                        }
                    ]
                }
            ),
            _Response(
                {
                    "results": [
                        {
                            "day": {"volume": 700},
                            "open_interest": 3_000,
                        }
                    ]
                }
            ),
        ]

        with patch.object(bot_technical, "MIN_AUTO_VOLUME", 2_000_000), patch.object(
            bot_technical, "MIN_AUTO_CHANGE_PCT", 2.0
        ), patch.object(
            bot_technical, "MIN_EXTENDED_HOURS_VOLUME", 500_000
        ), patch.object(
            bot_technical, "MIN_EXTENDED_HOURS_CHANGE_PCT", 2.0
        ), patch.object(
            bot_technical, "MIN_AUTO_OPTION_VOLUME", 1_000
        ), patch.object(
            bot_technical, "MIN_AUTO_OPTION_OPEN_INTEREST", 5_000
        ), patch.object(
            bot_technical, "MIN_STOCK_PRICE", 8
        ), patch.object(
            bot_technical, "AUTO_WATCHLIST_LIMIT", 10
        ), patch.object(
            bot_technical, "AUTO_WATCHLIST_EXTENDED_CANDIDATE_LIMIT", 1
        ), patch.object(
            bot_technical, "AUTO_WATCHLIST_OPTIONS_CANDIDATE_LIMIT", 1
        ), patch.object(
            bot_technical.requests, "get", side_effect=responses
        ) as get:
            watchlist = bot.get_auto_watchlist(dt.date(2025, 1, 15))

        self.assertEqual(watchlist, ["BASE", "AAA"])
        self.assertIn(
            "/v2/aggs/ticker/AAA/range/1/minute/2025-01-15/2025-01-15",
            get.call_args_list[3].args[0],
        )
        self.assertIn("/v3/snapshot/options/AAA", get.call_args_list[4].args[0])
        self.assertEqual(
            get.call_args_list[4].kwargs["params"]["contract_type"], "call"
        )
        self.assertEqual(get.call_args_list[5].kwargs["params"]["contract_type"], "put")

    def test_reference_ticker_pagination_collects_active_symbols(self):
        bot = StockTechnicalBase([])
        responses = [
            _Response(
                {
                    "results": [{"ticker": "AAA"}],
                    "next_url": "https://api.polygon.io/v3/reference/tickers?cursor=NEXT",
                }
            ),
            _Response({"results": [{"ticker": "BBB"}]}),
        ]

        with patch.object(bot_technical.requests, "get", side_effect=responses) as get:
            tickers = bot.get_active_tickers_for_day("2025-02-03")

        self.assertEqual(tickers, {"AAA", "BBB"})
        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            get.call_args_list[1].kwargs["params"],
            {"apiKey": bot_technical.POLYGON_API_KEY},
        )


if __name__ == "__main__":
    unittest.main()
