from market_data import get_stock_data, compute_indicators
from analyzer import analyze_stock
from ai_analyst import ai_decision
from market_filter import get_market_bias, market_allows_setup
from telegram_alert import send_telegram
from cooldown import is_in_cooldown, update_cooldown
from sector_filter import sector_confirm
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

            if is_in_cooldown(symbol, analysis["signal"]):
                continue

            allowed, reason = market_allows_setup(analysis["signal"], market["bias"])
            if not allowed:
                continue

            sector_ok, sector_reason = sector_confirm(symbol)
            if not sector_ok:
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
            update_cooldown(symbol, analysis["signal"])

        except Exception as e:
            print(f"Error {symbol}: {e}")

    time.sleep(300)
