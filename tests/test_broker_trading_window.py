from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

import broker


def test_within_trading_window_allows_weekday_session():
    ts = datetime(2026, 5, 18, 9, 30, tzinfo=ZoneInfo("America/New_York"))  # Monday
    assert broker._within_trading_window(ts) is True






def test_within_trading_window_allows_sell_all_day_session():
    ts = datetime(2026, 5, 18, 14, 30, tzinfo=ZoneInfo("America/New_York"))  # Monday
    assert broker._within_trading_window(ts, side="SELL") is True


def test_within_trading_window_blocks_sell_after_close():
    ts = datetime(2026, 5, 18, 16, 1, tzinfo=ZoneInfo("America/New_York"))  # Monday
    assert broker._within_trading_window(ts, side="SELL") is False


def test_within_trading_window_blocks_after_11am():
    ts = datetime(2026, 5, 18, 11, 1, tzinfo=ZoneInfo("America/New_York"))  # Monday
    assert broker._within_trading_window(ts) is False


def test_within_trading_window_blocks_weekend():
    ts = datetime(2026, 5, 17, 10, 0, tzinfo=ZoneInfo("America/New_York"))  # Sunday
    assert broker._within_trading_window(ts) is False


def test_place_trade_blocks_outside_trading_window():
    with patch("broker._execution_allowed", return_value=(True, "ok")), patch("broker.client", object()), patch(
        "broker._within_trading_window", return_value=False
    ):
        response = broker.place_trade("AAPL", 1, "BUY")
    assert "only submitted during trading hours" in response


def test_place_option_order_blocks_outside_trading_window():
    with patch("broker._execution_allowed", return_value=(True, "ok")), patch("broker.client", object()), patch(
        "broker._within_trading_window", return_value=False
    ):
        response = broker.place_option_limit_order("AAPL260619C00200000", 1, "BUY", 1.25)
    assert "only submitted during trading hours" in response
