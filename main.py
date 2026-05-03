from market_data import get_stock_data, compute_indicators
from analyzer import analyze_stock
from ai_analyst import ai_decision
from market_filter import get_market_bias, market_allows_setup
from telegram_alert import send_telegram
from cooldown import is_in_cooldown, update_cooldown
from sector_filter import sector_confirm
from storage import save_result
from options_engine import select_option_contract, option_to_dict, format_option_alert
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

            allowed, _ = market_allows_setup(analysis["signal"], market["bias"])
            if not allowed:
                continue

            sector_ok, _ = sector_confirm(symbol)
            if not sector_ok:
                continue

            if not analysis["a_plus"]:
                continue

            ai_output = ai_decision(symbol, analysis)

            option_candidate = select_option_contract(symbol, analysis)
            option_dict = option_to_dict(option_candidate)

            trade = {
                "symbol": symbol,
                "signal": analysis["signal"],
                "price": analysis["price"],
                "entry": analysis["entry"],
                "stop": analysis.get("stop"),
                "target": analysis.get("target"),
                "score": analysis["score"],
                "direction": "LONG" if "BULL" in analysis["signal"] else "SHORT",
                "option": option_dict,
            }

            save_result(trade)

            option_text = format_option_alert(option_candidate)

            message = (
                f"🚀 {symbol} A+ Setup\n"
                f"Signal: {analysis['signal']}\n"
                f"Entry: {analysis['entry']}\n"
                f"Price: {analysis['price']}\n"
                f"Score: {analysis['score']}\n\n"
                f"{option_text}\n\n"
                f"AI:\n{ai_output}"
            )

            print(message)
            send_telegram(message)
            update_cooldown(symbol, analysis["signal"])

        except Exception as e:
            print(f"Error {symbol}: {e}")

    time.sleep(300)
