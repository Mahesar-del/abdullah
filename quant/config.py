"""Per-instrument assumptions.

cost_bps = ONE-WAY cost per unit of notional traded (half-spread + slippage + commission), in basis points.
These are deliberately conservative defaults. REPLACE them with your broker's real numbers
(check your Exness/MT5 spread + commission + swap) — results are very sensitive to this.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    name: str
    yahoo: str          # yfinance ticker
    cost_bps: float     # one-way cost, bps of notional
    days_per_year: int  # trading days used for annualisation


ASSETS = {
    "EURUSD": Asset("EURUSD", "EURUSD=X", 1.5, 252),
    "GBPUSD": Asset("GBPUSD", "GBPUSD=X", 2.0, 252),
    "XAUUSD": Asset("XAUUSD", "GC=F", 3.0, 252),
    "US30":   Asset("US30",   "^DJI",     3.0, 252),
    "BTCUSD": Asset("BTCUSD", "BTC-USD", 10.0, 365),
}

BARS_PER_DAY = {"1d": 1, "1h": 24, "4h": 6}


def periods_per_year(asset: Asset, interval: str) -> int:
    return asset.days_per_year * BARS_PER_DAY.get(interval, 1)
