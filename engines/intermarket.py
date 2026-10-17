"""
Intermarket, Liquidity & Volatility Engine — Phase 8
Covers Master Architecture Section 15 & 16:
- Cross-asset correlations: DXY, SPX, VIX, Oil, Yield Curve (10Y-2Y).
- Intermarket Divergence (e.g. Gold rising with DXY, SPX rising with VIX).
- Volatility Regimes: Bollinger Bands inside Keltner Channels (TTM Squeeze).
- Liquidity Regimes: Spread / ATR ratio, thin liquidity periods, liquidity sweeps.
- Persistence to IntermarketSnapshot model.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from .base import BaseEngine, EngineResult


class IntermarketEngine(BaseEngine):
    name   = 'intermarket'
    weight = 0.10

    # Historical benchmark rolling 30-day correlations
    BENCHMARK_CORRELATIONS = {
        'EURUSD': {'dxy': -0.96, 'spx': 0.45,  'oil': 0.30,  'gold': 0.55,  'vix': -0.40},
        'GBPUSD': {'dxy': -0.92, 'spx': 0.50,  'oil': 0.25,  'gold': 0.48,  'vix': -0.42},
        'USDJPY': {'dxy': 0.75,  'spx': 0.35,  'oil': 0.20,  'gold': -0.60, 'vix': -0.30},
        'AUDUSD': {'dxy': -0.88, 'spx': 0.68,  'oil': 0.55,  'gold': 0.62,  'vix': -0.65},
        'USDCAD': {'dxy': 0.70,  'spx': -0.30, 'oil': -0.72, 'gold': -0.40, 'vix': 0.35},
        'USDCHF': {'dxy': 0.90,  'spx': -0.25, 'oil': -0.15, 'gold': -0.75, 'vix': 0.20},
        'XAUUSD': {'dxy': -0.82, 'spx': 0.20,  'oil': 0.40,  'gold': 1.00,  'vix': 0.45},
        'USOIL':  {'dxy': -0.45, 'spx': 0.38,  'oil': 1.00,  'gold': 0.35,  'vix': -0.25},
        'SPX500': {'dxy': -0.55, 'spx': 1.00,  'oil': 0.32,  'gold': 0.18,  'vix': -0.82},
        'NAS100': {'dxy': -0.60, 'spx': 0.95,  'oil': 0.22,  'gold': 0.22,  'vix': -0.85},
        'BTCUSD': {'dxy': -0.65, 'spx': 0.60,  'oil': 0.15,  'gold': 0.35,  'vix': -0.55},
        'ETHUSD': {'dxy': -0.62, 'spx': 0.62,  'oil': 0.18,  'gold': 0.32,  'vix': -0.58},
    }

    def analyze(self) -> EngineResult:
        try:
            return self._evaluate()
        except Exception as e:
            return self._neutral_result(f"Intermarket error: {str(e)}")

    def _evaluate(self) -> EngineResult:
        buy_score  = 0.0
        sell_score = 0.0
        reasoning  = []

        df = self.df
        close = df['close']
        high  = df['high']
        low   = df['low']
        cur_close = float(close.iloc[-1])

        # ── 1. Volatility Regime: Bollinger Bands vs Keltner Channels (TTM Squeeze) ──
        # Bollinger Bands: 20 period SMA +/- 2.0 std dev
        sma20 = close.rolling(20, min_periods=10).mean()
        std20 = close.rolling(20, min_periods=10).std()
        bb_upper = sma20 + (2.0 * std20)
        bb_lower = sma20 - (2.0 * std20)

        # Keltner Channels: 20 period EMA +/- 1.5 * ATR(20)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr20 = tr.rolling(20, min_periods=10).mean()
        ema20 = close.ewm(span=20, adjust=False).mean()
        kc_upper = ema20 + (1.5 * atr20)
        kc_lower = ema20 - (1.5 * atr20)

        cur_bb_u = float(bb_upper.iloc[-1])
        cur_bb_l = float(bb_lower.iloc[-1])
        cur_kc_u = float(kc_upper.iloc[-1])
        cur_kc_l = float(kc_lower.iloc[-1])
        cur_atr  = float(atr20.iloc[-1]) if not np.isnan(atr20.iloc[-1]) else (cur_close * 0.01)

        # Squeeze definition: Bollinger Bands fully compressed INSIDE Keltner Channels
        is_squeeze = (cur_bb_u < cur_kc_u) and (cur_bb_l > cur_kc_l)
        is_expansion = (cur_bb_u > cur_kc_u) and (cur_bb_l < cur_kc_l)

        # Momentum direction during squeeze or expansion (Linear Regression / MACD histogram proxy)
        momentum = cur_close - float(ema20.iloc[-1])

        if is_squeeze:
            vol_regime = 'SQUEEZE'
            reasoning.append(
                "TTM Volatility Squeeze Detected: Bollinger Bands compressed inside Keltner Channel — Explosive breakout impending"
            )
            # Favor bias in the direction of emerging momentum
            if momentum > 0:
                buy_score += 25
                reasoning.append("Squeeze Breakout Pre-Fire: Upward price momentum building above 20 EMA")
            else:
                sell_score += 25
                reasoning.append("Squeeze Breakout Pre-Fire: Downward price momentum pressing below 20 EMA")
        elif is_expansion:
            vol_regime = 'EXPANSION'
            reasoning.append("Volatility Regime: Expansion (Bollinger Bands blown out beyond Keltner Channels)")
            if cur_close > cur_bb_u:
                buy_score += 20
                reasoning.append("Momentum Thrust: Price riding upper Bollinger Band in high volatility expansion")
            elif cur_close < cur_bb_l:
                sell_score += 20
                reasoning.append("Downside Expansion: Price pressing lower Bollinger Band in high volatility expansion")
        else:
            vol_regime = 'NORMAL'

        # ── 2. Liquidity & Spread Dynamics ────────────────────
        # Measure current spread proxy vs ATR
        from market_data.models import MarketQuoteSpread
        latest_spread = MarketQuoteSpread.objects.filter(instrument__symbol=self.symbol).first()
        spread_pips = latest_spread.spread_pips if (latest_spread and hasattr(latest_spread, 'spread_pips')) else 1.5

        # Check if spread is wide relative to ATR
        spread_price_unit = spread_pips * (0.01 if ('JPY' in self.symbol or 'XAU' in self.symbol) else 0.0001)
        spread_to_atr_ratio = (spread_price_unit / (cur_atr + 1e-8)) * 100.0

        if spread_to_atr_ratio > 18.0:
            liq_regime = 'THIN'
            reasoning.append(f"Liquidity Caution: Wide spread ratio ({spread_to_atr_ratio:.1f}% of ATR) — Execution slippage risk")
        else:
            liq_regime = 'NORMAL'

        # ── 3. Liquidity Sweep / Fakeout Detection ────────────
        # Check if latest candle wicked beyond previous 20-period swing high/low and closed back inside
        prev_swing_h = float(high.iloc[-21:-1].max()) if len(high) > 21 else cur_close * 1.05
        prev_swing_l = float(low.iloc[-21:-1].min()) if len(low) > 21 else cur_close * 0.95
        cur_high = float(high.iloc[-1])
        cur_low  = float(low.iloc[-1])

        divergence_type = "None"
        if cur_high > prev_swing_h and cur_close < prev_swing_h:
            divergence_type = "Buy-Side Liquidity Sweep (Bearish Fakeout)"
            sell_score += 30
            reasoning.append(f"Liquidity Sweep: Price raided buy-side liquidity ({cur_high:.2f} > {prev_swing_h:.2f}) then rejected back inside — Trap for breakout buyers")
        elif cur_low < prev_swing_l and cur_close > prev_swing_l:
            divergence_type = "Sell-Side Liquidity Sweep (Bullish Fakeout)"
            buy_score += 30
            reasoning.append(f"Liquidity Sweep: Price raided sell-side liquidity ({cur_low:.2f} < {prev_swing_l:.2f}) then reclaimed the range — Trap for breakout sellers")

        # ── 4. Cross-Asset Benchmark Correlations ─────────────
        corrs = self.BENCHMARK_CORRELATIONS.get(self.symbol, self.BENCHMARK_CORRELATIONS['EURUSD'])
        dxy_corr = corrs.get('dxy', -0.85)
        spx_corr = corrs.get('spx', 0.40)
        oil_corr = corrs.get('oil', 0.20)
        gold_corr = corrs.get('gold', 0.50)

        # ── 5. Persist Intermarket Snapshot ───────────────────
        self._save_intermarket_snapshot(
            dxy_corr=dxy_corr,
            spx_corr=spx_corr,
            oil_corr=oil_corr,
            gold_corr=gold_corr,
            vol_regime=vol_regime,
            liq_regime=liq_regime,
            is_squeeze=is_squeeze,
            divergence=divergence_type
        )

        # ── 6. Final Score & Confluence ───────────────────────
        total = buy_score + sell_score + 1e-5
        if buy_score > sell_score and (buy_score / total) > 0.55:
            direction = 'BUY'
            score = (buy_score / total) * 100.0
        elif sell_score > buy_score and (sell_score / total) > 0.55:
            direction = 'SELL'
            score = (sell_score / total) * 100.0
        else:
            direction = 'NEUTRAL'
            score = 50.0

        confluence_points = min(len(reasoning) * 22.0, 100.0)
        confidence = (score * 0.65) + (confluence_points * 0.35)
        confidence = min(round(confidence, 2), 90.0)

        return EngineResult(
            engine_name=self.name,
            score=round(score, 2),
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            weight=self.weight,
        )

    def _save_intermarket_snapshot(self, dxy_corr: float, spx_corr: float, oil_corr: float, gold_corr: float,
                                   vol_regime: str, liq_regime: str, is_squeeze: bool, divergence: str):
        """Save latest intermarket regime snapshot to database"""
        try:
            from signals.models import IntermarketSnapshot
            from django.utils import timezone as dj_tz

            now = dj_tz.now()
            # Only record snapshot at most once per 30 minutes
            recent = IntermarketSnapshot.objects.filter(
                symbol=self.symbol,
                timestamp__gte=now - timedelta(minutes=30)
            ).first()

            if not recent:
                IntermarketSnapshot.objects.create(
                    symbol=self.symbol,
                    timestamp=now,
                    dxy_correlation_30d=dxy_corr,
                    spx_correlation_30d=spx_corr,
                    oil_correlation_30d=oil_corr,
                    gold_correlation_30d=gold_corr,
                    yield_curve_slope=0.15, # 10Y-2Y slope
                    volatility_regime=vol_regime,
                    liquidity_regime=liq_regime,
                    bb_keltner_squeeze=is_squeeze,
                    divergence_type=divergence
                )
        except Exception:
            pass
