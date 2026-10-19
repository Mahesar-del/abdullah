"""Data loaders. All return a DataFrame indexed by tz-naive datetime with columns open/high/low/close(/volume)."""
import sqlite3
import numpy as np
import pandas as pd


def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    ren = {"time": "date", "datetime": "date", "timestamp": "date", "adj close": "close"}
    df = df.rename(columns=ren)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce").dt.tz_localize(None)
        df = df.set_index("date")
    else:
        idx = pd.to_datetime(df.index, utc=True, errors="coerce")
        df.index = idx.tz_localize(None)
    need = ["open", "high", "low", "close"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns {missing}. Got {list(df.columns)}")
    df = df[need + (["volume"] if "volume" in df.columns else [])]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["close"])
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    return df


def load_csv(path: str) -> pd.DataFrame:
    """CSV with columns: date/time, open, high, low, close (MT5 / Dukascopy / TradingView exports work)."""
    return _standardize(pd.read_csv(path))


def load_yfinance(ticker: str, interval: str = "1d", period: str = "max") -> pd.DataFrame:
    import yfinance as yf
    if interval in ("1h", "60m") and period == "max":
        period = "730d"  # yfinance hourly limit
    df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"No data for {ticker} ({interval}). Check internet / ticker.")
    return _standardize(df.reset_index())


def load_django_db(db_path: str, symbol: str, timeframe: str = "H4") -> pd.DataFrame:
    """Read candles already stored by the Django app (read-only). NOTE: usually far too short for validation."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    q = """SELECT o.timestamp AS date, o.open_price AS open, o.high_price AS high,
                  o.low_price AS low, o.close_price AS close, o.volume AS volume
           FROM market_data_ohlcv o JOIN market_data_instrument i ON i.id=o.instrument_id
           WHERE i.symbol=? AND o.timeframe=? ORDER BY o.timestamp"""
    df = pd.read_sql_query(q, con, params=(symbol, timeframe))
    con.close()
    return _standardize(df)
