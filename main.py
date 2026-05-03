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
import time

MAX_ALERTS_PER_SCAN = 5
SCAN_INTERVAL_SECONDS = 300

WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
    "AMD", "NFLX", "SHOP", "COIN", "ROKU", "PLTR",
    "SMH", "MU", "AVGO", "LRCX", "KLAC", "ASML",
    "RIVN", "LCID", "NIO",
    "SPY", "QQQ", "IWM", "XLF", "XLE",
    "XOM", "CVX", "SLB",
    "JPM", "GS", "BAC",
    "MRNA", "REGN", "VRTX",
]


def setup_rank_score(analysis, mtf_info, smc_info, intraday_info):
    """Rank candidates so only the best setups alert per scan."""
    tier_bonus = {
        "A+": 30,
        "Early A+": 20,
        "B+": 10,
    }.get(analysis.get("tier"), 0)

    mtf_bonus = int(mtf_info.get("passed", 0)) * 5
    smc_bonus = int(smc_info.get("score", 0))
    intraday_bonus = 0

    if intraday_info.get("approved"):
        intraday_bonus += 15
    if intraday_info.get("rel_volume_5m", 0) >= 1.5:
        intraday_bonus += 10
    if intraday_info.get("body_pct", 0) >= 0.45:
        intraday_bonus += 5

    late_penalty = 50 if analysis.get("late_entry") else 0
    extension_penalty = float(analysis.get("extended_pct", 0)) * 10

    return (
        int(analysis.get("score", 0))
        + tier_bonus
        + mtf_bonus
        + smc_bonus
        + intraday_bonus
        - late_penalty
        - extension_penalty
    )


while True:
    print("\n===== NEW SCAN =====")

    market = get_market_bias()
    print("Market:", market)

    candidates = []

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

            if not (
                analysis.get("a_plus") or
                analysis.get("early_a_plus") or
                analysis.get("b_plus")
            ):
                print("Skipped: below B+ threshold")
                continue

            skip_loss, loss_reason = should_skip_from_loss_history(symbol, analysis["signal"])
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

            rank_score = setup_rank_score(analysis, mtf_info, smc_info, intraday_info)
            candidates.append({
                "symbol": symbol,
                "analysis": analysis,
                "intraday": intraday_info,
                "mtf": mtf_info,
                "smc": smc_info,
                "rank_score": rank_score,
            })
            print(f"Candidate added: rank_score={rank_score}")

        except Exception as e:
            print(f"Error {symbol}: {e}")

    candidates = sorted(candidates, key=lambda x: x["rank_score"], reverse=True)
    top_candidates = candidates[:MAX_ALERTS_PER_SCAN]

    print(f"\nTop candidates this scan: {[c['symbol'] for c in top_candidates]}")

    for candidate in top_candidates:
        symbol = candidate["symbol"]
        analysis = candidate["analysis"]
        intraday_info = candidate["intraday"]
        mtf_info = candidate["mtf"]
        smc_info = candidate["smc"]
        rank_score = candidate["rank_score"]

        try:
            option_candidate = select_option_contract(symbol, analysis)
            option_dict = option_to_dict(option_candidate)
            option_text = format_option_alert(option_candidate)

            final_gate = pre_trade_filter(symbol, analysis, option_dict)
            print(f"Pre-trade AI for {symbol}:", final_gate)
            if "REJECT" in final_gate.upper():
                print(f"Skipped {symbol}: pre-trade AI rejected setup")
                continue

            ai_output = ai_decision(symbol, analysis)

            trade = {
                "symbol": symbol,
                "signal": analysis["signal"],
                "price": analysis["price"],
                "entry": analysis["entry"],
                "score": analysis["score"],
                "rank_score": rank_score,
                "tier": analysis.get("tier"),
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
                f"🚀 {symbol} {analysis.get('tier')} Setup\n"
                f"Rank Score: {round(rank_score, 2)}\n"
                f"Signal: {analysis['signal']}\n"
                f"Entry: {analysis['entry']}\n"
                f"Price: {analysis['price']}\n"
                f"Score: {analysis['score']}\n\n"
                f"MTF: {mtf_info.get('passed')}/{mtf_info.get('required')}\n"
                f"SMC Score: {smc_info.get('score')}\n"
                f"5m RelVol: {intraday_info.get('rel_volume_5m')}\n\n"
                f"{option_text}\n\n"
                f"AI:\n{ai_output}"
            )

            print(message)
            send_telegram(message)
            update_cooldown(symbol, analysis["signal"])

        except Exception as e:
            print(f"Error processing top candidate {symbol}: {e}")

    time.sleep(SCAN_INTERVAL_SECONDS)
