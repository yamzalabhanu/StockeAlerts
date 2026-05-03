import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

PAPER = os.getenv("PAPER_TRADING", "true").lower() == "true"
ENABLE_REAL_EXECUTION = os.getenv("ENABLE_REAL_EXECUTION", "false").lower() == "true"

client = TradingClient(
    api_key=os.getenv("ALPACA_API_KEY"),
    secret_key=os.getenv("ALPACA_SECRET_KEY"),
    paper=PAPER,
)


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
    """Place an options limit order. Use paper mode first.

    Note: Alpaca options access must be enabled on your account. If unavailable,
    this returns the broker error without stopping the scanner.
    """
    allowed, reason = _execution_allowed()
    if not allowed:
        return reason

    order = LimitOrderRequest(
        symbol=option_symbol,
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
