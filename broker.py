import os
from datetime import datetime, time
from zoneinfo import ZoneInfo
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

PAPER = os.getenv("PAPER_TRADING", "true").lower() == "true"
ENABLE_REAL_EXECUTION = os.getenv("ENABLE_REAL_EXECUTION", "false").lower() == "true"

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

client = (
    TradingClient(
        api_key=ALPACA_API_KEY,
        secret_key=ALPACA_SECRET_KEY,
        paper=PAPER,
    )
    if ALPACA_API_KEY and ALPACA_SECRET_KEY
    else None
)


def _within_trading_window(now: datetime | None = None) -> bool:
    """Return True during Monday-Friday, 9:30 AM-11:00 AM Eastern Time."""
    eastern = ZoneInfo("America/New_York")
    current = now.astimezone(eastern) if now else datetime.now(eastern)
    if current.weekday() >= 5:
        return False
    current_time = current.time()
    return time(9, 30) <= current_time <= time(11, 0)


def normalize_option_symbol(option_symbol: str) -> str:
    """Return an Alpaca-compatible OCC option symbol.

    Polygon/Massive option tickers are commonly prefixed with ``O:``
    (for example ``O:GLD260515C00457000``), while Alpaca order
    requests expect the OCC symbol without that vendor prefix.
    """
    symbol = str(option_symbol or "").strip().upper()
    if symbol.startswith("O:"):
        symbol = symbol[2:]
    return symbol


def _execution_allowed():
    """Block live execution unless explicitly enabled."""
    if PAPER:
        return True, "Paper trading enabled"
    if ENABLE_REAL_EXECUTION:
        return True, "Live execution explicitly enabled"
    return False, "Blocked: PAPER_TRADING=false but ENABLE_REAL_EXECUTION is not true"


def place_trade(symbol, qty, side):
    allowed, reason = _execution_allowed()
    if not allowed:
        return reason
    if client is None:
        return "Trade failed: ALPACA_API_KEY and ALPACA_SECRET_KEY are required"
    if not _within_trading_window():
        return "Trade failed: orders are only submitted during trading hours (Mon-Fri, 9:30 AM-11:00 AM ET)"

    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )

    try:
        response = client.submit_order(order)
        return str(response)
    except Exception as e:
        return f"Trade failed: {e}"


def place_option_limit_order(option_symbol: str, contracts: int, side: str, limit_price: float):
    """Place an options DAY limit order. Use paper mode first.

    DAY limit orders submitted after options market hours are accepted for queuing
    by the broker instead of attempting an extended-hours options execution.

    Note: Alpaca options access must be enabled on your account. If unavailable,
    this returns the broker error without stopping the scanner.
    """
    allowed, reason = _execution_allowed()
    if not allowed:
        return reason
    if client is None:
        return "Option order failed: ALPACA_API_KEY and ALPACA_SECRET_KEY are required"
    if not _within_trading_window():
        return "Option order failed: orders are only submitted during trading hours (Mon-Fri, 9:30 AM-11:00 AM ET)"

    alpaca_symbol = normalize_option_symbol(option_symbol)
    if not alpaca_symbol:
        return "Option order failed: option symbol is required"

    order = LimitOrderRequest(
        symbol=alpaca_symbol,
        qty=contracts,
        side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price,
        order_class=OrderClass.SIMPLE,
    )

    try:
        response = client.submit_order(order)
        return str(response)
    except Exception as e:
        return f"Option order failed: {e}"
