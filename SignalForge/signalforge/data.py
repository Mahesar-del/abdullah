"""Data adapters. Yahoo is unofficial; failures return an explicit data gap."""
from __future__ import annotations
from datetime import datetime, timezone
import os
import numpy as np
import pandas as pd

YAHOO_SYMBOLS = {"GOLD": "GC=F", "XAUUSD": "GC=F", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X"}

def synthetic_ohlcv(periods: int = 2600, freq: str = "h", seed: int = 7) -> pd.DataFrame:
    """Deterministic synthetic history used by offline tests, never presented as market data."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor(freq), periods=periods, freq=freq)
    regime = np.where(np.arange(periods) % 480 < 300, 0.00012, -0.00008)
    returns = regime + rng.normal(0, 0.004, periods)
    close = 2000 * np.exp(np.cumsum(returns))
    spread = np.abs(rng.normal(.003, .0015, periods))
    return pd.DataFrame({"open": np.r_[close[0], close[:-1]], "high": close*(1+spread), "low": close*(1-spread), "close": close, "volume": rng.integers(100, 2000, periods)}, index=idx)

def collect_candles(symbol: str, interval: str = "1h", offline: bool = False) -> dict:
    if offline or os.getenv("SIGNALFORGE_OFFLINE") == "1":
        return {"status": "ok", "source": "synthetic/offline", "data": synthetic_ohlcv(freq="h"), "data_gaps": ["Offline synthetic data; not a tradable quote."]}
    try:
        import yfinance as yf
        ticker = YAHOO_SYMBOLS.get(symbol.upper(), symbol)
        raw = yf.download(ticker, period="2y", interval=interval, auto_adjust=True, progress=False)
        if raw.empty: raise ValueError("Yahoo returned no candles")
        if isinstance(raw.columns, pd.MultiIndex): raw.columns = raw.columns.get_level_values(0)
        df = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
        df.index = pd.to_datetime(df.index, utc=True)
        return {"status": "ok", "source": "Yahoo Finance (unofficial)", "data": df, "data_gaps": []}
    except Exception as exc:
        return {"status": "degraded", "source": "unavailable", "data": synthetic_ohlcv(), "data_gaps": [f"Candle download failed: {exc}", "Synthetic fallback is research-only."]}

def event_calendar(now: pd.Timestamp | None = None) -> dict:
    """User-editable CSV can replace this stub; no future prices are requested or implied."""
    now = now or pd.Timestamp.now(tz="UTC")
    return {"status": "ok", "events": [], "data_gaps": ["No event CSV configured; event-risk filter cannot confirm upcoming releases."]}
