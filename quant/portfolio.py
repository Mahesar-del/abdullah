"""Portfolio layer: equal-risk combination of sleeves, portfolio-level vol targeting and a drawdown governor."""
import numpy as np
import pandas as pd


def combine(sleeves: dict, ppy=252, target_vol=0.10, max_lev=3.0, dd_soft=0.05, dd_hard=0.15, floor=0.25):
    """sleeves: {name: net return Series}. Everything is causal (uses info up to t-1 for bar t).
    - equal weight across sleeves (diversification), then scaled to portfolio target vol
    - drawdown governor: full risk until -dd_soft, linearly cut to `floor` at -dd_hard (never fully off)"""
    df = pd.DataFrame(sleeves).sort_index().fillna(0.0)
    raw = df.mean(axis=1)
    vol = raw.ewm(span=60, min_periods=30).std() * np.sqrt(ppy)
    lev = (target_vol / vol).clip(upper=max_lev).shift(1).fillna(0.0)
    scaled = (raw * lev).to_numpy()

    eq = peak = 1.0
    out, mult = np.zeros(len(scaled)), np.ones(len(scaled))
    for i, r in enumerate(scaled):
        dd = eq / peak - 1.0
        if dd >= -dd_soft:
            m = 1.0
        elif dd <= -dd_hard:
            m = floor
        else:
            m = 1.0 - (1.0 - floor) * (-dd - dd_soft) / (dd_hard - dd_soft)
        mult[i] = m
        out[i] = r * m
        eq *= 1.0 + out[i]
        peak = max(peak, eq)
    return pd.DataFrame({"ret": out, "lev": lev.to_numpy(), "dd_mult": mult}, index=df.index)
