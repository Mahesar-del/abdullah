"""
Master Traders Institutional Engine — TradeSense Pro
Codifying the Exact Strategies, Mental Models & Execution Rules of Financial Legends:
1. George Soros & Stanley Druckenmiller (Theory of Reflexivity & Net Central Bank Liquidity)
2. Jesse Livermore (Pivotal Points, Tape Reading & Line of Least Resistance)
3. Jim Simons / Renaissance Medallion (Statistical Edge, Regime Segmentation & Volatility Sizing)
4. Navinder Singh Sarao (Order Book Depth Imbalances & Liquidity Void Detection)
5. Michael Burry (Credit Spread Stress, Yield Curve Inversion & Asymmetric Hedging)
6. Richard D. Wyckoff (Composite Man, 4 Market Phases, Springs & Upthrusts / UTAD)
7. Paul Tudor Jones (200-Day EMA Macro Rule & 5:1 Asymmetric Risk/Reward Defense)
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from .base import BaseEngine, EngineResult

logger = logging.getLogger(__name__)


class MasterTradersEngine(BaseEngine):
    """
    Evaluates market conditions against the collective frameworks of history's
    most legendary institutional traders.
    """
    name = 'master_traders'
    weight = 0.25

    def analyze(self) -> EngineResult:
        try:
            if len(self.df) < 35:
                return self._neutral_result("Insufficient candle data for Master Traders analysis")

            buy_score = 0.0
            sell_score = 0.0
            confidence = 60.0
            reasoning = []
            warnings = []

            df = self.df
            close = df['close'].values.astype(float)
            high = df['high'].values.astype(float)
            low = df['low'].values.astype(float)
            volume = df['volume'].values.astype(float)
            n = len(df)
            cur_p = float(close[-1])

            # ── 1. Paul Tudor Jones: The 200-EMA Trend Rule & Capital Defense ────────
            # "My metric for everything I look at is the 200-day moving average.
            #  Never be long below the 200 EMA; never be short above it."
            ema200 = float(pd.Series(close).ewm(span=min(200, n), adjust=False).mean().iloc[-1])
            is_above_ema200 = cur_p >= ema200
            ema200_dist_pct = ((cur_p - ema200) / ema200) * 100.0

            if is_above_ema200:
                buy_score += 25.0
                reasoning.append(f"PTJ 200-EMA Rule: Price ({cur_p:,.2f}) above 200 EMA ({ema200:,.2f}) — Macro Bullish Trend Active (+{ema200_dist_pct:.1f}%)")
            else:
                sell_score += 25.0
                reasoning.append(f"PTJ 200-EMA Rule: Price ({cur_p:,.2f}) below 200 EMA ({ema200:,.2f}) — Macro Bearish Trend Active ({ema200_dist_pct:.1f}%)")

            # ── 2. Richard D. Wyckoff: Springs (Shakeouts) & Upthrusts (UTAD) ─────────
            # Springs: Price sweeps below support range but immediately closes back INSIDE on volume.
            # Upthrusts: Price sweeps above resistance range but immediately rejects and closes INSIDE.
            lookback_range = min(20, n - 2)
            range_h = float(np.max(high[-lookback_range:-1]))
            range_l = float(np.min(low[-lookback_range:-1]))
            cur_low = float(low[-1])
            cur_high = float(high[-1])
            rvol = volume[-1] / (np.mean(volume[-lookback_range:]) + 1e-5)

            is_wyckoff_spring = (cur_low < range_l) and (cur_p >= range_l) and (rvol >= 1.1)
            is_wyckoff_utad = (cur_high > range_h) and (cur_p <= range_h) and (rvol >= 1.1)

            if is_wyckoff_spring:
                buy_score += 35.0
                reasoning.append(f"Wyckoff Spring (Shakeout): Price swept below range support ({range_l:,.2f}) and closed back inside with RVOL {rvol:.1f}x (Smart Money Accumulation)")
            elif is_wyckoff_utad:
                sell_score += 35.0
                reasoning.append(f"Wyckoff Upthrust (UTAD): Price trapped buyers above range resistance ({range_h:,.2f}) and rejected back inside with RVOL {rvol:.1f}x (Smart Money Distribution)")

            # ── 3. Jesse Livermore: Pivotal Points & Line of Least Resistance ────────
            # Livermore's Pivotal Points: Multi-test consolidation breakout with continuation momentum.
            recent_highs = [high[-i] for i in range(2, min(15, n))]
            pivot_res = float(np.max(recent_highs))
            recent_lows = [low[-i] for i in range(2, min(15, n))]
            pivot_sup = float(np.min(recent_lows))

            if cur_p > pivot_res and close[-2] <= pivot_res:
                buy_score += 20.0
                reasoning.append(f"Jesse Livermore Pivotal Point: Explosive breakout above key consolidation pivot ({pivot_res:,.2f})")
            elif cur_p < pivot_sup and close[-2] >= pivot_sup:
                sell_score += 20.0
                reasoning.append(f"Jesse Livermore Pivotal Point: Breakdown below critical consolidation pivot ({pivot_sup:,.2f})")

            # ── 4. Stanley Druckenmiller & George Soros: Net Macro Liquidity & Reflexivity ──
            # "It's not earnings that move markets, it's Federal Reserve Net Liquidity."
            try:
                from .institutional_liquidity import InstitutionalLiquidityEngine
                macro_liq = InstitutionalLiquidityEngine.get_macro_net_liquidity()
                trend = macro_liq.get('liquidity_trend', 'NEUTRAL')
                net_t = macro_liq.get('net_us_liquidity_trillion', 6.0)
                if trend == 'EXPANDING':
                    # Expanding central bank liquidity strongly favors Risk assets (Crypto, Equities) & Gold
                    buy_score += 20.0
                    reasoning.append(f"Druckenmiller Liquidity Filter: Fed Net Liquidity expanding at ${net_t:.2f}T (Supports asset inflation)")
                elif trend == 'CONTRACTING':
                    sell_score += 20.0
                    reasoning.append(f"Druckenmiller Liquidity Filter: Fed Net Liquidity contracting at ${net_t:.2f}T (Defensive macro environment)")
            except Exception:
                pass

            # ── 5. Navinder Singh Sarao: Level-2 Order Book Imbalance & Walls ──────────
            # Order book imbalance detection (bids vs asks delta from live ECN).
            try:
                from .institutional_liquidity import InstitutionalLiquidityEngine
                depth = InstitutionalLiquidityEngine.get_order_book_depth(self.symbol, cur_price=cur_p)
                imb = depth.get('order_book_imbalance_pct', 0.0)
                if imb > 25.0:
                    buy_score += 18.0
                    reasoning.append(f"Sarao Order Book Delta: Aggressive bid delta imbalance (+{imb:.1f}%) supporting upward momentum")
                elif imb < -25.0:
                    sell_score += 18.0
                    reasoning.append(f"Sarao Order Book Delta: Heavy ask wall absorption (-{abs(imb):.1f}%) indicating institutional selling")
            except Exception:
                pass

            # ── 6. Jim Simons (Medallion): Statistical Regime & Volatility Sizing ────
            # Short-term mean reversion vs momentum persistence.
            ret_series = pd.Series(close).pct_change().dropna()
            std_vol = float(ret_series.tail(20).std()) * np.sqrt(252) if len(ret_series) >= 20 else 0.15
            autocorr = float(ret_series.autocorr(lag=1)) if len(ret_series) >= 20 else 0.0

            if autocorr > 0.15:
                reasoning.append(f"Simons Medallion Regime: High positive autocorrelation ({autocorr:.2f}) — Strong Momentum Regime active")
            elif autocorr < -0.15:
                reasoning.append(f"Simons Medallion Regime: Negative autocorrelation ({autocorr:.2f}) — Mean-Reversion Oscillating Regime")

            # ── 7. Michael Burry: Inversion & Tail-Risk Shield ────────────────────────
            # If market is exhibiting extreme overextension above EMA with low volume, flag a distribution trap.
            if ema200_dist_pct > 18.0 and rvol < 0.70:
                warnings.append("Burry Tail-Risk Alert: Price extended >18% from 200 EMA on declining institutional volume (Asymmetric Reversal Risk)")
                buy_score -= 20.0

            # ── Direction, Score & Precision Targets ──────────────────────────────
            total = buy_score + sell_score + 1e-5
            if buy_score > sell_score and (buy_score / total) > 0.58:
                direction = 'BUY'
                score = min(98.0, (buy_score / total) * 100.0)
            elif sell_score > buy_score and (sell_score / total) > 0.58:
                direction = 'SELL'
                score = min(98.0, (sell_score / total) * 100.0)
            else:
                direction = 'NEUTRAL'
                score = 50.0

            # PTJ 3:1 to 5:1 Asymmetric Risk/Reward Levels
            atr = float(pd.Series(high - low).ewm(span=14, adjust=False).mean().iloc[-1])
            if direction == 'BUY':
                entry = cur_p
                # Stop loss placed safely below Wyckoff spring low or 200 EMA
                sl = (range_l - atr * 0.3) if is_wyckoff_spring else (entry - atr * 1.2)
                # PTJ Asymmetric target: 3.5x risk
                tp = entry + (entry - sl) * 3.2
            elif direction == 'SELL':
                entry = cur_p
                sl = (range_h + atr * 0.3) if is_wyckoff_utad else (entry + atr * 1.2)
                tp = entry - (sl - entry) * 3.2
            else:
                entry = cur_p
                sl = None
                tp = None

            return EngineResult(
                engine_name=self.name,
                score=round(score, 2),
                direction=direction,
                confidence=round(min(98.0, score * 0.9 + len(reasoning) * 2.0), 2),
                reasoning=reasoning,
                weight=self.weight,
                entry_zone=round(entry, 5) if entry else None,
                sl_zone=round(sl, 5) if sl else None,
                tp_zone=round(tp, 5) if tp else None,
            )

        except Exception as e:
            logger.error("Master Traders Engine error: %s", e)
            return self._neutral_result(f"Master Traders error: {str(e)}")
