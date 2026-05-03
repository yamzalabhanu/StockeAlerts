import time

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
from intraday_confirm import intraday_confirmation
from mtf_confirm import mtf_confirmation
from smc_confirm import smc_confirmation


WATCHLIST = [
    # 🔥 Mega Cap Leaders
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA",

    # ⚡ High Beta / Momentum
    "AMD","NFLX","SHOP","COIN","ROKU","PLTR",

    # 🧠 AI / Data Center Infra
    "NVDA","SMH","AVGO","ASML","LRCX","KLAC",
    "ANET","DELL","HPE","SUPM","ARM",

    # 💾 Memory / Storage (CYCLICAL MOMENTUM)
    "MU","WDC","STX","SKYY","UMC",

    # ⚡ Semiconductor Supply Chain
    "AMAT","TER","ONTO","IPGP",

    # 🔋 Energy + Nuclear Theme
    "XOM","CVX","SLB","HAL",
    "URA","CCJ","BWXT","LEU",

    # ⚛️ Nuclear / Uranium (HIGH MOMENTUM)
    "SMR","OKLO","UEC","NXE",

    # 🧬 Quantum / Next-Gen Compute
    "IONQ","QBTS","RGTI",

    # ☁️ Cloud / Software Infra
    "CRM","SNOW","MDB","DDOG","NET","ZS",

    # 📡 Networking / Infra
    "CSCO","JNPR","EXTR",

    # 🚗 EV + Future Mobility
    "RIVN","LCID","NIO",

    # 🏦 Financials (Momentum Rotation)
    "JPM","GS","BAC",

    # 🧪 Biotech Movers
    "MRNA","REGN","VRTX",

    # 📊 ETFs (Market + Sector Bias)
    "SPY","QQQ","IWM","XLF","XLE","SMH","XLK"
]

SCAN_INTERVAL_SECONDS = 300


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

            allowed, market_reason = market_allows_setup(
                analysis["signal"],
                market["bias"],
            )
            if not allowed:
                print("Skipped market filter:", market_reason)
                continue

            sector_ok, sector_reason = sector_confirm(symbol)
            if not sector_ok:
                print("Skipped sector filter:", sector_reason)
                continue

            if not (analysis.get("a_plus") or analysis.get("early_a_plus")):
                print("Skipped: not A+ or early setup")
                continue

            skip_loss, loss_reason = should_skip_from_loss_history(
                symbol,
                analysis["signal"],
            )
            if skip_loss:
                print("Skipped loss-history filter:", loss_reason)
                continue

            intraday_ok, intraday_info = intraday_confirmation(symbol, analysis)
            print("Intraday:", intraday_info)

            if not intraday_ok:
                print("Skipped intraday confirmation")
                continue

            mtf_ok, mtf_info = mtf_confirmation(symbol, analysis, strict=True)
            print("MTF:", mtf_info)

            if not mtf_ok:
                print("Skipped MTF confirmation")
                continue

            smc_ok, smc_info = smc_confirmation(symbol, analysis)
            print("SMC:", smc_info)

            if not smc_ok:
                print("Skipped SMC confirmation")
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
                "intraday": intraday_info,
                "mtf": mtf_info,
                "smc": smc_info,
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
                f"Intraday: {intraday_info}\n\n"
                f"MTF: passed {mtf_info.get('passed')}/{mtf_info.get('required')}\n"
                f"SMC Score: {smc_info.get('score')}\n\n"
                f"{option_text}\n\n"
                f"Pre-Trade AI:\n{final_gate}\n\n"
                f"AI:\n{ai_output}"
            )

            print(message)
            send_telegram(message)
            update_cooldown(symbol, analysis["signal"])

        except Exception as e:
            print(f"Error {symbol}: {e}")

    time.sleep(SCAN_INTERVAL_SECONDS)
