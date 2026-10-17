"""
Technical Indicator Engine — Weight: 15%
Phase 2 Upgrades:
- Baseline: RSI, MACD, EMA (20/50/200), Bollinger Bands, Stochastic, ATR
- Added: SMA/WMA, ADX, VWAP, Anchored VWAP
- Added: OBV, Relative Volume (RVOL), Volume Profile (POC)
- Added: CCI, ROC, Williams %R
- Added: Keltner Channels, Standard Deviation, Supertrend
- Added: Multi-regime detection (Trend, Momentum, Volatility, Mean-Reversion)
- Configurable per asset & timeframe
- Automatic snapshot persistence to IndicatorSnapshot
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from .base import BaseEngine, EngineResult


class TechnicalEngine(BaseEngine):
    name   = 'technical'
    weight = 0.15

    # ── Default Indicator Parameters ─────────────────────
    DEFAULT_CONFIG = {
        'RSI_PERIOD': 14,
        'RSI_OVERBOUGHT': 70,
        'RSI_OVERSOLD': 30,
        'MACD_FAST': 12,
        'MACD_SLOW': 26,
        'MACD_SIGNAL': 9,
        'EMA_FAST': 20,
        'EMA_MID': 50,
        'EMA_SLOW': 200,
        'SMA_PERIOD': 50,
        'WMA_PERIOD': 20,
        'BB_PERIOD': 20,
        'BB_STD': 2.0,
        'KC_PERIOD': 20,
        'KC_MULT': 1.5,
        'STOCH_K': 14,
        'STOCH_D': 3,
        'STOCH_OB': 80,
        'STOCH_OS': 20,
        'ATR_PERIOD': 14,
        'ADX_PERIOD': 14,
        'CCI_PERIOD': 20,
        'ROC_PERIOD': 12,
        'WILLIAMS_PERIOD': 14,
        'SUPERTREND_PERIOD': 10,
        'SUPERTREND_MULT': 3.0,
    }

    def __init__(self, df: pd.DataFrame, symbol: str = '', timeframe: str = 'H1', custom_config: Optional[dict] = None):
        super().__init__(df, symbol, timeframe=timeframe)
        self.indicators = {}
        self.config = self.DEFAULT_CONFIG.copy()
        if custom_config:
            self.config.update(custom_config)

        # Asset-specific tuning
        if 'BTC' in symbol or 'ETH' in symbol or 'SOL' in symbol:
            self.config['RSI_OVERBOUGHT'] = 75
            self.config['RSI_OVERSOLD'] = 25
            self.config['BB_STD'] = 2.2

    def analyze(self) -> EngineResult:
        try:
            self._compute_indicators()
            self._detect_regimes()
            result = self._evaluate()
            self._save_snapshot_safely()
            return result
        except Exception as e:
            return self._neutral_result(f"Technical calculation error: {str(e)}")

    def _compute_indicators(self):
        df = self.df
        close = df['close']
        high  = df['high']
        low   = df['low']
        volume = df['volume'] if 'volume' in df.columns else pd.Series(1, index=df.index)

        cfg = self.config

        # ── 1. RSI ───────────────────────────────────────────
        delta = close.diff()
        gain  = delta.clip(lower=0)
        loss  = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=cfg['RSI_PERIOD'] - 1, min_periods=cfg['RSI_PERIOD']).mean()
        avg_loss = loss.ewm(com=cfg['RSI_PERIOD'] - 1, min_periods=cfg['RSI_PERIOD']).mean()
        rs  = avg_gain / avg_loss.replace(0, np.nan)
        self.rsi = (100 - (100 / (1 + rs))).fillna(50)

        # ── 2. MACD ──────────────────────────────────────────
        ema_fast = close.ewm(span=cfg['MACD_FAST'], adjust=False).mean()
        ema_slow = close.ewm(span=cfg['MACD_SLOW'], adjust=False).mean()
        self.macd = ema_fast - ema_slow
        self.macd_signal = self.macd.ewm(span=cfg['MACD_SIGNAL'], adjust=False).mean()
        self.macd_hist   = self.macd - self.macd_signal

        # ── 3. Moving Averages (EMA, SMA, WMA) ────────────────
        self.ema20  = close.ewm(span=cfg['EMA_FAST'], adjust=False).mean()
        self.ema50  = close.ewm(span=cfg['EMA_MID'],  adjust=False).mean()
        self.ema200 = close.ewm(span=cfg['EMA_SLOW'], adjust=False).mean()
        self.sma50  = close.rolling(cfg['SMA_PERIOD']).mean().fillna(self.ema50)

        # WMA
        weights = np.arange(1, cfg['WMA_PERIOD'] + 1)
        wma_func = lambda x: np.dot(x, weights) / weights.sum() if len(x) == cfg['WMA_PERIOD'] else np.nan
        self.wma20 = close.rolling(cfg['WMA_PERIOD']).apply(wma_func, raw=True).fillna(self.ema20)

        # ── 4. Bollinger Bands & Standard Deviation ───────────
        bb_mid = close.rolling(cfg['BB_PERIOD']).mean()
        self.bb_std = close.rolling(cfg['BB_PERIOD']).std().fillna(0)
        self.bb_upper = bb_mid + (cfg['BB_STD'] * self.bb_std)
        self.bb_lower = bb_mid - (cfg['BB_STD'] * self.bb_std)
        self.bb_mid   = bb_mid
        self.bb_width = (self.bb_upper - self.bb_lower) / bb_mid.replace(0, 1)

        # ── 5. ATR ────────────────────────────────────────────
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs()
        ], axis=1).max(axis=1)
        self.atr = tr.ewm(span=cfg['ATR_PERIOD'], adjust=False).mean()

        # ── 6. Keltner Channels ───────────────────────────────
        self.kc_mid = self.ema20
        self.kc_upper = self.kc_mid + (cfg['KC_MULT'] * self.atr)
        self.kc_lower = self.kc_mid - (cfg['KC_MULT'] * self.atr)

        # ── 7. Stochastic ─────────────────────────────────────
        low_min  = low.rolling(cfg['STOCH_K']).min()
        high_max = high.rolling(cfg['STOCH_K']).max()
        self.stoch_k = 100 * (close - low_min) / (high_max - low_min + 1e-10)
        self.stoch_d = self.stoch_k.rolling(cfg['STOCH_D']).mean().fillna(50)

        # ── 8. ADX (Average Directional Index) ────────────────
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        tr_smooth = tr.rolling(cfg['ADX_PERIOD']).mean().replace(0, 1e-10)
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).rolling(cfg['ADX_PERIOD']).mean() / tr_smooth)
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(cfg['ADX_PERIOD']).mean() / tr_smooth)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10)
        self.adx = dx.rolling(cfg['ADX_PERIOD']).mean().fillna(20)
        self.plus_di = plus_di.fillna(20)
        self.minus_di = minus_di.fillna(20)

        # ── 9. VWAP & Anchored VWAP ───────────────────────────
        typical_price = (high + low + close) / 3.0
        cum_vol = volume.cumsum().replace(0, 1)
        self.vwap = (typical_price * volume).cumsum() / cum_vol

        # Anchored VWAP to last 50 candles (or session equivalent)
        anchor_len = min(50, len(df))
        anchor_tp = typical_price.iloc[-anchor_len:]
        anchor_vol = volume.iloc[-anchor_len:]
        self.anchored_vwap = float((anchor_tp * anchor_vol).sum() / max(anchor_vol.sum(), 1))

        # ── 10. Volume Analytics (OBV, RVOL, Volume Profile) ──
        direction_sgn = np.sign(close.diff().fillna(0))
        self.obv = (direction_sgn * volume).cumsum()
        vol_mean20 = volume.rolling(20).mean().replace(0, 1)
        self.rvol = volume / vol_mean20

        # Point of Control (POC) via 50-candle volume profile
        lookback = min(50, len(df))
        sub_c = close.iloc[-lookback:]
        sub_v = volume.iloc[-lookback:]
        if len(sub_c) > 0 and sub_v.sum() > 0:
            bins = 15
            counts, bin_edges = np.histogram(sub_c, bins=bins, weights=sub_v)
            poc_idx = np.argmax(counts)
            self.poc = float((bin_edges[poc_idx] + bin_edges[poc_idx + 1]) / 2.0)
        else:
            self.poc = float(close.iloc[-1])

        # ── 11. Momentum Oscillators (CCI, ROC, Williams %R) ──
        # CCI
        tp_sma = typical_price.rolling(cfg['CCI_PERIOD']).mean()
        tp_mad = typical_price.rolling(cfg['CCI_PERIOD']).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True).replace(0, 1e-10)
        self.cci = ((typical_price - tp_sma) / (0.015 * tp_mad)).fillna(0)

        # ROC
        self.roc = ((close - close.shift(cfg['ROC_PERIOD'])) / close.shift(cfg['ROC_PERIOD']).replace(0, 1e-10)) * 100
        self.roc = self.roc.fillna(0)

        # Williams %R
        h_max = high.rolling(cfg['WILLIAMS_PERIOD']).max()
        l_min = low.rolling(cfg['WILLIAMS_PERIOD']).min()
        self.williams_r = (((h_max - close) / (h_max - l_min).replace(0, 1e-10)) * -100).fillna(-50)

        # ── 12. Supertrend ────────────────────────────────────
        hl2 = (high + low) / 2.0
        upperband = hl2 + (cfg['SUPERTREND_MULT'] * self.atr)
        lowerband = hl2 - (cfg['SUPERTREND_MULT'] * self.atr)
        
        supertrend = [lowerband.iloc[0]]
        in_uptrend = True
        for idx in range(1, len(df)):
            if in_uptrend:
                if close.iloc[idx] < lowerband.iloc[idx]:
                    in_uptrend = False
                    supertrend.append(upperband.iloc[idx])
                else:
                    supertrend.append(max(lowerband.iloc[idx], supertrend[-1]))
            else:
                if close.iloc[idx] > upperband.iloc[idx]:
                    in_uptrend = True
                    supertrend.append(lowerband.iloc[idx])
                else:
                    supertrend.append(min(upperband.iloc[idx], supertrend[-1]))
        self.supertrend = pd.Series(supertrend, index=df.index)
        self.supertrend_trend = in_uptrend

        # Collect latest scalar snapshot of all calculated indicators
        self.indicators = {
            'rsi': float(self.rsi.iloc[-1]),
            'macd': float(self.macd.iloc[-1]),
            'macd_signal': float(self.macd_signal.iloc[-1]),
            'macd_hist': float(self.macd_hist.iloc[-1]),
            'ema20': float(self.ema20.iloc[-1]),
            'ema50': float(self.ema50.iloc[-1]),
            'ema200': float(self.ema200.iloc[-1]),
            'sma50': float(self.sma50.iloc[-1]),
            'wma20': float(self.wma20.iloc[-1]),
            'bb_upper': float(self.bb_upper.iloc[-1]),
            'bb_lower': float(self.bb_lower.iloc[-1]),
            'bb_mid': float(self.bb_mid.iloc[-1]),
            'atr': float(self.atr.iloc[-1]),
            'adx': float(self.adx.iloc[-1]),
            'plus_di': float(self.plus_di.iloc[-1]),
            'minus_di': float(self.minus_di.iloc[-1]),
            'stoch_k': float(self.stoch_k.iloc[-1]),
            'stoch_d': float(self.stoch_d.iloc[-1]),
            'supertrend': float(self.supertrend.iloc[-1]),
            'cci': float(self.cci.iloc[-1]),
            'roc': float(self.roc.iloc[-1]),
            'williams_r': float(self.williams_r.iloc[-1]),
            'vwap': float(self.vwap.iloc[-1]),
            'anchored_vwap': float(self.anchored_vwap),
            'poc': float(self.poc),
            'rvol': float(self.rvol.iloc[-1]),
        }

    def _detect_regimes(self):
        """Classify Trend, Volatility, Momentum, and Mean-Reversion Regimes"""
        adx_val = float(self.adx.iloc[-1])
        bb_w = float(self.bb_width.iloc[-1])
        bb_w_mean = float(self.bb_width.rolling(20).mean().iloc[-1]) if len(self.bb_width) >= 20 else bb_w

        # Trend Regime
        if adx_val >= 25:
            if float(self.plus_di.iloc[-1]) > float(self.minus_di.iloc[-1]):
                self.trend_regime = 'STRONG_BULLISH_TREND'
            else:
                self.trend_regime = 'STRONG_BEARISH_TREND'
        elif adx_val >= 18:
            self.trend_regime = 'MILD_TREND'
        else:
            self.trend_regime = 'RANGING'

        # Volatility Regime
        if bb_w > bb_w_mean * 1.3:
            self.volatility_regime = 'HIGH_VOLATILITY'
        elif bb_w < bb_w_mean * 0.7:
            self.volatility_regime = 'LOW_VOLATILITY_SQUEEZE'
        else:
            self.volatility_regime = 'NORMAL_VOLATILITY'

        # Momentum Regime
        roc_val = float(self.roc.iloc[-1])
        macd_hist_val = float(self.macd_hist.iloc[-1])
        if roc_val > 0.5 and macd_hist_val > 0:
            self.momentum_regime = 'BULLISH_EXPANSION'
        elif roc_val < -0.5 and macd_hist_val < 0:
            self.momentum_regime = 'BEARISH_EXPANSION'
        else:
            self.momentum_regime = 'CONSOLIDATING'

        # Overall Unified Regime Label
        if 'TREND' in self.trend_regime:
            self.regime = self.trend_regime
        elif self.volatility_regime == 'HIGH_VOLATILITY':
            self.regime = 'HIGH_VOLATILITY'
        elif self.volatility_regime == 'LOW_VOLATILITY_SQUEEZE':
            self.regime = 'SQUEEZE_RANGE'
        else:
            self.regime = 'TRANSITION'

    def _evaluate(self) -> EngineResult:
        cur_close  = float(self.df['close'].iloc[-1])
        cur_rsi    = float(self.rsi.iloc[-1])
        prev_rsi   = float(self.rsi.iloc[-2])
        cur_macd   = float(self.macd.iloc[-1])
        cur_sig    = float(self.macd_signal.iloc[-1])
        prev_macd  = float(self.macd.iloc[-2])
        prev_sig   = float(self.macd_signal.iloc[-2])
        cur_ema20  = float(self.ema20.iloc[-1])
        cur_ema50  = float(self.ema50.iloc[-1])
        cur_ema200 = float(self.ema200.iloc[-1])
        cur_vwap   = float(self.vwap.iloc[-1])
        cur_cci    = float(self.cci.iloc[-1])
        cur_wr     = float(self.williams_r.iloc[-1])
        cur_rvol   = float(self.rvol.iloc[-1])
        cur_adx    = float(self.adx.iloc[-1])
        cur_st_trend = self.supertrend_trend
        cur_atr    = float(self.atr.iloc[-1])

        buy_signals  = []
        sell_signals = []
        reasoning    = []

        # ── 1. RSI ──
        if cur_rsi < self.config['RSI_OVERSOLD']:
            buy_signals.append(('RSI_OVERSOLD', 2.0))
            reasoning.append(f"RSI oversold at {cur_rsi:.1f}")
        elif cur_rsi > self.config['RSI_OVERBOUGHT']:
            sell_signals.append(('RSI_OVERBOUGHT', 2.0))
            reasoning.append(f"RSI overbought at {cur_rsi:.1f}")
        elif cur_rsi > 50 and prev_rsi <= 50:
            buy_signals.append(('RSI_CROSS_50', 1.0))
            reasoning.append(f"RSI bullish cross above 50 ({cur_rsi:.1f})")
        elif cur_rsi < 50 and prev_rsi >= 50:
            sell_signals.append(('RSI_CROSS_50', 1.0))
            reasoning.append(f"RSI bearish cross below 50 ({cur_rsi:.1f})")

        # ── 2. MACD ──
        if cur_macd > cur_sig and prev_macd <= prev_sig:
            buy_signals.append(('MACD_BULL_CROSS', 2.5))
            reasoning.append("MACD bullish crossover")
        elif cur_macd < cur_sig and prev_macd >= prev_sig:
            sell_signals.append(('MACD_BEAR_CROSS', 2.5))
            reasoning.append("MACD bearish crossover")

        # ── 3. EMA & Trend Stack ──
        if cur_close > cur_ema20 > cur_ema50 > cur_ema200:
            buy_signals.append(('EMA_FULL_BULL_STACK', 3.0))
            reasoning.append("Full bullish EMA alignment (Price > EMA20 > EMA50 > EMA200)")
        elif cur_close < cur_ema20 < cur_ema50 < cur_ema200:
            sell_signals.append(('EMA_FULL_BEAR_STACK', 3.0))
            reasoning.append("Full bearish EMA alignment (Price < EMA20 < EMA50 < EMA200)")
        elif cur_close > cur_ema200:
            buy_signals.append(('ABOVE_EMA200', 1.5))
            reasoning.append("Price above EMA200 (Long-term bullish)")
        else:
            sell_signals.append(('BELOW_EMA200', 1.5))
            reasoning.append("Price below EMA200 (Long-term bearish)")

        # ── 4. VWAP & Anchored VWAP ──
        if cur_close > cur_vwap and cur_close > self.anchored_vwap:
            buy_signals.append(('ABOVE_VWAP', 1.5))
            reasoning.append("Price above VWAP and Anchored VWAP (Institutional bid)")
        elif cur_close < cur_vwap and cur_close < self.anchored_vwap:
            sell_signals.append(('BELOW_VWAP', 1.5))
            reasoning.append("Price below VWAP and Anchored VWAP (Institutional offer)")

        # ── 5. Supertrend ──
        if cur_st_trend:
            buy_signals.append(('SUPERTREND_BULL', 2.0))
            reasoning.append("Supertrend is Bullish")
        else:
            sell_signals.append(('SUPERTREND_BEAR', 2.0))
            reasoning.append("Supertrend is Bearish")

        # ── 6. ADX Directional Trend Strength ──
        if cur_adx > 25:
            reasoning.append(f"Strong Trend detected (ADX = {cur_adx:.1f})")

        # ── 7. CCI & Williams %R (Momentum & Mean-Reversion) ──
        if cur_cci < -100 or cur_wr < -80:
            buy_signals.append(('OVERSOLD_MOMENTUM', 1.5))
            reasoning.append(f"CCI ({cur_cci:.0f}) & Williams %R ({cur_wr:.0f}) indicate oversold discount")
        elif cur_cci > 100 or cur_wr > -20:
            sell_signals.append(('OVERBOUGHT_MOMENTUM', 1.5))
            reasoning.append(f"CCI ({cur_cci:.0f}) & Williams %R ({cur_wr:.0f}) indicate overbought premium")

        # ── 8. Volume Confirmation (RVOL & OBV) ──
        if cur_rvol > 1.3:
            reasoning.append(f"High Relative Volume (RVOL = {cur_rvol:.2f}x)")

        # ── Aggregation & Scoring ──
        total_buy  = sum(w for _, w in buy_signals)
        total_sell = sum(w for _, w in sell_signals)
        total      = total_buy + total_sell + 1e-5

        if total_buy > total_sell and (total_buy / total) > 0.55:
            direction = 'BUY'
            raw_score = (total_buy / total) * 100
        elif total_sell > total_buy and (total_sell / total) > 0.55:
            direction = 'SELL'
            raw_score = (total_sell / total) * 100
        else:
            direction = 'NEUTRAL'
            raw_score = 50.0

        confluence = min((len(buy_signals if direction == 'BUY' else sell_signals) / 6.0) * 100, 100)
        confidence = (raw_score * 0.65) + (confluence * 0.35)

        # Levels
        entry = cur_close
        sl_dist = cur_atr * 1.5
        tp_dist = cur_atr * 3.0

        sl_zone = entry - sl_dist if direction == 'BUY' else (entry + sl_dist if direction == 'SELL' else None)
        tp_zone = entry + tp_dist if direction == 'BUY' else (entry - tp_dist if direction == 'SELL' else None)

        reasoning.append(f"Regime: {self.regime} | Volatility: {self.volatility_regime}")

        return EngineResult(
            engine_name = self.name,
            score       = round(raw_score, 2),
            direction   = direction,
            confidence  = round(confidence, 2),
            reasoning   = reasoning,
            weight      = self.weight,
            entry_zone  = round(entry, 5),
            sl_zone     = round(sl_zone, 5) if sl_zone else None,
            tp_zone     = round(tp_zone, 5) if tp_zone else None,
        )

    def _save_snapshot_safely(self):
        """Saves indicator values to IndicatorSnapshot model for audit & ML"""
        try:
            from signals.models import IndicatorSnapshot
            from market_data.models import Instrument
            import django.utils.timezone as dj_tz

            inst = Instrument.objects.filter(symbol=self.symbol).first()
            if not inst:
                return

            last_ts = self.df.index[-1]
            if not hasattr(last_ts, 'tzinfo') or last_ts.tzinfo is None:
                last_ts = dj_tz.now()

            IndicatorSnapshot.objects.create(
                instrument=inst,
                timeframe=self.timeframe,
                timestamp=last_ts,
                rsi=round(float(self.rsi.iloc[-1]), 4),
                macd=round(float(self.macd.iloc[-1]), 6),
                macd_signal=round(float(self.macd_signal.iloc[-1]), 6),
                adx=round(float(self.adx.iloc[-1]), 4),
                atr=round(float(self.atr.iloc[-1]), 6),
                vwap=round(float(self.vwap.iloc[-1]), 6),
                obv=round(float(self.obv.iloc[-1]), 2),
                cci=round(float(self.cci.iloc[-1]), 4),
                supertrend=round(float(self.supertrend.iloc[-1]), 6),
                regime=self.regime,
                raw_data={
                    'rvol': round(float(self.rvol.iloc[-1]), 2),
                    'poc': round(float(self.poc), 5),
                    'williams_r': round(float(self.williams_r.iloc[-1]), 2),
                    'bb_width': round(float(self.bb_width.iloc[-1]), 5)
                }
            )
        except Exception:
            pass
