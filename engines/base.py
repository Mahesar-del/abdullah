"""
Base Engine Class — All engines inherit from this
Provides common interface for the Unified Signal Engine
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class EngineResult:
    """Standard result returned by every engine"""
    engine_name:  str
    score:        float          # 0-100 (how strong is the signal)
    direction:    str            # 'BUY', 'SELL', or 'NEUTRAL'
    confidence:   float          # 0-100
    reasoning:    list           # List of strings explaining the decision
    weight:       float          # Engine weight from SRS (e.g. 0.15)
    entry_zone:   Optional[float] = None
    sl_zone:      Optional[float] = None
    tp_zone:      Optional[float] = None

    @property
    def weighted_score(self) -> float:
        """Score multiplied by engine weight"""
        if self.direction == 'SELL':
            return -abs(self.score * self.weight)
        elif self.direction == 'BUY':
            return abs(self.score * self.weight)
        return 0.0

    def to_dict(self) -> dict:
        return {
            'engine':     self.engine_name,
            'score':      round(self.score, 2),
            'direction':  self.direction,
            'confidence': round(self.confidence, 2),
            'reasoning':  self.reasoning,
            'weight':     self.weight,
            'weighted':   round(self.weighted_score, 4),
        }


class BaseEngine(ABC):
    """Abstract base class for all signal engines"""

    name:   str = 'base'
    weight: float = 0.0

    def __init__(self, df: pd.DataFrame, symbol: str = '', timeframe: str = 'H1', *args, **kwargs):
        """
        Args:
            df: OHLCV DataFrame with columns: open, high, low, close, volume
                Index should be datetime, sorted ascending
            symbol: Instrument symbol e.g. 'XAUUSD'
            timeframe: Data timeframe e.g. 'H1', 'M15'
        """
        self.df        = df.copy()
        self.symbol    = symbol
        self.timeframe = timeframe
        self._validate_df()

    def _validate_df(self):
        required = ['open', 'high', 'low', 'close']
        for col in required:
            if col not in self.df.columns:
                raise ValueError(f"DataFrame missing column: '{col}'")
        if len(self.df) < 20:
            raise ValueError("Need at least 20 candles for analysis")

    @abstractmethod
    def analyze(self) -> EngineResult:
        """Run the engine analysis and return an EngineResult"""
        pass

    def _neutral_result(self, reason: str) -> EngineResult:
        return EngineResult(
            engine_name=self.name,
            score=0,
            direction='NEUTRAL',
            confidence=0,
            reasoning=[reason],
            weight=self.weight,
        )
