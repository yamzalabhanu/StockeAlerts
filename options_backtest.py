from market_data import get_stock_data, compute_indicators
from analyzer import analyze_stock


def estimate_option_return(stock_move_pct, delta=0.5):
    """Approximate option return from underlying move."""
    return stock_move_pct * delta * 3  # leverage factor


def backtest_options(symbol="NVDA"):
    df = compute_indicators(get_stock_data(symbol))
    results = []

    for i in range(50, len(df) - 5):
        sub = df.iloc[:i]
        analysis = analyze_stock(sub)

        if not analysis["a_plus"]:
            continue

        entry_price = analysis["price"]
        future_price = df.iloc[i + 5].Close

        move_pct = ((future_price - entry_price) / entry_price) * 100
        option_return = estimate_option_return(move_pct)

        results.append({
            "symbol": symbol,
            "stock_move_pct": round(move_pct, 2),
            "option_return_pct": round(option_return, 2),
        })

    return results


if __name__ == "__main__":
    print(backtest_options()[:10])
