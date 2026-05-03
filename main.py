from market_data import get_stock_data, compute_indicators
from analyzer import analyze_stock
from ai_analyst import ai_decision
from market_filter import get_market_bias, market_allows_setup
from telegram_alert import send_telegram
import time

WATCHLIST = ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]

while True:
    print("\n===== NEW SCAN =====")

    market = get_market_bias()
    print("Market:", market)

    for symbol in WATCHLIST:
        try:
            df = get_stock_data(symbol)
            df = compute_indicators(df)
            analysis = analyze_stock(df)

            allowed, reason = market_allows_setup(analysis["signal"], market["bias"])

            if not allowed:
                continue

            if not analysis["a_plus"]:
                continue

            ai_output = ai_decision(symbol, analysis)

            message = f"""
🚀 {symbol} A+ Setup

Signal: {analysis['signal']}
Entry: {analysis['entry']}
Price: {analysis['price']}
Score: {analysis['score']}

AI:
{ai_output}
"""

            print(message)
            send_telegram(message)

        except Exception as e:
            print(f"Error {symbol}: {e}")

    time.sleep(300)
