"""Synthetic price generators — ONLY for testing the machinery (never evidence of real profitability)."""
import numpy as np
import pandas as pd


def _ohlc(returns, seed, start="2010-01-01", base=100.0):
    rng = np.random.default_rng(seed + 999)
    n = len(returns)
    close = base * np.exp(np.cumsum(returns))
    open_ = np.r_[base, close[:-1]]
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n)))
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def null_walk(n=3000, seed=0, vol=0.01):
    """Pure random walk: NO exploitable edge exists. Any honest backtest must show ~0 (or negative after costs)."""
    return _ohlc(np.random.default_rng(seed).normal(0, vol, n), seed)


def regime_trend(n=3000, seed=0, vol=0.01, drift=0.0006, p_switch=0.005):
    """Persistent up/down drift regimes: trend-following SHOULD find an edge here."""
    rng = np.random.default_rng(seed)
    state, d = 1.0, np.empty(n)
    for i in range(n):
        if rng.random() < p_switch:
            state = -state
        d[i] = state * drift
    return _ohlc(d + rng.normal(0, vol, n), seed)
