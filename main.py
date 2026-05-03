# UPDATED VERSION (relaxed filters)
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

MAX_ALERTS_PER_SCAN = 5
SCAN_INTERVAL_SECONDS = 300

WATCHLIST = WATCHLIST = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","AMD","NFLX","SHOP","COIN","ROKU","PLTR",
    "SMH","AVGO","ASML","LRCX","KLAC","ANET","DELL","HPE","SMCI","ARM",
    "MU","WDC","STX","SKYY","UMC",
    "AMAT","TER","ONTO","IPGP",
    "XOM","CVX","SLB","HAL","URA","CCJ","BWXT","LEU","SMR","OKLO","UEC","NXE",
    "IONQ","QBTS","RGTI",
    "CRM","SNOW","MDB","DDOG","NET","ZS",
    "RIVN","LCID","NIO",
    "JPM","GS","BAC",
    "MRNA","REGN","VRTX",
    "SPY","QQQ","IWM","XLF","XLE","XLK",
]


def setup_rank_score(analysis, mtf_info, smc_info, intraday_info):
    score = int(analysis.get("score", 0))

    # Bonuses instead of hard filters
    if analysis.get("tier") == "B+":
        score += 10

    if mtf_info.get("approved"):
        score += 10

    # SMC now bonus only
    score += int(smc_info.get("score", 0))

    if intraday_info.get("approved"):
        score += 15

    return score


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
                continue

            allowed, market_reason = market_allows_setup(
                analysis["signal"],
                market["bias"],
            )
            if not allowed:
                print("Skipped market filter:", market_reason)
                continue

            # 🔥 RELAXED THRESHOLD (was strict B+ only)
            if analysis.get("score", 0) < 60:
                print("Skipped: below relaxed threshold (60)")
                continue

            intraday_ok, intraday_info = intraday_confirmation(symbol, analysis)
            print("Intraday:", intraday_info)
            if not intraday_ok:
                continue

            mtf_ok, mtf_info = mtf_confirmation(symbol, analysis, strict=False)
            print("MTF:", mtf_info)

            smc_ok, smc_info = smc_confirmation(symbol, analysis)
            print("SMC:", smc_info)
            # 🔥 NO MORE BLOCKING

            rank_score = setup_rank_score(
                analysis,
                mtf_info,
                smc_info,
                intraday_info,
            )

            candidates.append({
                "symbol": symbol,
                "analysis": analysis,
                "intraday": intraday_info,
                "mtf": mtf_info,
                "smc": smc_info,
                "rank_score": rank_score,
            })

            print(f"Candidate added: rank_score={round(rank_score, 2)}")

        except Exception as e:
            print(f"Error {symbol}: {e}")

    candidates = sorted(
        candidates,
        key=lambda x: x["rank_score"],
        reverse=True,
    )

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

            ai_output = ai_decision(symbol, analysis)

            message = (
                f"🚀 {symbol} Setup\n"
                f"Rank Score: {round(rank_score, 2)}\n"
                f"Signal: {analysis['signal']}\n"
                f"Price: {analysis['price']}\n"
                f"Score: {analysis['score']}\n\n"
                f"Intraday: {intraday_info.get('confirmations')}/{intraday_info.get('required_confirmations')}\n"
                f"MTF Passed: {mtf_info.get('passed')}\n"
                f"SMC Score: {smc_info.get('score')}\n"
                f"{option_text}"
            )

            print(message)
            send_telegram(message)
            update_cooldown(symbol, analysis["signal"])

        except Exception as e:
            print(f"Error processing {symbol}: {e}")

    time.sleep(SCAN_INTERVAL_SECONDS)
