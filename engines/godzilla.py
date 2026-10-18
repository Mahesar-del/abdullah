"""
Godzilla Crypto Leverage Trading Formula Engine — Phase 10
==========================================================
Based on the "Godzilla Crypto Leverage Trading Formula":

Variables:
  P_t    = current mid-price (e.g. BTCUSDT)
  θ_t²   = Engle-style forecasted variance (ARCH/GARCH approximation via realized variance)
  σ_t    = √θ_t² = forecasted volatility (annualised then per-candle)
  V_bid  = top-of-book bid volume proxy  (approximated from candle data)
  V_ask  = top-of-book ask volume proxy
  S_t    = Ask_t − Bid_t  ≈ bid–ask spread (approximated from High − Low for OHLCV)
  φ_t    = S_t / P_t = relative spread (friction cost)

Direction Signal (Order Imbalance Index):
  I_t = (V_bid − V_ask) / (V_bid + V_ask)
      > 0  → buyers dominate  → LONG  (BUY)
      < 0  → sellers dominate → SHORT (SELL)

Max Leverage:
  Max_Leverage_t = L_0 / (1 + σ_t)
  • Volatility zyada  → leverage kam   (position size ghatao)
  • Volatility kam    → leverage zyada (position size barhao)

Combined Signal:
  Direction  = sign(I_t) filtered by φ_t threshold
  Size/Lots  = base_lots × (L_0 / (1 + σ_t))  — capped by Max_Leverage
"""

import numpy as np
import pandas as pd
from typing import Optional

from .base import BaseEngine, EngineResult

# ─── Standalone helper (no Django/DB needed) ─────────────────────────────────

def godzilla_leverage_cap(
    sigma_t: float,
    base_leverage: float = 10.0,
    min_leverage: float = 1.0,
    max_leverage: float = 100.0,
) -> float:
    """
    Compute the Godzilla volatility-adjusted max leverage.

    Formula:  Max_Leverage = L_0 / (1 + σ_t)

    Args:
        sigma_t       : Forecasted per-candle volatility (fractional, e.g. 0.025 = 2.5%)
        base_leverage : L_0 — base/maximum allowed leverage (default 10x)
        min_leverage  : Floor leverage (always trade with at least this)
        max_leverage  : Hard ceiling even when volatility is near zero

    Returns:
        float: Adjusted max leverage for this candle
    """
    lev = base_leverage / (1.0 + sigma_t)
    return float(np.clip(lev, min_leverage, max_leverage))


def godzilla_lot_size(
    account_balance: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    sigma_t: float,
    pip_value_per_lot: float = 10.0,
    pip_unit: float = 0.0001,
    base_leverage: float = 10.0,
    min_lots: float = 0.01,
    max_lots: float = 50.0,
) -> dict:
    """
    Full Godzilla position-sizing calculation.

    Steps:
      1. Standard risk-based lot size   (Dollar Risk / SL cost per lot)
      2. Volatility leverage cap        (Max_Lev = L_0 / (1 + σ_t))
      3. Leverage-adjusted max lot size (max_dollar_exposure / entry)
      4. Return the MINIMUM of step-1 and step-3 (conservative)

    Returns dict with:
      recommended_lots, max_leverage, sigma_t, risk_amount,
      godzilla_capped_lots, standard_lots
    """
    # 1. Standard risk-based position sizing
    risk_amount = account_balance * (risk_pct / 100.0)
    sl_dist = abs(entry - stop_loss)
    sl_pips = sl_dist / pip_unit if pip_unit > 0 else 1.0
    sl_cost_per_lot = max(sl_pips * pip_value_per_lot, 1.0)
    standard_lots = round(risk_amount / sl_cost_per_lot, 4)

    # 2. Volatility-adjusted leverage cap
    max_lev = godzilla_leverage_cap(sigma_t, base_leverage)

    # 3. Max exposure based on leverage cap
    max_dollar_exposure = account_balance * max_lev
    # Convert dollar exposure to lots: exposure / (entry price / pip_unit) × pip_value
    # Simpler: exposure = lots × entry (1 lot = 1 contract of asset value)
    # For Forex: 1 lot = 100,000 units → exposure = lots × 100,000 × entry (EURUSD etc)
    # We use a simplified: max_lots_by_leverage = max_dollar_exposure / (entry * 1000)
    # Safest universal approximation:
    margin_lots = max_dollar_exposure / (entry * 1000.0) if entry > 0 else standard_lots
    margin_lots = max(margin_lots, min_lots)

    # 4. Take the conservative minimum
    recommended_lots = min(standard_lots, margin_lots)
    recommended_lots = float(np.clip(recommended_lots, min_lots, max_lots))

    return {
        'recommended_lots':     round(recommended_lots, 4),
        'standard_lots':        round(standard_lots, 4),
        'godzilla_capped_lots': round(margin_lots, 4),
        'max_leverage':         round(max_lev, 2),
        'sigma_t':              round(sigma_t, 6),
        'risk_amount':          round(risk_amount, 2),
    }


# ─── Full Engine Class ────────────────────────────────────────────────────────

class GodzillaEngine(BaseEngine):
    """
    Godzilla Crypto Leverage Trading Formula Engine.

    Produces:
      - Direction signal from Order Imbalance Index (I_t)
      - Volatility-adjusted leverage cap (Max_Leverage_t)
      - Relative spread (friction) filter (φ_t)
      - Score proportional to |I_t| × quality factor
    """

    name   = 'godzilla'
    weight = 0.10   # 10% weight in the unified engine

    # ── Configuration ─────────────────────────────────────
    # ARCH/GARCH window for rolling variance estimate
    GARCH_WINDOW   = 20
    # Minimum |I_t| to trigger a directional signal (avoid noise near 0)
    IMBALANCE_THRESHOLD = 0.05
    # Relative-spread (φ_t) max allowed — if spread too wide, friction too high → WAIT
    MAX_PHI        = 0.005   # 0.5% of price — aggressive trades only when cost is low
    # Base leverage for the formula
    BASE_LEVERAGE  = 10.0

    def analyze(self) -> EngineResult:
        try:
            result = self._run_godzilla()
            return result
        except Exception as exc:
            return self._neutral_result(f"Godzilla engine error: {str(exc)[:100]}")

    # ── Internal Implementation ───────────────────────────

    def _run_godzilla(self) -> EngineResult:
        df = self.df
        close  = df['close'].values.astype(float)
        high   = df['high'].values.astype(float)
        low    = df['low'].values.astype(float)
        volume = df['volume'].values.astype(float) if 'volume' in df.columns else np.ones(len(df))

        P_t = float(close[-1])   # Current mid-price

        # ── Step 1: GARCH-style Volatility (σ_t) ─────────
        # Approximate ARCH variance via rolling realized variance of log-returns
        log_returns = np.diff(np.log(np.maximum(close, 1e-10)))
        window = min(self.GARCH_WINDOW, len(log_returns) - 1)
        if window < 5:
            return self._neutral_result("Not enough data for volatility estimation")

        recent_returns = log_returns[-window:]

        # EWMA variance (Engle ARCH approximation with λ=0.94 RiskMetrics style)
        lambda_decay = 0.94
        ewma_var = float(np.var(recent_returns))  # initial
        for r in recent_returns:
            ewma_var = lambda_decay * ewma_var + (1 - lambda_decay) * (r ** 2)

        sigma_t = float(np.sqrt(max(ewma_var, 1e-12)))   # per-candle fractional volatility

        # ── Step 2: Bid-Ask Spread Approximation (S_t, φ_t) ──
        # Without live order book, approximate: spread ≈ High - Low of last candle
        # This is an upper-bound estimate of the true bid-ask spread.
        last_high = float(high[-1])
        last_low  = float(low[-1])
        S_t  = last_high - last_low           # bid-ask spread proxy
        phi_t = S_t / P_t if P_t > 0 else 0.0  # relative spread (friction)

        # ── Step 3: Order Imbalance Index (I_t) ──────────
        # Approximate bid/ask volumes from candle data:
        #   V_bid proxy: volume on bullish candles (close > open) in recent window
        #   V_ask proxy: volume on bearish candles (close < open) in recent window
        # Use last N candles for the rolling imbalance estimate
        N = min(20, len(df))
        recent = df.tail(N)
        open_arr  = recent['open'].values.astype(float)
        close_arr = recent['close'].values.astype(float)
        vol_arr   = recent['volume'].values.astype(float) if 'volume' in recent.columns else np.ones(N)

        bull_mask = close_arr >= open_arr
        bear_mask = close_arr < open_arr

        # Weight volumes by candle body size (larger body = stronger conviction)
        body_sizes = np.abs(close_arr - open_arr)
        total_body = body_sizes.sum() + 1e-10

        V_bid = float((vol_arr[bull_mask] * body_sizes[bull_mask]).sum())
        V_ask = float((vol_arr[bear_mask] * body_sizes[bear_mask]).sum())
        denom = V_bid + V_ask

        I_t = (V_bid - V_ask) / denom if denom > 0 else 0.0  # range [-1, +1]

        # ── Step 4: Max Leverage ──────────────────────────
        max_lev = godzilla_leverage_cap(sigma_t, self.BASE_LEVERAGE)

        # ── Step 5: Direction Decision ────────────────────
        reasoning = [
            f"Godzilla I_t={I_t:+.3f} | σ_t={sigma_t:.4f} | φ_t={phi_t:.5f} | MaxLev={max_lev:.1f}x"
        ]

        # Friction filter: if spread too wide → friction too high → WAIT
        if phi_t > self.MAX_PHI:
            reasoning.append(f"FRICTION BLOCK: φ_t={phi_t:.5f} > {self.MAX_PHI} (spread too wide)")
            return EngineResult(
                engine_name='godzilla',
                score=0.0,
                direction='NEUTRAL',
                confidence=0.0,
                reasoning=reasoning,
                weight=self.weight,
            )

        # Imbalance threshold filter
        if abs(I_t) < self.IMBALANCE_THRESHOLD:
            reasoning.append(f"IMBALANCE WEAK: |I_t|={abs(I_t):.3f} < {self.IMBALANCE_THRESHOLD} threshold")
            return EngineResult(
                engine_name='godzilla',
                score=20.0,
                direction='NEUTRAL',
                confidence=20.0,
                reasoning=reasoning,
                weight=self.weight,
            )

        # Direction from I_t sign
        direction = 'BUY' if I_t > 0 else 'SELL'

        # Score = |I_t| × 100 × volatility quality factor
        # Quality factor: low volatility assets get higher confidence from this engine
        # High volatility can still trade but with reduced position size (handled by leverage cap)
        vol_quality = max(0.3, 1.0 - sigma_t * 10)  # penalise extreme vol slightly for score
        score = float(np.clip(abs(I_t) * 100.0 * vol_quality, 0.0, 100.0))
        confidence = float(np.clip(abs(I_t) * 80.0 * vol_quality, 0.0, 95.0))

        reasoning.append(
            f"{'BUYERS' if I_t > 0 else 'SELLERS'} dominate order flow (I_t={I_t:+.3f}) → {direction}"
        )
        reasoning.append(
            f"Volatility-adjusted Max Leverage: {max_lev:.1f}x "
            f"({'↑ low vol' if max_lev > self.BASE_LEVERAGE * 0.7 else '↓ high vol'})"
        )

        # Extra crypto-specific info
        if sigma_t > 0.05:
            reasoning.append(f"HIGH VOLATILITY WARNING: σ_t={sigma_t:.4f} — leverage automatically capped to {max_lev:.1f}x")
        if max_lev < 3.0:
            reasoning.append("EXTREME VOLATILITY: Max leverage < 3x — micro position only")

        return EngineResult(
            engine_name='godzilla',
            score=round(score, 2),
            direction=direction,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            weight=self.weight,
            # Store extra metadata in entry_zone for downstream use
            entry_zone=sigma_t,   # σ_t (for leverage calc downstream)
            sl_zone=phi_t,        # φ_t (spread friction)
            tp_zone=max_lev,      # Max_Leverage_t
        )

    def get_leverage_cap(self) -> float:
        """Quick helper to get just the leverage cap for position sizing"""
        try:
            close = self.df['close'].values.astype(float)
            log_returns = np.diff(np.log(np.maximum(close, 1e-10)))
            window = min(self.GARCH_WINDOW, len(log_returns) - 1)
            recent = log_returns[-window:]
            lam = 0.94
            ewma_var = float(np.var(recent))
            for r in recent:
                ewma_var = lam * ewma_var + (1 - lam) * (r ** 2)
            sigma_t = float(np.sqrt(max(ewma_var, 1e-12)))
            return godzilla_leverage_cap(sigma_t, self.BASE_LEVERAGE)
        except Exception:
            return self.BASE_LEVERAGE
