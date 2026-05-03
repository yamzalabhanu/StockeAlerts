import yfinance as yf
import pandas as pd


def get_stock_data(symbol: str, period="6mo", interval="1d"):
    df = yf.download(symbol, period=period, interval=interval)
    df.dropna(inplace=True)
    return df


def compute_indicators(df: pd.DataFrame):
    df["EMA8"] = df["Close"].ewm(span=8).mean()
    df["EMA21"] = df["Close"].ewm(span=21).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()
    df["High50"] = df["High"].rolling(50).max()
    df["Low50"] = df["Low"].rolling(50).min()
    return df
