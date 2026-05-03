import pandas as pd
import yfinance as yf


def get_stock_data(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """Fetch daily OHLCV data for swing-trade analysis."""
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No market data returned for {symbol}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    df.dropna(inplace=True)
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMAs, DMAs, ATR, volume, trend, breakout levels."""
    df = df.copy()

    df["EMA8"] = df["Close"].ewm(span=8, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["DMA50"] = df["Close"].rolling(50).mean()
    df["DMA200"] = df["Close"].rolling(200).mean()

    df["High20"] = df["High"].rolling(20).max().shift(1)
    df["Low20"] = df["Low"].rolling(20).min().shift(1)
    df["High50"] = df["High"].rolling(50).max().shift(1)
    df["Low50"] = df["Low"].rolling(50).min().shift(1)

    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["ATR14"] = tr.rolling(14).mean()
    df["ATR10AVG"] = df["ATR14"].rolling(10).mean()

    df["Vol20"] = df["Volume"].rolling(20).mean()
    df["RelVol"] = df["Volume"] / df["Vol20"]

    df["ChangePct"] = df["Close"].pct_change() * 100
    df["RangePct"] = ((df["High"] - df["Low"]) / df["Close"]) * 100

    return df
