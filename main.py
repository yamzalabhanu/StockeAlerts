from market_data import get_stock_data, compute_indicators
from analyzer import analyze_stock

WATCHLIST = ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]

for symbol in WATCHLIST:
    try:
        df = get_stock_data(symbol)
        df = compute_indicators(df)
        result = analyze_stock(df)

        print(f"\n=== {symbol} ===")
        print(result)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")
