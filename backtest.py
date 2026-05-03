from market_data import get_stock_data, compute_indicators
from analyzer import analyze_stock


def backtest(symbol="AAPL"):
    df = compute_indicators(get_stock_data(symbol))
    results = []

    for i in range(50, len(df)-5):
        sub_df = df.iloc[:i]
        analysis = analyze_stock(sub_df)

        if not analysis["a_plus"]:
            continue

        entry = analysis["price"]
        future_price = df.iloc[i+5].Close

        outcome = "WIN" if future_price > entry else "LOSS"

        results.append({
            "symbol": symbol,
            "entry": entry,
            "exit": float(future_price),
            "outcome": outcome
        })

    return results


if __name__ == "__main__":
    results = backtest("NVDA")
    print(results[:10])
