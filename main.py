from market_data import get_stock_data, compute_indicators
from analyzer import analyze_stock
from ai_analyst import ai_decision

WATCHLIST = ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]

for symbol in WATCHLIST:
    try:
        df = get_stock_data(symbol)
        df = compute_indicators(df)
        analysis = analyze_stock(df)

        ai_output = ai_decision(symbol, analysis)

        print(f"\n=== {symbol} ===")
        print("Analysis:", analysis)
        print("AI Decision:", ai_output)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")
