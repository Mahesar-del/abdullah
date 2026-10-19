"""Baseline alpha sleeves. Every function is CAUSAL: signal[t] uses only data up to and including bar t.
Output: Series in {-1, 0, +1} = desired direction decided at close of bar t (executed from bar t+1).
Grids are deliberately tiny to limit overfitting (few trials)."""
import numpy as np
import pandas as pd


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def trend_ema(df, fast=50, slow=200):
    c = df["close"]
    sig = np.sign(_ema(c, fast) - _ema(c, slow)).astype(float)
    sig.iloc[:slow] = 0.0
    return sig


def donchian(df, n=55):
    """Breakout stop-and-reverse on the PREVIOUS n-bar channel (shifted -> no lookahead)."""
    hi = df["high"].rolling(n).max().shift(1)
    lo = df["low"].rolling(n).min().shift(1)
    c = df["close"]
    raw = pd.Series(np.nan, index=df.index)
    raw[c > hi] = 1.0
    raw[c < lo] = -1.0
    return raw.ffill().fillna(0.0)


def meanrev(df, lookback=20, z_entry=2.0, er_max=0.35, z_stop=3.5):
    """Fade stretched moves only when the market is NOT trending (Kaufman efficiency ratio low)."""
    c = df["close"]
    m, sd = c.rolling(lookback).mean(), c.rolling(lookback).std()
    z = ((c - m) / sd).to_numpy()
    er = (c.diff(lookback).abs() / c.diff().abs().rolling(lookback).sum()).to_numpy()
    out = np.zeros(len(c))
    state, locked = 0.0, False
    for i in range(len(c)):
        if np.isnan(z[i]) or np.isnan(er[i]):
            state, locked = 0.0, False
        else:
            if locked and abs(z[i]) < z_entry:
                locked = False
            if state == 0.0:
                if not locked and er[i] <= er_max:
                    if z[i] <= -z_entry:
                        state = 1.0
                    elif z[i] >= z_entry:
                        state = -1.0
            elif (state > 0 and z[i] >= 0) or (state < 0 and z[i] <= 0):
                state = 0.0                       # target reached (mean)
            elif (state > 0 and z[i] <= -z_stop) or (state < 0 and z[i] >= z_stop):
                state, locked = 0.0, True         # it's trending against us -> stop out, wait
        out[i] = state
    return pd.Series(out, index=c.index)


REGISTRY = {
    "trend":    (trend_ema, {"fast": [20, 50], "slow": [100, 200]}),
    "donchian": (donchian,  {"n": [20, 55, 100]}),
    "meanrev":  (meanrev,   {"lookback": [10, 20], "z_entry": [1.5, 2.0]}),
}
