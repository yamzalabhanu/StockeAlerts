from market_data import get_stock_data, compute_indicators
from analyzer import analyze_stock
from ai_analyst import ai_decision
from market_filter import get_market_bias, market_allows_setup
import asyncio
from chart_ai import analyze_chart_ai

WATCHLIST = ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]

market = get_market_bias()
print("\n=== MARKET ===")
print(market)

for symbol in WATCHLIST:
    try:
        df = get_stock_data(symbol)
        df = compute_indicators(df)
        analysis = analyze_stock(df)

        allowed, reason = market_allows_setup(analysis["signal"], market["bias"])

        if not allowed:
            print(f"\n=== {symbol} ===")
            print("Skipped:", reason)
            continue

        ai_output = ai_decision(symbol, analysis)
        chart_ai_output = asyncio.run(analyze_chart_ai(symbol))

        print(f"\n=== {symbol} ===")
        print("Analysis:", analysis)
        print("AI Decision:", ai_output)
        print("Chart AI:", chart_ai_output)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")
