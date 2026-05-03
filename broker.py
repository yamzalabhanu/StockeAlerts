import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

PAPER = os.getenv("PAPER_TRADING", "true").lower() == "true"

client = TradingClient(
    api_key=os.getenv("ALPACA_API_KEY"),
    secret_key=os.getenv("ALPACA_SECRET_KEY"),
    paper=PAPER
)


def place_trade(symbol, qty, side):
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY
    )

    try:
        response = client.submit_order(order)
        return str(response)
    except Exception as e:
        return f"Trade failed: {e}"
