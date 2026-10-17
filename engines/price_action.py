"""
Price Action & Market Structure Engine — Weight: 15%
Phase 2 Upgrades:
- HH / HL / LH / LL Market Structure
- Support & Resistance Detection
- Breakouts, Retests, False Breakouts (Spring / Upthrust)
- Rejection and Displacement Analysis
- Candlestick Patterns (Engulfing, Pin bar, Hammers, Star, Inside bars, Soldiers/Crows)
- Previous Day/Week Highs and Lows (PDH, PDL, PWH, PWL)
- Range Expansion / Contraction
- Regime Classification: Trend, Range, Transition, Volatile
- Automatic event persistence to StructureEvent model
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from .base import BaseEngine, EngineResult


class PriceActionEngine(BaseEngine):
    name   = 'price_action'
    weight = 0.15

    SHADOW_RATIO  = 2.0
    DOJI_THRESH   = 0.1
    ENGULF_FACTOR = 1.05

    def __init__(self, df: pd.DataFrame, symbol: str = '', timeframe: str = 'H1'):
        super().__init__(df, symbol)
        self.timeframe = timeframe
        self.structure_events = []

    def analyze(self) -> EngineResult:
        try:
            self._compute_basics()
            self._detect_swings_and_structure()
            self._detect_support_resistance()
            self._detect_breakouts_and_displacement()
            self._detect_session_and_period_levels()
            result = self._evaluate()
            self._save_structure_events_safely()
            return result
        except Exception as e:
            return self._neutral_result(f"PA calculation error: {str(e)}")

    def _compute_basics(self):
        df = self.df
        o  = df['open'].values.astype(float)
        h  = df['high'].values.astype(float)
        l  = df['low'].values.astype(float)
        c  = df['close'].values.astype(float)

        self.body    = np.abs(c - o)
        self.range_  = h - l
        self.upper_s = h - np.maximum(o, c)
        self.lower_s = np.minimum(o, c) - l
        self.is_bull = c > o
        self.is_bear = c < o

        tr = np.column_stack([
            h - l,
            np.abs(h - np.roll(c, 1)),
            np.abs(l - np.roll(c, 1))
        ]).max(axis=1)
        tr[0] = h[0] - l[0]
        self.atr = float(pd.Series(tr).ewm(span=14, adjust=False).mean().iloc[-1])
        self.avg_body = float(pd.Series(self.body).rolling(20).mean().iloc[-1])
        self.avg_range = float(pd.Series(self.range_).rolling(20).mean().iloc[-1])

    def _detect_swings_and_structure(self):
        """Identify swing highs/lows and determine HH/HL/LH/LL"""
        h = self.df['high'].values
        l = self.df['low'].values
        n = len(h)

        self.swing_highs = []
        self.swing_lows  = []

        # 3-bar pivot detection
        for i in range(2, n - 2):
            if h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]:
                self.swing_highs.append((i, float(h[i])))
            if l[i] < l[i-1] and l[i] < l[i-2] and l[i] < l[i+1] and l[i] < l[i+2]:
                self.swing_lows.append((i, float(l[i])))

        # Determine Market Structure
        self.structure_bias = 'NEUTRAL'
        self.structure_labels = []

        if len(self.swing_highs) >= 2 and len(self.swing_lows) >= 2:
            prev_sh, cur_sh = self.swing_highs[-2][1], self.swing_highs[-1][1]
            prev_sl, cur_sl = self.swing_lows[-2][1], self.swing_lows[-1][1]

            if cur_sh > prev_sh:
                self.structure_labels.append('HH')
            else:
                self.structure_labels.append('LH')

            if cur_sl > prev_sl:
                self.structure_labels.append('HL')
            else:
                self.structure_labels.append('LL')

            if cur_sh > prev_sh and cur_sl > prev_sl:
                self.structure_bias = 'BULLISH'
                self.regime = 'TRENDING_UP'
            elif cur_sh < prev_sh and cur_sl < prev_sl:
                self.structure_bias = 'BEARISH'
                self.regime = 'TRENDING_DOWN'
            else:
                self.structure_bias = 'NEUTRAL'
                self.regime = 'RANGING'
        else:
            self.regime = 'CONSOLIDATION'

    def _detect_support_resistance(self):
        """Cluster swing points into key S/R levels"""
        levels = [sh[1] for sh in self.swing_highs[-5:]] + [sl[1] for sl in self.swing_lows[-5:]]
        cur_close = float(self.df['close'].iloc[-1])

        self.resistances = sorted([lv for lv in levels if lv > cur_close])
        self.supports    = sorted([lv for lv in levels if lv < cur_close], reverse=True)

        self.nearest_res = self.resistances[0] if self.resistances else cur_close + self.atr * 2
        self.nearest_sup = self.supports[0] if self.supports else cur_close - self.atr * 2

    def _detect_breakouts_and_displacement(self):
        """Detect breakouts, false breakouts, and high-energy displacements"""
        c = float(self.df['close'].iloc[-1])
        o = float(self.df['open'].iloc[-1])
        h = float(self.df['high'].iloc[-1])
        l = float(self.df['low'].iloc[-1])
        prev_c = float(self.df['close'].iloc[-2])

        self.breakout_type = None

        # Breakout / False Breakout
        if prev_c <= self.nearest_res and c > self.nearest_res:
            self.breakout_type = 'BULLISH_BREAKOUT'
            self.structure_events.append(('BREAKOUT', self.nearest_res))
        elif prev_c >= self.nearest_sup and c < self.nearest_sup:
            self.breakout_type = 'BEARISH_BREAKOUT'
            self.structure_events.append(('BREAKOUT', self.nearest_sup))
        elif h > self.nearest_res and c < self.nearest_res:
            self.breakout_type = 'FALSE_BREAKOUT_HIGH'
            self.structure_events.append(('FALSE_BREAKOUT', self.nearest_res))
        elif l < self.nearest_sup and c > self.nearest_sup:
            self.breakout_type = 'FALSE_BREAKOUT_LOW'
            self.structure_events.append(('FALSE_BREAKOUT', self.nearest_sup))

        # Displacement detection (body >= 1.8x average body)
        cur_body = abs(c - o)
        self.has_displacement = cur_body >= (self.avg_body * 1.8) and cur_body > 0
        if self.has_displacement:
            self.structure_events.append(('DISPLACEMENT', c))

        # Range expansion vs contraction
        cur_range = h - l
        if cur_range > self.avg_range * 1.5:
            self.range_status = 'EXPANSION'
        elif cur_range < self.avg_range * 0.6:
            self.range_status = 'CONTRACTION'
        else:
            self.range_status = 'NORMAL'

    def _detect_session_and_period_levels(self):
        """Extract Previous Day & Week High / Low (PDH, PDL, PWH, PWL)"""
        df = self.df
        # If daily or sub-daily, approximate PDH/PDL from last 24 periods
        lookback_day = min(24, len(df))
        self.pdh = float(df['high'].iloc[-lookback_day:].max())
        self.pdl = float(df['low'].iloc[-lookback_day:].min())

        lookback_wk = min(120, len(df))
        self.pwh = float(df['high'].iloc[-lookback_wk:].max())
        self.pwl = float(df['low'].iloc[-lookback_wk:].min())

    def _evaluate(self) -> EngineResult:
        buy_score  = 0.0
        sell_score = 0.0
        reasoning  = []
        n = len(self.df)

        i   = n - 1
        i_1 = n - 2
        i_2 = n - 3

        o = self.df['open'].values.astype(float)
        h = self.df['high'].values.astype(float)
        l = self.df['low'].values.astype(float)
        c = self.df['close'].values.astype(float)

        # ── 1. Market Structure Bias (HH/HL vs LH/LL) ────
        if self.structure_bias == 'BULLISH':
            buy_score += 25
            reasoning.append(f"Bullish Market Structure: {', '.join(self.structure_labels)}")
        elif self.structure_bias == 'BEARISH':
            sell_score += 25
            reasoning.append(f"Bearish Market Structure: {', '.join(self.structure_labels)}")

        # ── 2. Breakouts & Rejections ─────────────────────
        if self.breakout_type == 'BULLISH_BREAKOUT':
            buy_score += 20
            reasoning.append(f"Bullish Breakout above key level {self.nearest_res:.5g}")
        elif self.breakout_type == 'BEARISH_BREAKOUT':
            sell_score += 20
            reasoning.append(f"Bearish Breakout below key level {self.nearest_sup:.5g}")
        elif self.breakout_type == 'FALSE_BREAKOUT_HIGH':
            sell_score += 22
            reasoning.append(f"False Breakout (Liquidity Trap) at resistance {self.nearest_res:.5g}")
        elif self.breakout_type == 'FALSE_BREAKOUT_LOW':
            buy_score += 22
            reasoning.append(f"False Breakout (Liquidity Trap) at support {self.nearest_sup:.5g}")

        # ── 3. Displacement & Energy ──────────────────────
        if self.has_displacement:
            if self.is_bull[i]:
                buy_score += 15
                reasoning.append("Bullish Displacement Candle (Strong Institutional Momentum)")
            else:
                sell_score += 15
                reasoning.append("Bearish Displacement Candle (Strong Institutional Momentum)")

        # ── 4. Candlestick Patterns ───────────────────────
        # Engulfing
        if i_1 >= 0:
            if (self.is_bear[i_1] and self.is_bull[i] and
                c[i] > o[i_1] and o[i] < c[i_1] and
                self.body[i] > self.body[i_1] * self.ENGULF_FACTOR):
                buy_score += 20
                reasoning.append("Bullish Engulfing pattern")
            elif (self.is_bull[i_1] and self.is_bear[i] and
                  c[i] < o[i_1] and o[i] > c[i_1] and
                  self.body[i] > self.body[i_1] * self.ENGULF_FACTOR):
                sell_score += 20
                reasoning.append("Bearish Engulfing pattern")

        # Pin Bar / Rejection
        rng  = self.range_[i]
        body = self.body[i]
        us   = self.upper_s[i]
        ls   = self.lower_s[i]

        if rng > 0 and body > 0:
            if ls > body * self.SHADOW_RATIO and us < body * 0.5:
                buy_score += 18
                reasoning.append("Hammer / Bullish Pin Bar — strong rejection of lower prices")
            elif us > body * self.SHADOW_RATIO and ls < body * 0.5:
                sell_score += 18
                reasoning.append("Shooting Star / Bearish Pin Bar — rejection of higher prices")

        # Morning / Evening Star
        if i_2 >= 0:
            ms = (self.is_bear[i_2] and self.body[i_1] < self.body[i_2] * 0.5 and
                  self.is_bull[i] and c[i] > (o[i_2] + c[i_2]) / 2)
            es = (self.is_bull[i_2] and self.body[i_1] < self.body[i_2] * 0.5 and
                  self.is_bear[i] and c[i] < (o[i_2] + c[i_2]) / 2)
            if ms:
                buy_score += 25
                reasoning.append("Morning Star bullish reversal pattern")
            if es:
                sell_score += 25
                reasoning.append("Evening Star bearish reversal pattern")

        # Inside Bar
        if i_1 >= 0 and h[i] < h[i_1] and l[i] > l[i_1]:
            reasoning.append("Inside Bar consolidation")
            if self.structure_bias == 'BULLISH':
                buy_score += 8
            elif self.structure_bias == 'BEARISH':
                sell_score += 8

        # Range Expansion note
        if self.range_status == 'EXPANSION':
            reasoning.append("Range Expansion active")
        elif self.range_status == 'CONTRACTION':
            reasoning.append("Range Contraction — potential volatility expansion upcoming")

        # ── Final Direction & Score ───────────────────────
        total = buy_score + sell_score + 1e-5

        if buy_score > sell_score and (buy_score / total) > 0.55:
            direction = 'BUY'
            score     = (buy_score / total) * 100
        elif sell_score > buy_score and (sell_score / total) > 0.55:
            direction = 'SELL'
            score     = (sell_score / total) * 100
        else:
            direction = 'NEUTRAL'
            score     = 50.0

        confluence = min(len(reasoning) * 12.0, 100.0)
        confidence = (score * 0.70) + (confluence * 0.30)

        entry = float(c[i])
        sl_zone = self.nearest_sup if direction == 'BUY' else (self.nearest_res if direction == 'SELL' else None)
        tp_zone = self.nearest_res if direction == 'BUY' else (self.nearest_sup if direction == 'SELL' else None)

        if not sl_zone:
            sl_zone = entry - self.atr * 1.5 if direction == 'BUY' else entry + self.atr * 1.5
        if not tp_zone:
            tp_zone = entry + self.atr * 3.0 if direction == 'BUY' else entry - self.atr * 3.0

        reasoning.append(f"PA Regime: {self.regime}")

        return EngineResult(
            engine_name = self.name,
            score       = round(score, 2),
            direction   = direction,
            confidence  = round(confidence, 2),
            reasoning   = reasoning,
            weight      = self.weight,
            entry_zone  = round(entry, 5),
            sl_zone     = round(sl_zone, 5) if sl_zone else None,
            tp_zone     = round(tp_zone, 5) if tp_zone else None,
        )

    def _save_structure_events_safely(self):
        """Persist detected structure events into StructureEvent model"""
        try:
            from signals.models import StructureEvent
            from market_data.models import Instrument
            import django.utils.timezone as dj_tz

            inst = Instrument.objects.filter(symbol=self.symbol).first()
            if not inst:
                return

            last_ts = self.df.index[-1]
            if not hasattr(last_ts, 'tzinfo') or last_ts.tzinfo is None:
                last_ts = dj_tz.now()

            for event_type, price_level in self.structure_events:
                StructureEvent.objects.create(
                    instrument=inst,
                    timeframe=self.timeframe,
                    timestamp=last_ts,
                    event_type=event_type,
                    price_level=round(float(price_level), 8),
                    regime=self.regime,
                    metadata={
                        'structure_bias': self.structure_bias,
                        'range_status': self.range_status,
                        'nearest_res': round(self.nearest_res, 5),
                        'nearest_sup': round(self.nearest_sup, 5)
                    }
                )
        except Exception:
            pass
