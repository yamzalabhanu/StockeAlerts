from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from config import ALPACA_API_KEY, ALPACA_SECRET_KEY

client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)


def place_trade(ticker, direction, qty=1):
    side = OrderSide.BUY if direction == "CALL" else OrderSide.SELL

    order = MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.DAY
    )

    try:
        response = client.submit_order(order)
        print(f"Order placed: {response}")
        return response
    except Exception as e:
        print(f"Trade failed: {e}")
        return None
