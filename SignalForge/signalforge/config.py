from dataclasses import dataclass, field

WEIGHTS = {"trend": 0.36, "momentum": 0.26, "stretch": 0.18, "liquidity": 0.20}
LONG_THRESHOLD = 0.30
SHORT_THRESHOLD = -0.30
COST_BPS = 2.0
HIGH_IMPACT_BUFFER_MINUTES = (-60, 30)

@dataclass
class Settings:
    symbol: str = "GOLD"
    horizon: str = "swing"
    account: float = 5000.0
    risk_pct: float = 1.0
    weights: dict = field(default_factory=lambda: WEIGHTS.copy())
