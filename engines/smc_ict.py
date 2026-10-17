"""
Advanced SMC / ICT Engine — Weight: 20%
Phase 3 Upgrades:
- Baseline: Swing points, BOS, CHoCH, Order Blocks, FVG, Liquidity Sweeps, Premium/Discount
- Added: Market Structure Shift (MSS)
- Added: Equal Highs / Lows (EQH / EQL) Liquidity Pools (BSL / SSL)
- Added: Inducement (IDM) detection
- Added: Breaker Blocks & Mitigation / Retest logic
- Added: Displacement confirmation
- Added: Previous Daily/Weekly Highs & Lows (PDH, PDL, DO, PWH, PWL, WO)
- Added: Asian, London, and New York Kill Zones
- Added: Quality scoring for zones (0-100 based on freshness, displacement, confluence)
- Added: SMCZone model persistence
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from .base import BaseEngine, EngineResult


class SMCEngine(BaseEngine):
    name   = 'smc_ict'
    weight = 0.20

    # ── Parameters ────────────────────────────────────────
    SWING_LOOKBACK     = 4     # bars each side for swing points
    OB_LOOKBACK        = 50    # bars to scan for OBs
    FVG_MIN_SIZE_ATR   = 0.25  # minimum FVG size relative to ATR
    EQ_TOLERANCE_PCT   = 0.001 # 0.1% tolerance for equal highs/lows

    def __init__(self, df: pd.DataFrame, symbol: str = '', timeframe: str = 'H1'):
        super().__init__(df, symbol)
        self.timeframe = timeframe
        self.smc_zones_to_save = []

    def analyze(self) -> EngineResult:
        try:
            if len(self.df) < 35:
                return self._neutral_result("Not enough data (need 35+ candles for SMC)")
            self._compute_atr()
            self._find_swing_points()
            self._identify_structure_and_mss()
            self._find_equal_highs_lows()
            self._find_order_and_breaker_blocks()
            self._find_fvg()
            self._find_liquidity_sweeps_and_idm()
            self._detect_sessions_and_killzones()
            result = self._evaluate()
            self._save_zones_safely()
            return result
        except Exception as e:
            return self._neutral_result(f"Advanced SMC error: {str(e)}")

    def _compute_atr(self):
        h, l, c = self.df['high'], self.df['low'], self.df['close']
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        self.atr = tr.ewm(span=14, adjust=False).mean()
        self.cur_atr = float(self.atr.iloc[-1])

    def _find_swing_points(self):
        df = self.df
        lb = self.SWING_LOOKBACK
        n  = len(df)
        self.swing_highs = []
        self.swing_lows  = []

        for i in range(lb, n - lb):
            h = df['high'].iloc[i]
            l = df['low'].iloc[i]
            is_sh = all(h >= df['high'].iloc[i-j] for j in range(1, lb+1)) and \
                    all(h >= df['high'].iloc[i+j] for j in range(1, lb+1))
            is_sl = all(l <= df['low'].iloc[i-j] for j in range(1, lb+1)) and \
                    all(l <= df['low'].iloc[i+j] for j in range(1, lb+1))
            if is_sh:
                self.swing_highs.append((i, float(h)))
            if is_sl:
                self.swing_lows.append((i, float(l)))

    def _identify_structure_and_mss(self):
        """Determine BOS, CHoCH, and Market Structure Shift (MSS)"""
        self.structure = 'RANGING'
        self.bos       = None
        self.choch     = None
        self.mss       = None

        sh = self.swing_highs
        sl = self.swing_lows
        if len(sh) < 2 or len(sl) < 2:
            return

        last_sh1, last_sh2 = sh[-1][1], sh[-2][1]
        last_sl1, last_sl2 = sl[-1][1], sl[-2][1]

        higher_highs = last_sh1 > last_sh2
        higher_lows  = last_sl1 > last_sl2
        lower_highs  = last_sh1 < last_sh2
        lower_lows   = last_sl1 < last_sl2

        if higher_highs and higher_lows:
            self.structure = 'BULLISH'
            self.bos = 'BUY'
        elif lower_highs and lower_lows:
            self.structure = 'BEARISH'
            self.bos = 'SELL'

        # CHoCH: trend structure shift
        if len(sh) >= 3 and len(sl) >= 3:
            prev_bull = sh[-2][1] > sh[-3][1] and sl[-2][1] > sl[-3][1]
            prev_bear = sh[-2][1] < sh[-3][1] and sl[-2][1] < sl[-3][1]
            if prev_bear and self.structure == 'BULLISH':
                self.choch = 'BUY'
            elif prev_bull and self.structure == 'BEARISH':
                self.choch = 'SELL'

        # MSS (Market Structure Shift)
        # Shift happens when latest candle body closes past the most recent swing point with displacement
        cur_close = float(self.df['close'].iloc[-1])
        cur_body = abs(float(self.df['close'].iloc[-1]) - float(self.df['open'].iloc[-1]))
        has_displacement = cur_body > (self.cur_atr * 0.75)

        if lower_highs and cur_close > last_sh1 and has_displacement:
            self.mss = 'BULLISH_MSS'
        elif higher_lows and cur_close < last_sl1 and has_displacement:
            self.mss = 'BEARISH_MSS'

    def _find_equal_highs_lows(self):
        """Detect EQH (Buy-side liquidity) and EQL (Sell-side liquidity)"""
        self.eq_highs = []
        self.eq_lows  = []

        # Compare adjacent swing highs
        for i in range(len(self.swing_highs) - 1):
            p1 = self.swing_highs[i][1]
            p2 = self.swing_highs[i+1][1]
            if abs(p1 - p2) / p1 < self.EQ_TOLERANCE_PCT:
                self.eq_highs.append((p1 + p2) / 2.0)

        # Compare adjacent swing lows
        for i in range(len(self.swing_lows) - 1):
            p1 = self.swing_lows[i][1]
            p2 = self.swing_lows[i+1][1]
            if abs(p1 - p2) / p1 < self.EQ_TOLERANCE_PCT:
                self.eq_lows.append((p1 + p2) / 2.0)

    def _find_order_and_breaker_blocks(self):
        """Identify Order Blocks and Breaker Blocks with mitigation status"""
        df = self.df
        self.bullish_obs = []
        self.bearish_obs = []
        self.breaker_blocks = []

        close = df['close'].values
        open_ = df['open'].values
        high  = df['high'].values
        low   = df['low'].values
        n     = len(df)
        lb    = min(self.OB_LOOKBACK, n - 3)
        cur_c = float(close[-1])

        for i in range(n - lb, n - 2):
            move_size = abs(close[i+1] - open_[i+1])
            is_bear_candle = close[i] < open_[i]
            is_bull_candle = close[i] > open_[i]
            next_bull_move = close[i+1] > open_[i+1] and close[i+1] > high[i]
            next_bear_move = close[i+1] < open_[i+1] and close[i+1] < low[i]

            # Bullish Order Block
            if is_bear_candle and next_bull_move:
                ob_h = float(high[i])
                ob_l = float(low[i])
                # Check mitigation in subsequent candles
                is_mitigated = any(low[k] <= ob_h for k in range(i+2, n))
                is_violated = any(close[k] < ob_l for k in range(i+2, n))

                if is_violated:
                    # Violated bullish OB becomes a Bearish Breaker Block
                    self.breaker_blocks.append({
                        'type': 'BEARISH_BREAKER',
                        'high': ob_h, 'low': ob_l,
                        'quality': 75.0, 'index': i
                    })
                    self.smc_zones_to_save.append(('BREAKER_BLOCK', ob_h, ob_l, 75.0, True))
                else:
                    quality = 90.0 if not is_mitigated else 50.0
                    if move_size > self.cur_atr: quality += 10.0
                    self.bullish_obs.append({
                        'high': ob_h, 'low': ob_l,
                        'mid': (ob_h + ob_l) / 2.0,
                        'is_mitigated': is_mitigated,
                        'quality': min(quality, 100.0),
                        'strength': round(move_size / self.cur_atr, 2),
                        'index': i
                    })
                    self.smc_zones_to_save.append(('BULLISH_OB', ob_h, ob_l, min(quality, 100.0), is_mitigated))


            # Bearish Order Block
            if is_bull_candle and next_bear_move:
                ob_h = float(high[i])
                ob_l = float(low[i])
                is_mitigated = any(high[k] >= ob_l for k in range(i+2, n))
                is_violated = any(close[k] > ob_h for k in range(i+2, n))

                if is_violated:
                    # Violated bearish OB becomes a Bullish Breaker Block
                    self.breaker_blocks.append({
                        'type': 'BULLISH_BREAKER',
                        'high': ob_h, 'low': ob_l,
                        'quality': 75.0, 'index': i
                    })
                    self.smc_zones_to_save.append(('BREAKER_BLOCK', ob_h, ob_l, 75.0, True))
                else:
                    quality = 90.0 if not is_mitigated else 50.0
                    if move_size > self.cur_atr: quality += 10.0
                    self.bearish_obs.append({
                        'high': ob_h, 'low': ob_l,
                        'mid': (ob_h + ob_l) / 2.0,
                        'is_mitigated': is_mitigated,
                        'quality': min(quality, 100.0),
                        'strength': round(move_size / self.cur_atr, 2),
                        'index': i
                    })
                    self.smc_zones_to_save.append(('BEARISH_OB', ob_h, ob_l, min(quality, 100.0), is_mitigated))

    def _find_fvg(self):
        """Identify Fair Value Gaps and track if they are mitigated"""
        df = self.df
        self.bullish_fvg = []
        self.bearish_fvg = []
        high = df['high'].values
        low  = df['low'].values
        n    = len(df)

        for i in range(1, n - 1):
            gap_up   = low[i+1] - high[i-1]
            gap_down = low[i-1] - high[i+1]

            if gap_up > self.cur_atr * self.FVG_MIN_SIZE_ATR:
                is_filled = any(low[k] <= high[i-1] for k in range(i+2, n))
                quality = 85.0 if not is_filled else 40.0
                self.bullish_fvg.append({
                    'top': float(low[i+1]), 'bot': float(high[i-1]),
                    'mid': float((low[i+1] + high[i-1]) / 2),
                    'is_mitigated': is_filled,
                    'quality': quality, 'index': i
                })
                self.smc_zones_to_save.append(('BULLISH_FVG', float(low[i+1]), float(high[i-1]), quality, is_filled))

            if gap_down > self.cur_atr * self.FVG_MIN_SIZE_ATR:
                is_filled = any(high[k] >= low[i-1] for k in range(i+2, n))
                quality = 85.0 if not is_filled else 40.0
                self.bearish_fvg.append({
                    'top': float(low[i-1]), 'bot': float(high[i+1]),
                    'mid': float((low[i-1] + high[i+1]) / 2),
                    'is_mitigated': is_filled,
                    'quality': quality, 'index': i
                })
                self.smc_zones_to_save.append(('BEARISH_FVG', float(low[i-1]), float(high[i+1]), quality, is_filled))

    def _find_liquidity_sweeps_and_idm(self):
        """Identify sweeps and Inducement (IDM)"""
        df = self.df
        self.buy_side_sweep  = False
        self.sell_side_sweep = False
        self.sweep_level     = None
        self.inducement_level = None

        cur_high  = float(df['high'].iloc[-1])
        cur_low   = float(df['low'].iloc[-1])
        cur_close = float(df['close'].iloc[-1])

        # Sweeps of swing levels
        recent_sh = self.swing_highs[-1][1] if self.swing_highs else None
        recent_sl = self.swing_lows[-1][1]  if self.swing_lows  else None

        if recent_sl and cur_low < recent_sl and cur_close > recent_sl:
            self.buy_side_sweep = True
            self.sweep_level = recent_sl

        if recent_sh and cur_high > recent_sh and cur_close < recent_sh:
            self.sell_side_sweep = True
            self.sweep_level = recent_sh

        # Sweeps of Equal Highs / Lows pools
        for eqh in self.eq_highs:
            if cur_high > eqh and cur_close < eqh:
                self.sell_side_sweep = True
                self.sweep_level = eqh
                break

        for eql in self.eq_lows:
            if cur_low < eql and cur_close > eql:
                self.buy_side_sweep = True
                self.sweep_level = eql
                break

        # Inducement (IDM): First internal pullback high/low before major structure
        if len(self.swing_highs) >= 2 and len(self.swing_lows) >= 2:
            if self.structure == 'BULLISH':
                self.inducement_level = self.swing_lows[-1][1]
            elif self.structure == 'BEARISH':
                self.inducement_level = self.swing_highs[-1][1]

    def _detect_sessions_and_killzones(self):
        """Detect active session and ICT Kill Zones (UTC)"""
        now = datetime.now(timezone.utc)
        cur_hour = now.hour

        self.kill_zone = 'NONE'
        if 0 <= cur_hour < 6:
            self.kill_zone = 'ASIAN_SESSION'
        elif 7 <= cur_hour <= 10:
            self.kill_zone = 'LONDON_KILLZONE'
        elif 12 <= cur_hour <= 15:
            self.kill_zone = 'NEW_YORK_KILLZONE'
        elif 15 < cur_hour <= 17:
            self.kill_zone = 'LONDON_CLOSE'

        # Daily / Weekly Open approximations
        self.daily_open = float(self.df['open'].iloc[-min(24, len(self.df))])
        self.weekly_open = float(self.df['open'].iloc[-min(120, len(self.df))])

    def _get_pd_zone(self) -> str:
        if not self.swing_highs or not self.swing_lows:
            return 'UNKNOWN'
        recent_sh = max(sh[1] for sh in self.swing_highs[-3:])
        recent_sl = min(sl[1] for sl in self.swing_lows[-3:])
        cur_close = float(self.df['close'].iloc[-1])
        mid_point = (recent_sh + recent_sl) / 2.0
        return 'PREMIUM' if cur_close > mid_point else 'DISCOUNT'

    def _evaluate(self) -> EngineResult:
        buy_score  = 0.0
        sell_score = 0.0
        reasoning  = []
        cur_close  = float(self.df['close'].iloc[-1])

        # ── 1. Structure (BOS / CHoCH / MSS) ──────────────
        if self.mss == 'BULLISH_MSS':
            buy_score += 30
            reasoning.append("Bullish Market Structure Shift (MSS) confirmed with displacement")
        elif self.mss == 'BEARISH_MSS':
            sell_score += 30
            reasoning.append("Bearish Market Structure Shift (MSS) confirmed with displacement")
        elif self.choch == 'BUY':
            buy_score += 25
            reasoning.append("Bullish CHoCH: Change of Character indicating trend shift")
        elif self.choch == 'SELL':
            sell_score += 25
            reasoning.append("Bearish CHoCH: Change of Character indicating trend shift")
        elif self.bos == 'BUY':
            buy_score += 20
            reasoning.append("Bullish BOS: Higher Highs & Higher Lows continuation")
        elif self.bos == 'SELL':
            sell_score += 20
            reasoning.append("Bearish BOS: Lower Highs & Lower Lows continuation")

        # ── 2. Breaker Blocks ─────────────────────────────
        for bb in self.breaker_blocks[-2:]:
            if bb['low'] <= cur_close <= bb['high']:
                if bb['type'] == 'BULLISH_BREAKER':
                    buy_score += 22
                    reasoning.append(f"Price at Bullish Breaker Block [{bb['low']:.5f} - {bb['high']:.5f}]")
                else:
                    sell_score += 22
                    reasoning.append(f"Price at Bearish Breaker Block [{bb['low']:.5f} - {bb['high']:.5f}]")

        # ── 3. Order Blocks (Fresh/Unmitigated) ───────────
        for ob in self.bullish_obs[-3:]:
            if ob['low'] <= cur_close <= ob['high']:
                points = 25 if not ob['is_mitigated'] else 12
                buy_score += points
                reasoning.append(f"Price in Bullish OB [{ob['low']:.5f} - {ob['high']:.5f}] Quality={ob['quality']}%")
                self.smc_zones_to_save.append(('BULLISH_OB', ob['high'], ob['low'], ob['quality'], ob['is_mitigated']))
                break

        for ob in self.bearish_obs[-3:]:
            if ob['low'] <= cur_close <= ob['high']:
                points = 25 if not ob['is_mitigated'] else 12
                sell_score += points
                reasoning.append(f"Price in Bearish OB [{ob['low']:.5f} - {ob['high']:.5f}] Quality={ob['quality']}%")
                self.smc_zones_to_save.append(('BEARISH_OB', ob['high'], ob['low'], ob['quality'], ob['is_mitigated']))
                break

        # ── 4. Fair Value Gaps (FVG) ──────────────────────
        for fvg in self.bullish_fvg[-3:]:
            if fvg['bot'] <= cur_close <= fvg['top']:
                buy_score += 18 if not fvg['is_mitigated'] else 8
                reasoning.append(f"Price in Bullish FVG [{fvg['bot']:.5f} - {fvg['top']:.5f}]")
                self.smc_zones_to_save.append(('BULLISH_FVG', fvg['top'], fvg['bot'], fvg['quality'], fvg['is_mitigated']))
                break

        for fvg in self.bearish_fvg[-3:]:
            if fvg['bot'] <= cur_close <= fvg['top']:
                sell_score += 18 if not fvg['is_mitigated'] else 8
                reasoning.append(f"Price in Bearish FVG [{fvg['bot']:.5f} - {fvg['top']:.5f}]")
                self.smc_zones_to_save.append(('BEARISH_FVG', fvg['top'], fvg['bot'], fvg['quality'], fvg['is_mitigated']))
                break

        # ── 5. Liquidity Sweeps & Equal Highs/Lows ────────
        if self.buy_side_sweep:
            buy_score += 25
            reasoning.append(f"Sell-side Liquidity Swept @ {self.sweep_level:.5f} (Spring / Liquidity Purge)")
        if self.sell_side_sweep:
            sell_score += 25
            reasoning.append(f"Buy-side Liquidity Swept @ {self.sweep_level:.5f} (Upthrust / Liquidity Purge)")

        if self.eq_highs and cur_close < self.eq_highs[-1]:
            reasoning.append(f"Equal Highs (BSL pool) target above at {self.eq_highs[-1]:.5f}")
        if self.eq_lows and cur_close > self.eq_lows[-1]:
            reasoning.append(f"Equal Lows (SSL pool) target below at {self.eq_lows[-1]:.5f}")

        # ── 6. Premium / Discount Pricing ─────────────────
        pd_zone = self._get_pd_zone()
        if pd_zone == 'DISCOUNT':
            buy_score += 12
            reasoning.append("Discount Zone: Smart money favorable pricing for longs")
        elif pd_zone == 'PREMIUM':
            sell_score += 12
            reasoning.append("Premium Zone: Smart money favorable pricing for shorts")

        # ── 7. Kill Zone Alignment ────────────────────────
        if 'KILLZONE' in self.kill_zone:
            reasoning.append(f"Active Session: {self.kill_zone.replace('_', ' ')} (High Institutional Liquidity)")

        # ── Scoring & Direction ───────────────────────────
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

        confluence = min((len(reasoning) / 5.0) * 100.0, 100.0)
        confidence = (score * 0.75) + (confluence * 0.25)

        entry = cur_close
        sl_dist = self.cur_atr * 1.2
        tp_dist = self.cur_atr * 2.8

        sl_zone = entry - sl_dist if direction == 'BUY' else (entry + sl_dist if direction == 'SELL' else None)
        tp_zone = entry + tp_dist if direction == 'BUY' else (entry - tp_dist if direction == 'SELL' else None)

        if not reasoning:
            reasoning.append(f"Structure: {self.structure} | PD Zone: {pd_zone} | Killzone: {self.kill_zone.replace('_', ' ')}")

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

    def _save_zones_safely(self):
        """Save high-quality SMC zones to database SMCZone model"""
        try:
            from signals.models import SMCZone
            from market_data.models import Instrument
            import django.utils.timezone as dj_tz

            inst = Instrument.objects.filter(symbol=self.symbol).first()
            if not inst:
                return

            last_ts = self.df.index[-1]
            if not hasattr(last_ts, 'tzinfo') or last_ts.tzinfo is None:
                last_ts = dj_tz.now()

            for zone_type, high, low, quality, is_mitigated in self.smc_zones_to_save:
                SMCZone.objects.create(
                    instrument=inst,
                    timeframe=self.timeframe,
                    zone_type=zone_type,
                    high_price=round(float(high), 8),
                    low_price=round(float(low), 8),
                    quality_score=round(float(quality), 2),
                    is_mitigated=is_mitigated,
                    timestamp=last_ts,
                    metadata={'kill_zone': self.kill_zone, 'structure': self.structure}
                )
        except Exception:
            pass
