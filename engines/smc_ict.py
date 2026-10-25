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
        self.bullish_obs = []
        self.bearish_obs = []
        self.breaker_blocks = []
        self.bullish_fvg = []
        self.bearish_fvg = []
        self.eq_highs = []
        self.eq_lows = []
        self.swing_highs = []
        self.swing_lows = []
        self.structure = 'RANGING'
        self.bos = None
        self.choch = None
        self.mss = None
        self.buy_side_sweep = False
        self.sell_side_sweep = False
        self.sweep_level = None
        self.inducement_level = None
        self.kill_zone = 'NONE'
        self.silver_bullet = 'INACTIVE'
        self.judas_swing = None
        self.ote_levels = {}
        self.is_in_ote_zone = False
        self.ote_direction = None
        self.liquidity_map = {'bsl_pools': [], 'ssl_pools': [], 'nearest_bsl': None, 'nearest_ssl': None}
        self.draw_on_liquidity = None
        self.liquidity_trap = None
        self.ict_2022_model = {
            'is_active': False,
            'direction': 'NEUTRAL',
            'checklist': {},
            'confidence': 0.0,
            'description': 'No 2022 ICT Mentorship model currently active'
        }

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
            self._map_liquidity_pools_and_dol()
            self._detect_ote_and_2022_model()
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
                    mt_level = (ob_h + ob_l) / 2.0
                    self.bullish_obs.append({
                        'high': ob_h, 'low': ob_l,
                        'mid': mt_level,
                        'mean_threshold_mt': mt_level,
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
                    mt_level = (ob_h + ob_l) / 2.0
                    self.bearish_obs.append({
                        'high': ob_h, 'low': ob_l,
                        'mid': mt_level,
                        'mean_threshold_mt': mt_level,
                        'is_mitigated': is_mitigated,
                        'quality': min(quality, 100.0),
                        'strength': round(move_size / self.cur_atr, 2),
                        'index': i
                    })
                    self.smc_zones_to_save.append(('BEARISH_OB', ob_h, ob_l, min(quality, 100.0), is_mitigated))

    def _find_fvg(self):
        """Identify Fair Value Gaps (BISI / SIBI) and Consequent Encroachment (CE 50%)"""
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
                ce_level = float((low[i+1] + high[i-1]) / 2) # Consequent Encroachment (CE 50%)
                self.bullish_fvg.append({
                    'top': float(low[i+1]), 'bot': float(high[i-1]),
                    'mid': ce_level,
                    'consequent_encroachment_ce': ce_level,
                    'type': 'BISI', # Buy-side Imbalance Sell-side Inefficiency
                    'is_mitigated': is_filled,
                    'quality': quality, 'index': i
                })
                self.smc_zones_to_save.append(('BULLISH_FVG', float(low[i+1]), float(high[i-1]), quality, is_filled))

            if gap_down > self.cur_atr * self.FVG_MIN_SIZE_ATR:
                is_filled = any(high[k] >= low[i-1] for k in range(i+2, n))
                quality = 85.0 if not is_filled else 40.0
                ce_level = float((low[i-1] + high[i+1]) / 2) # Consequent Encroachment (CE 50%)
                self.bearish_fvg.append({
                    'top': float(low[i-1]), 'bot': float(high[i+1]),
                    'mid': ce_level,
                    'consequent_encroachment_ce': ce_level,
                    'type': 'SIBI', # Sell-side Imbalance Buy-side Inefficiency
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
        """Detect active session, ICT Kill Zones & Silver Bullet Windows (UTC)"""
        now = datetime.now(timezone.utc)
        cur_hour = now.hour

        self.kill_zone = 'NONE'
        self.silver_bullet = 'INACTIVE'
        self.judas_swing = None

        # Standard ICT Killzones (UTC)
        if 0 <= cur_hour < 6:
            self.kill_zone = 'ASIAN_SESSION'
        elif 7 <= cur_hour <= 10:
            self.kill_zone = 'LONDON_KILLZONE'
        elif 12 <= cur_hour <= 15:
            self.kill_zone = 'NEW_YORK_KILLZONE'
        elif 15 < cur_hour <= 17:
            self.kill_zone = 'LONDON_CLOSE'

        # ICT Silver Bullet Windows (YouTube 2023 Masterclass)
        # 1. London Silver Bullet: 03:00 - 04:00 AM NY (08:00 - 09:00 UTC)
        # 2. NY AM Silver Bullet: 10:00 - 11:00 AM NY (15:00 - 16:00 UTC)
        # 3. NY PM Silver Bullet: 14:00 - 15:00 PM NY (19:00 - 20:00 UTC)
        if 8 <= cur_hour < 9:
            self.silver_bullet = 'LONDON_SILVER_BULLET (03:00-04:00 AM NY)'
        elif 15 <= cur_hour < 16:
            self.silver_bullet = 'NY_AM_SILVER_BULLET (10:00-11:00 AM NY)'
        elif 19 <= cur_hour < 20:
            self.silver_bullet = 'NY_PM_SILVER_BULLET (14:00-15:00 PM NY)'

        # Judas Swing Detection (London Open or NY Open false breakout manipulation)
        if (7 <= cur_hour <= 9 or 12 <= cur_hour <= 14):
            if self.sell_side_sweep and self.structure != 'BULLISH':
                self.judas_swing = 'BEARISH_JUDAS_SWING (False upward expansion sweeping liquidity before true drop)'
            elif self.buy_side_sweep and self.structure != 'BEARISH':
                self.judas_swing = 'BULLISH_JUDAS_SWING (False downward raid sweeping liquidity before true rally)'

        # Daily / Weekly Open approximations
        self.daily_open = float(self.df['open'].iloc[-min(24, len(self.df))])
        self.weekly_open = float(self.df['open'].iloc[-min(120, len(self.df))])

    def _map_liquidity_pools_and_dol(self):
        """
        Locates exact resting Liquidity Pools (BSL & SSL) and defines the Draw on Liquidity (DOL):
        1. BSL Pools (Resting Buy Stops above peaks):
           - Equal Highs (EQH - Double/Triple top retail stop cluster)
           - Previous Day High (PDH)
           - Previous Week High (PWH)
           - Asian Session High
           - Swing Highs
        2. SSL Pools (Resting Sell Stops below troughs):
           - Equal Lows (EQL - Double/Triple bottom retail stop cluster)
           - Previous Day Low (PDL)
           - Previous Week Low (PWL)
           - Asian Session Low
           - Swing Lows
        3. Liquidity Trap Protection:
           - NEVER BUY directly under a major BSL pool (institutions sell into breakout retail).
           - NEVER SELL directly above a major SSL pool (institutions buy into breakdown retail).
        4. Draw on Liquidity (DOL):
           - The exact magnet pool where price is drawn for Take Profit.
        """
        df = self.df
        cur_c = float(df['close'].iloc[-1])
        h = df['high'].values.astype(float)
        l = df['low'].values.astype(float)
        n = len(df)

        bsl_candidates = []
        ssl_candidates = []

        # 1. Equal Highs & Equal Lows (Highest Quality Liquidity Pools)
        for eqh in self.eq_highs:
            if eqh > cur_c:
                bsl_candidates.append({'type': 'Equal Highs (EQH)', 'price': float(eqh), 'quality': 95.0})
        for eql in self.eq_lows:
            if eql < cur_c:
                ssl_candidates.append({'type': 'Equal Lows (EQL)', 'price': float(eql), 'quality': 95.0})

        # 2. Previous Day High (PDH) & Previous Day Low (PDL)
        lookback_day = min(24, n)
        pdh = float(np.max(h[-lookback_day:]))
        pdl = float(np.min(l[-lookback_day:]))
        if pdh > cur_c:
            bsl_candidates.append({'type': 'Previous Day High (PDH)', 'price': pdh, 'quality': 90.0})
        if pdl < cur_c:
            ssl_candidates.append({'type': 'Previous Day Low (PDL)', 'price': pdl, 'quality': 90.0})

        # 3. Previous Week High (PWH) & Low (PWL)
        lookback_wk = min(120, n)
        pwh = float(np.max(h[-lookback_wk:]))
        pwl = float(np.min(l[-lookback_wk:]))
        if pwh > cur_c:
            bsl_candidates.append({'type': 'Previous Week High (PWH)', 'price': pwh, 'quality': 92.0})
        if pwl < cur_c:
            ssl_candidates.append({'type': 'Previous Week Low (PWL)', 'price': pwl, 'quality': 92.0})

        # 4. Asian Session High & Low (approx 00:00 - 05:00 UTC)
        lookback_asian = min(12, n)
        asian_h = float(np.max(h[-lookback_asian:]))
        asian_l = float(np.min(l[-lookback_asian:]))
        if asian_h > cur_c and abs(asian_h - pdh) > (self.cur_atr * 0.2):
            bsl_candidates.append({'type': 'Asian Range High', 'price': asian_h, 'quality': 85.0})
        if asian_l < cur_c and abs(asian_l - pdl) > (self.cur_atr * 0.2):
            ssl_candidates.append({'type': 'Asian Range Low', 'price': asian_l, 'quality': 85.0})

        # 5. Major Swing Highs & Lows
        for idx, sh_p in self.swing_highs[-4:]:
            if sh_p > cur_c and not any(abs(sh_p - b['price']) < (self.cur_atr * 0.15) for b in bsl_candidates):
                bsl_candidates.append({'type': 'Swing High Liquidity', 'price': sh_p, 'quality': 80.0})
        for idx, sl_p in self.swing_lows[-4:]:
            if sl_p < cur_c and not any(abs(sl_p - s['price']) < (self.cur_atr * 0.15) for s in ssl_candidates):
                ssl_candidates.append({'type': 'Swing Low Liquidity', 'price': sl_p, 'quality': 80.0})

        # 6. Live Institutional Level-2 Order Book Walls (E.g. CME / Binance Futures / COT Footprint)
        order_book_meta = {}
        try:
            from .institutional_liquidity import InstitutionalLiquidityEngine
            ecn_depth = InstitutionalLiquidityEngine.get_order_book_depth(self.symbol, cur_c, self.cur_atr)
            order_book_meta = {
                'source': ecn_depth.get('source'),
                'imbalance_pct': ecn_depth.get('order_book_imbalance_pct', 0.0),
                'open_interest_usd': ecn_depth.get('open_interest_usd', 0.0),
                'funding_rate_pct': ecn_depth.get('funding_rate_pct', 0.0),
            }
            if ecn_depth.get('nearest_bsl_wall'):
                wall = ecn_depth['nearest_bsl_wall']
                if wall['price'] > cur_c:
                    bsl_candidates.insert(0, {
                        'type': f"{wall['type']} (${wall.get('usd_value', 0):,.0f})",
                        'price': float(wall['price']),
                        'quality': 98.0
                    })
            if ecn_depth.get('nearest_ssl_wall'):
                wall = ecn_depth['nearest_ssl_wall']
                if wall['price'] < cur_c:
                    ssl_candidates.insert(0, {
                        'type': f"{wall['type']} (${wall.get('usd_value', 0):,.0f})",
                        'price': float(wall['price']),
                        'quality': 98.0
                    })
        except Exception:
            pass

        # Sort pools strictly by distance from current price
        bsl_sorted = sorted(bsl_candidates, key=lambda x: x['price'] - cur_c)
        ssl_sorted = sorted(ssl_candidates, key=lambda x: cur_c - x['price'])

        nearest_bsl = bsl_sorted[0] if bsl_sorted else {'type': 'Estimated BSL Target', 'price': cur_c + self.cur_atr * 2.5, 'quality': 50.0}
        nearest_ssl = ssl_sorted[0] if ssl_sorted else {'type': 'Estimated SSL Target', 'price': cur_c - self.cur_atr * 2.5, 'quality': 50.0}

        self.liquidity_map = {
            'bsl_pools': bsl_sorted[:4],
            'ssl_pools': ssl_sorted[:4],
            'nearest_bsl': nearest_bsl,
            'nearest_ssl': nearest_ssl,
            'bsl_distance_atr': round((nearest_bsl['price'] - cur_c) / self.cur_atr, 2),
            'ssl_distance_atr': round((cur_c - nearest_ssl['price']) / self.cur_atr, 2)
        }

        # Liquidity Trap Check
        # If price is within 0.35x ATR of a resting pool, flag a trap!
        self.liquidity_trap = None
        if (nearest_bsl['price'] - cur_c) < (self.cur_atr * 0.35):
            self.liquidity_trap = f"TRAP_WARNING_AT_BSL: Price is directly under {nearest_bsl['type']} ({nearest_bsl['price']:.5f}). High risk of institutional reversal!"
        elif (cur_c - nearest_ssl['price']) < (self.cur_atr * 0.35):
            self.liquidity_trap = f"TRAP_WARNING_AT_SSL: Price is directly above {nearest_ssl['type']} ({nearest_ssl['price']:.5f}). High risk of institutional reversal!"

    def _detect_ote_and_2022_model(self):
        """
        Michael J. Huddleston (ICT) 2022 Mentorship Model & Optimal Trade Entry (OTE):
        - OTE Fibonacci Retracement: 62% (0.618), 70.5% (The ICT Sweet Spot), 79% (0.786)
        - Consequent Encroachment (CE): 50% midpoint of FVG
        - Mean Threshold (MT): 50% midpoint of Order Block
        - ICT 2022 Mentorship Setup Checklist:
          1. Liquidity Run (BSL or SSL swept)
          2. Energetic Displacement (> 0.70 * ATR)
          3. Market Structure Shift (MSS)
          4. Fair Value Gap (FVG) formed
          5. Price in Discount OTE (for Buy) or Premium OTE (for Sell)
        """
        df = self.df
        cur_c = float(df['close'].iloc[-1])

        self.ote_levels = {}
        self.is_in_ote_zone = False
        self.ote_direction = None
        self.ict_2022_model = {
            'is_active': False,
            'direction': 'NEUTRAL',
            'checklist': {
                'liquidity_swept': False,
                'displacement': False,
                'mss': False,
                'fvg_present': False,
                'in_ote_or_ce': False,
            },
            'confidence': 0.0,
            'description': 'No 2022 ICT Mentorship model currently active'
        }

        if len(self.swing_highs) >= 1 and len(self.swing_lows) >= 1:
            recent_sh = self.swing_highs[-1][1]
            recent_sl = self.swing_lows[-1][1]
            diff = recent_sh - recent_sl

            if diff > 0:
                eq = recent_sl + diff * 0.50

                # Bullish OTE: Retracement from high down into discount
                bull_ote_62 = recent_sh - diff * 0.618
                bull_ote_705 = recent_sh - diff * 0.705  # The ICT Sweet Spot
                bull_ote_79 = recent_sh - diff * 0.786

                # Bearish OTE: Retracement from low up into premium
                bear_ote_62 = recent_sl + diff * 0.618
                bear_ote_705 = recent_sl + diff * 0.705  # The ICT Sweet Spot
                bear_ote_79 = recent_sl + diff * 0.786

                self.ote_levels = {
                    'equilibrium_50': round(eq, 5),
                    'bullish_ote': {
                        'fib_62': round(bull_ote_62, 5),
                        'fib_705_sweet_spot': round(bull_ote_705, 5),
                        'fib_79': round(bull_ote_79, 5)
                    },
                    'bearish_ote': {
                        'fib_62': round(bear_ote_62, 5),
                        'fib_705_sweet_spot': round(bear_ote_705, 5),
                        'fib_79': round(bear_ote_79, 5)
                    }
                }

                if bull_ote_79 <= cur_c <= bull_ote_62:
                    self.is_in_ote_zone = True
                    self.ote_direction = 'BUY'
                elif bear_ote_62 <= cur_c <= bear_ote_79:
                    self.is_in_ote_zone = True
                    self.ote_direction = 'SELL'

        # ICT 2022 Mentorship Model Checklist Verification
        has_sweep = bool(self.buy_side_sweep or self.sell_side_sweep)
        cur_body = abs(float(df['close'].iloc[-1]) - float(df['open'].iloc[-1]))
        has_displacement = cur_body >= (self.cur_atr * 0.70)
        has_mss = bool(self.mss)
        has_bull_fvg = any(not f['is_mitigated'] for f in self.bullish_fvg[-2:])
        has_bear_fvg = any(not f['is_mitigated'] for f in self.bearish_fvg[-2:])

        # Check Consequent Encroachment (CE) proximity
        in_fvg_or_ce = False
        if self.bullish_fvg:
            recent_fvg = self.bullish_fvg[-1]
            if recent_fvg['bot'] <= cur_c <= recent_fvg['top']:
                in_fvg_or_ce = True
        if self.bearish_fvg:
            recent_fvg = self.bearish_fvg[-1]
            if recent_fvg['bot'] <= cur_c <= recent_fvg['top']:
                in_fvg_or_ce = True

        checklist = {
            'liquidity_swept': has_sweep,
            'displacement': has_displacement,
            'mss': has_mss,
            'fvg_present': has_bull_fvg or has_bear_fvg,
            'in_ote_or_ce': self.is_in_ote_zone or in_fvg_or_ce
        }

        matched_count = sum(1 for v in checklist.values() if v)
        confidence = (matched_count / 5.0) * 100.0

        if matched_count >= 3:
            model_dir = 'BUY' if (self.buy_side_sweep or self.mss == 'BULLISH_MSS' or (self.is_in_ote_zone and self.ote_direction == 'BUY')) else 'SELL'
            self.ict_2022_model = {
                'is_active': True,
                'direction': model_dir,
                'checklist': checklist,
                'confidence': confidence,
                'description': f"Michael J. Huddleston 2022 Model ({model_dir}): {matched_count}/5 Confluences Verified"
            }

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

        # ── 2. Michael J. Huddleston 2022 Mentorship Model ─
        if self.ict_2022_model.get('is_active'):
            dir_2022 = self.ict_2022_model['direction']
            if dir_2022 == 'BUY':
                buy_score += 28
                reasoning.append(f"ICT 2022 Mentorship Model Active: Bullish Setup ({self.ict_2022_model['confidence']:.0f}% checklist confirmed)")
            elif dir_2022 == 'SELL':
                sell_score += 28
                reasoning.append(f"ICT 2022 Mentorship Model Active: Bearish Setup ({self.ict_2022_model['confidence']:.0f}% checklist confirmed)")

        # ── 3. Optimal Trade Entry (OTE 70.5% Sweet Spot) ──
        if self.is_in_ote_zone:
            if self.ote_direction == 'BUY':
                buy_score += 22
                sweet_spot = self.ote_levels.get('bullish_ote', {}).get('fib_705_sweet_spot', cur_close)
                reasoning.append(f"ICT Optimal Trade Entry (OTE): Price inside Discount 62%-79% zone (70.5% Sweet Spot @ {sweet_spot:.5f})")
            elif self.ote_direction == 'SELL':
                sell_score += 22
                sweet_spot = self.ote_levels.get('bearish_ote', {}).get('fib_705_sweet_spot', cur_close)
                reasoning.append(f"ICT Optimal Trade Entry (OTE): Price inside Premium 62%-79% zone (70.5% Sweet Spot @ {sweet_spot:.5f})")

        # ── 4. Breaker Blocks ─────────────────────────────
        for bb in self.breaker_blocks[-2:]:
            if bb['low'] <= cur_close <= bb['high']:
                if bb['type'] == 'BULLISH_BREAKER':
                    buy_score += 22
                    reasoning.append(f"Price at Bullish Breaker Block [{bb['low']:.5f} - {bb['high']:.5f}]")
                else:
                    sell_score += 22
                    reasoning.append(f"Price at Bearish Breaker Block [{bb['low']:.5f} - {bb['high']:.5f}]")

        # ── 5. Order Blocks (Fresh/Unmitigated & MT 50%) ───
        for ob in self.bullish_obs[-3:]:
            if ob['low'] <= cur_close <= ob['high']:
                points = 25 if not ob['is_mitigated'] else 12
                buy_score += points
                reasoning.append(f"Price in Bullish OB [{ob['low']:.5f} - {ob['high']:.5f}] Mean Threshold (MT 50%): {ob.get('mean_threshold_mt', ob['mid']):.5f}")
                self.smc_zones_to_save.append(('BULLISH_OB', ob['high'], ob['low'], ob['quality'], ob['is_mitigated']))
                break

        for ob in self.bearish_obs[-3:]:
            if ob['low'] <= cur_close <= ob['high']:
                points = 25 if not ob['is_mitigated'] else 12
                sell_score += points
                reasoning.append(f"Price in Bearish OB [{ob['low']:.5f} - {ob['high']:.5f}] Mean Threshold (MT 50%): {ob.get('mean_threshold_mt', ob['mid']):.5f}")
                self.smc_zones_to_save.append(('BEARISH_OB', ob['high'], ob['low'], ob['quality'], ob['is_mitigated']))
                break

        # ── 6. Fair Value Gaps (FVG) & Consequent Encroachment (CE 50%)
        for fvg in self.bullish_fvg[-3:]:
            if fvg['bot'] <= cur_close <= fvg['top']:
                buy_score += 20 if not fvg['is_mitigated'] else 8
                ce_val = fvg.get('consequent_encroachment_ce', fvg['mid'])
                reasoning.append(f"Price in Bullish FVG (BISI) [{fvg['bot']:.5f} - {fvg['top']:.5f}] Consequent Encroachment (CE 50%): {ce_val:.5f}")
                self.smc_zones_to_save.append(('BULLISH_FVG', fvg['top'], fvg['bot'], fvg['quality'], fvg['is_mitigated']))
                break

        for fvg in self.bearish_fvg[-3:]:
            if fvg['bot'] <= cur_close <= fvg['top']:
                sell_score += 20 if not fvg['is_mitigated'] else 8
                ce_val = fvg.get('consequent_encroachment_ce', fvg['mid'])
                reasoning.append(f"Price in Bearish FVG (SIBI) [{fvg['bot']:.5f} - {fvg['top']:.5f}] Consequent Encroachment (CE 50%): {ce_val:.5f}")
                self.smc_zones_to_save.append(('BEARISH_FVG', fvg['top'], fvg['bot'], fvg['quality'], fvg['is_mitigated']))
                break

        # ── 7. Liquidity Sweeps & Equal Highs/Lows ────────
        if self.buy_side_sweep:
            buy_score += 25
            reasoning.append(f"Sell-Side Liquidity (SSL) Swept @ {self.sweep_level:.5f} (Retail Stops Purged)")
        if self.sell_side_sweep:
            sell_score += 25
            reasoning.append(f"Buy-Side Liquidity (BSL) Swept @ {self.sweep_level:.5f} (Retail Stops Purged)")

        if self.eq_highs and cur_close < self.eq_highs[-1]:
            reasoning.append(f"Draw on Liquidity (DOL): Equal Highs (BSL pool) target above @ {self.eq_highs[-1]:.5f}")
        if self.eq_lows and cur_close > self.eq_lows[-1]:
            reasoning.append(f"Draw on Liquidity (DOL): Equal Lows (SSL pool) target below @ {self.eq_lows[-1]:.5f}")

        # ── 8. Premium / Discount Pricing ─────────────────
        pd_zone = self._get_pd_zone()
        if pd_zone == 'DISCOUNT':
            buy_score += 12
            reasoning.append("Discount Zone: Smart money institutional favorable pricing for longs")
        elif pd_zone == 'PREMIUM':
            sell_score += 12
            reasoning.append("Premium Zone: Smart money institutional favorable pricing for shorts")

        # ── 9. Kill Zone, Silver Bullet & Judas Swing ─────
        if self.silver_bullet != 'INACTIVE':
            reasoning.append(f"⚡ ICT Silver Bullet Window Active: {self.silver_bullet}")
            if self.structure == 'BULLISH':
                buy_score += 15
            elif self.structure == 'BEARISH':
                sell_score += 15
        elif 'KILLZONE' in self.kill_zone:
            reasoning.append(f"Active Session: {self.kill_zone.replace('_', ' ')} (High Institutional Liquidity)")

        if self.judas_swing:
            reasoning.append(f"⚠️ Judas Swing Detected: {self.judas_swing}")
            if 'BULLISH' in self.judas_swing:
                buy_score += 18
            else:
                sell_score += 18

        # ── 10. Liquidity Trap Protection (Filter) ─────────
        if self.liquidity_trap:
            reasoning.append(f"⚠️ {self.liquidity_trap}")
            if 'TRAP_WARNING_AT_BSL' in self.liquidity_trap:
                # Do NOT buy directly into resting BSL resistance!
                buy_score -= 35.0
            elif 'TRAP_WARNING_AT_SSL' in self.liquidity_trap:
                # Do NOT sell directly into resting SSL support!
                sell_score -= 35.0

        # ── Scoring & Direction ───────────────────────────
        buy_score = max(0.0, buy_score)
        sell_score = max(0.0, sell_score)
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
        nearest_bsl = self.liquidity_map.get('nearest_bsl')
        nearest_ssl = self.liquidity_map.get('nearest_ssl')

        # Precision Liquidity-Based Take Profit (DOL) & Stop Loss
        if direction == 'BUY':
            if nearest_bsl and nearest_bsl['price'] > entry:
                self.draw_on_liquidity = nearest_bsl
                # Front-run pool by 0.05 ATR to guarantee limit fill
                tp_zone = nearest_bsl['price'] - (self.cur_atr * 0.05)
                reasoning.append(f"🎯 Draw on Liquidity (DOL): Targeting {nearest_bsl['type']} @ {nearest_bsl['price']:.5f}")
            else:
                tp_zone = entry + (self.cur_atr * 2.8)

            # Anchor SL safely below the swept SSL pool or Bullish OB
            if self.sweep_level and self.sweep_level < entry:
                sl_zone = self.sweep_level - (self.cur_atr * 0.15)
                reasoning.append(f"🛡️ Liquidity Invalidation SL: Anchored below swept SSL low @ {sl_zone:.5f}")
            elif self.bullish_obs and self.bullish_obs[-1]['low'] < entry:
                sl_zone = self.bullish_obs[-1]['low'] - (self.cur_atr * 0.15)
            else:
                sl_zone = entry - (self.cur_atr * 1.2)

        elif direction == 'SELL':
            if nearest_ssl and nearest_ssl['price'] < entry:
                self.draw_on_liquidity = nearest_ssl
                # Front-run pool by 0.05 ATR to guarantee limit fill
                tp_zone = nearest_ssl['price'] + (self.cur_atr * 0.05)
                reasoning.append(f"🎯 Draw on Liquidity (DOL): Targeting {nearest_ssl['type']} @ {nearest_ssl['price']:.5f}")
            else:
                tp_zone = entry - (self.cur_atr * 2.8)

            # Anchor SL safely above the swept BSL pool or Bearish OB
            if self.sweep_level and self.sweep_level > entry:
                sl_zone = self.sweep_level + (self.cur_atr * 0.15)
                reasoning.append(f"🛡️ Liquidity Invalidation SL: Anchored above swept BSL high @ {sl_zone:.5f}")
            elif self.bearish_obs and self.bearish_obs[-1]['high'] > entry:
                sl_zone = self.bearish_obs[-1]['high'] + (self.cur_atr * 0.15)
            else:
                sl_zone = entry + (self.cur_atr * 1.2)
        else:
            sl_zone = None
            tp_zone = None

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
        """Save high-quality SMC zones to database SMCZone model using fast bulk operations"""
        if not self.smc_zones_to_save:
            return
        try:
            from signals.models import SMCZone
            from market_data.models import Instrument
            import django.utils.timezone as dj_tz

            inst = Instrument.get_cached(self.symbol)
            if not inst:
                return

            last_ts = self.df.index[-1]
            if not hasattr(last_ts, 'tzinfo') or last_ts.tzinfo is None:
                last_ts = dj_tz.now()

            new_zones = [
                SMCZone(
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
                for zone_type, high, low, quality, is_mitigated in self.smc_zones_to_save
            ]
            if new_zones:
                SMCZone.objects.bulk_create(new_zones, batch_size=100, ignore_conflicts=True)
        except Exception:
            pass
