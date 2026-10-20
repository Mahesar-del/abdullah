"""Data loaders. All return a DataFrame indexed by tz-naive datetime with columns open/high/low/close(/volume)."""
import os
import sqlite3
import numpy as np
import pandas as pd


def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Normalize column names: strip whitespace, angle brackets (<DATE> -> date) and lowercase
    df.columns = [str(c).strip().strip("<>").lower() for c in df.columns]

    # Combine separate date and time columns (standard MT5 export format)
    if "date" in df.columns and "time" in df.columns:
        dt_str = df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip()
        df["date"] = pd.to_datetime(dt_str, format="mixed", errors="coerce")
        df = df.drop(columns=["time"])

    ren = {"timestamp": "date", "datetime": "date", "adj close": "close", "tickvol": "volume", "vol": "volume"}
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

    df = df.loc[:, ~df.columns.duplicated(keep="first")]
    cols_to_keep = need + (["volume"] if "volume" in df.columns else [])
    df = df[cols_to_keep]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["close"])
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    return df


def validate_price_sanity(df: pd.DataFrame, max_bar_jump: float = 0.15, max_flat_bars: int = 15) -> tuple[bool, str]:
    """Validates that price data is neither stale, flatlined, nor exhibiting erratic price jumps.

    Returns (is_valid: bool, reason: str).
    """
    if df is None or len(df) < 10:
        return False, "Insufficient data bars (<10)"

    # Check for flatlining (stale feeds repeating exact same price)
    tail_closes = df["close"].iloc[-max_flat_bars:]
    if len(tail_closes) >= max_flat_bars and tail_closes.nunique() == 1:
        return False, f"Stale feed: price flatlined at {tail_closes.iloc[-1]} across {max_flat_bars} bars"

    # Check for unrealistic single-bar jumps (bad tick / data corruption / unadjusted split)
    pct_changes = df["close"].pct_change().abs().dropna()
    if not pct_changes.empty:
        max_jump = float(pct_changes.max())
        if max_jump > max_bar_jump:
            bad_idx = pct_changes.idxmax()
            return False, f"Inconsistent price jump: {max_jump:.1%} jump detected at {bad_idx} (exceeds threshold {max_bar_jump:.1%})"

    # Check for non-positive values
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        return False, "Negative or zero prices found in OHLC"

    return True, "OK"


def load_csv(path: str) -> pd.DataFrame:
    """Read CSV or native MT5 export (tab-separated or comma-separated, <DATE> <TIME> <OPEN>... headers)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found: {path}")

    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        first_line = f.readline()

    delim = "\t" if "\t" in first_line else ","
    df = pd.read_csv(path, sep=delim)
    return _standardize(df)


def load_yfinance(ticker: str, interval: str = "1d", period: str = "max") -> pd.DataFrame:
    import yfinance as yf
    if interval in ("1h", "60m") and period == "max":
        period = "730d"  # yfinance hourly limit
    t = yf.Ticker(ticker)
    df = t.history(period=period, interval=interval, auto_adjust=True)
    if (df is None or df.empty) and period == "max":
        df = t.history(period="5y", interval=interval, auto_adjust=True)
    if (df is None or df.empty) and period == "max":
        df = t.history(period="2y", interval=interval, auto_adjust=True)
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
