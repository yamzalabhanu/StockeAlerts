from market_data import get_stock_data, compute_indicators
from analyzer import analyze_stock
from ai_analyst import ai_decision
from market_filter import get_market_bias, market_allows_setup
from telegram_alert import send_telegram
from cooldown import is_in_cooldown, update_cooldown
from sector_filter import sector_confirm
from storage import save_result
from options_engine import select_option_contract, option_to_dict, format_option_alert
from loss_analyzer import should_skip_from_loss_history
from pre_trade_ai import pre_trade_filter
import time

WATCHLIST = [
    # 🔥 Mega Cap Momentum
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA",

    # ⚡ High Beta / Movers
    "AMD","NFLX","SHOP","COIN","ROKU","PLTR",

    # 🧠 AI / Semiconductor Leaders
    "SMH","MU","AVGO","LRCX","KLAC","ASML",

    # 🚗 EV / Growth
    "RIVN","LCID","NIO",

    # 📊 ETFs (Market + Sector)
    "SPY","QQQ","IWM","SMH","XLF","XLE",

    # 🛢️ Energy / Commodities Momentum
    "XOM","CVX","SLB",

    # 🏦 Financial Movers
    "JPM","GS","BAC",

    # 🧪 Biotech (volatile movers)
    "MRNA","REGN","VRTX"

    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
    "AMD", "NFLX", "SHOP", "COIN", "ROKU", "PLTR",
    "SMH", "MU", "AVGO", "LRCX", "KLAC", "ASML",
    "RIVN", "LCID", "NIO",
    "SPY", "QQQ", "IWM", "XLF", "XLE",
    "XOM", "CVX", "SLB",
    "JPM", "GS", "BAC",
    "MRNA", "REGN", "VRTX",
]

while True:
    print("\n===== NEW SCAN =====")

    market = get_market_bias()
    print("Market:", market)

    for symbol in WATCHLIST:
        try:
            print(f"\n--- Scanning {symbol} ---")

            df = get_stock_data(symbol)
            df = compute_indicators(df)
            analysis = analyze_stock(df)
            print("Analysis:", analysis)

            if is_in_cooldown(symbol, analysis["signal"]):
                print("Skipped: cooldown active")
                continue

            allowed, market_reason = market_allows_setup(analysis["signal"], market["bias"])
            if not allowed:
                print("Skipped market filter:", market_reason)
                continue

            sector_ok, sector_reason = sector_confirm(symbol)
            if not sector_ok:
                print("Skipped sector filter:", sector_reason)
                continue

            if not analysis["a_plus"]:
                print("Skipped: not A+ setup")
                continue

            skip_loss, loss_reason = should_skip_from_loss_history(symbol, analysis["signal"])
            if skip_loss:
                print("Skipped loss-history filter:", loss_reason)
                continue

            option_candidate = select_option_contract(symbol, analysis)
            option_dict = option_to_dict(option_candidate)
            option_text = format_option_alert(option_candidate)

            final_gate = pre_trade_filter(symbol, analysis, option_dict)
            print("Pre-trade AI:", final_gate)
            if "REJECT" in final_gate.upper():
                print("Skipped: pre-trade AI rejected setup")
                continue

            ai_output = ai_decision(symbol, analysis)

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
                "pre_trade_ai": final_gate,
                "ai_decision": ai_output,
            }

            save_result(trade)

            message = (
                f"🚀 {symbol} A+ Setup\n"
                f"Signal: {analysis['signal']}\n"
                f"Entry: {analysis['entry']}\n"
                f"Price: {analysis['price']}\n"
                f"Score: {analysis['score']}\n\n"
                f"{option_text}\n\n"
                f"Pre-Trade AI:\n{final_gate}\n\n"
                f"AI:\n{ai_output}"
            )

            print(message)
            send_telegram(message)
            update_cooldown(symbol, analysis["signal"])

        except Exception as e:
            print(f"Error {symbol}: {e}")

    time.sleep(300)
