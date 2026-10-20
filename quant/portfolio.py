"""Portfolio layer: equal-risk combination of sleeves, portfolio-level vol targeting and a drawdown governor.

All sleeves are strictly aligned to a unified business-day calendar (Mon-Fri, 252 days/year)
before combination to eliminate timestamp mismatch and dilution from 24/7 crypto or holiday gaps.
"""
import numpy as np
import pandas as pd


def align_to_business_calendar(s: pd.Series) -> pd.Series:
    """Normalise a return series to standard business days (Mon-Fri, 252 days/year).

    Weekend returns (e.g. 24/7 crypto) are geometrically compounded into Monday's return:
        (1 + r_sat) * (1 + r_sun) * (1 + r_mon) - 1
    Preserves total geometric wealth while eliminating off-calendar dilution.
    Missing business days (e.g. market holidays) are filled with 0.0 return.
    """
    if s.empty:
        return s

    s = s.copy()
    idx = pd.to_datetime(s.index)
    if getattr(idx, 'tz', None) is not None:
        idx = idx.tz_localize(None)
    s.index = idx.normalize()

    # If intra-day bars exist for the same day, compound them into daily return
    if s.index.duplicated().any():
        s = s.groupby(s.index).apply(lambda r: float(np.prod(1.0 + r.values) - 1.0))

    # Map Saturday (dow=5) and Sunday (dow=6) to the following Monday
    def map_to_bday(dt):
        dow = dt.dayofweek
        if dow == 5:
            return dt + pd.Timedelta(days=2)
        elif dow == 6:
            return dt + pd.Timedelta(days=1)
        return dt

    mapped_idx = s.index.map(map_to_bday)
    df_temp = pd.DataFrame({'ret': s.values}, index=mapped_idx)
    # Compound returns for any dates that map to the same business day
    bday_returns = df_temp.groupby(df_temp.index)['ret'].apply(
        lambda r: float(np.prod(1.0 + r.values) - 1.0)
    )

    min_date = bday_returns.index.min()
    max_date = bday_returns.index.max()
    full_bday_idx = pd.date_range(start=min_date, end=max_date, freq='B')
    return bday_returns.reindex(full_bday_idx, fill_value=0.0)


def combine(sleeves: dict, ppy=252, target_vol=0.10, max_lev=3.0, dd_soft=0.05, dd_hard=0.15, floor=0.25):
    """sleeves: {name: net return Series}. Everything is causal (uses info up to t-1 for bar t).

    1. Normalises all sleeves to a single standard business-day calendar.
    2. Equal weight across sleeves (diversification), then scaled to portfolio target vol.
    3. Drawdown governor: full risk until -dd_soft, linearly cut to `floor` at -dd_hard.
    """
    if not sleeves:
        return pd.DataFrame(columns=["ret", "lev", "dd_mult"])

    # Align each sleeve to the unified business-day calendar
    aligned = {name: align_to_business_calendar(s) for name, s in sleeves.items()}
    df = pd.DataFrame(aligned).sort_index().fillna(0.0)

    # Ensure strictly weekday business calendar
    df = df[df.index.dayofweek < 5]

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
