"""
Deterministic Risk Management & Trade Sizing Engine — Phase 9
Covers Master Architecture Section 17 & 18:
- Dynamic lot sizing based on account balance, risk percentage, and SL distance.
- Strict Risk:Reward validation (minimum 1:1.5; ideal 1:2.0 to 1:3.0).
- Spread-to-stop loss ratio validation (spread must not exceed 20% of SL).
- High-impact blackout suppression.
- Deterministic trade approval / rejection.
- Persistence to RiskDecision model.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from datetime import datetime, timezone, timedelta


@dataclass
class RiskEvaluation:
    is_allowed:            bool
    direction:             str
    recommended_lots:      float
    risk_amount_currency:  float
    risk_percentage:       float
    risk_reward_ratio:     float
    current_spread_pips:   float
    spread_cost_ratio_pct: float
    rejection_reasons:     List[str] = field(default_factory=list)
    risk_level:            str = 'CONSERVATIVE'


class RiskEngine:
    """Evaluates risk constraints, calculates position sizing, and enforces capital protection rules"""

    MIN_RR_RATIO = 1.5
    MAX_SPREAD_COST_RATIO = 20.0 # Spread cannot consume more than 20% of SL distance
    DEFAULT_RISK_PCT = 1.0       # 1% per trade default
    DEFAULT_BALANCE = 10000.0    # $10,000 benchmark account

    @classmethod
    def evaluate(cls,
                 symbol: str,
                 direction: str,
                 entry: float,
                 stop_loss: float,
                 take_profit: float,
                 confidence: float,
                 account_balance: float = 10000.0,
                 risk_percentage: float = 1.0,
                 is_in_blackout: bool = False,
                 ignore_daily_limit: bool = False,
                 godzilla_sigma: float = 0.0,
                 godzilla_max_lev: float = 10.0) -> RiskEvaluation:
        """
        Evaluate whether the trade passes all deterministic risk criteria and calculate lot size.
        """
        rejection_reasons = []

        # If direction is WAIT, no trade allowed
        if direction == 'WAIT':
            rejection_reasons.append("Signal direction is WAIT")
            return RiskEvaluation(
                is_allowed=False,
                direction=direction,
                recommended_lots=0.0,
                risk_amount_currency=0.0,
                risk_percentage=risk_percentage,
                risk_reward_ratio=0.0,
                current_spread_pips=0.0,
                spread_cost_ratio_pct=0.0,
                rejection_reasons=rejection_reasons
            )

        # 1. Blackout Check
        if is_in_blackout:
            rejection_reasons.append("Active High-Impact Economic or Central Bank Blackout Window")

        # 2. Maximum Daily Loss & Drawdown Protection (Kill Switch)
        try:
            from signals.models import SignalPerformance
            from django.utils import timezone as dj_tz
            today_start = dj_tz.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_losses = SignalPerformance.objects.filter(
                recorded_at__gte=today_start,
                outcome='LOSS'
            )
            total_loss_r = abs(sum(float(p.pnl_percent or 1.0) for p in today_losses))
            if not ignore_daily_limit and total_loss_r >= 3.0:
                rejection_reasons.append(f"Kill Switch Activated: Daily drawdown limit exceeded (-{total_loss_r:.1f}R >= 3.0R)")
        except Exception:
            pass

        # 3. Stop Loss & R:R Verification
        sl_dist = abs(entry - stop_loss)
        tp_dist = abs(take_profit - entry)

        if sl_dist <= 0:
            rejection_reasons.append("Invalid Stop Loss (SL distance is zero)")
            rr_ratio = 0.0
        else:
            rr_ratio = round(tp_dist / sl_dist, 2)

        if rr_ratio < cls.MIN_RR_RATIO:
            rejection_reasons.append(f"Risk:Reward ratio ({rr_ratio:.2f}) below required minimum ({cls.MIN_RR_RATIO})")

        # 4. Pip and Spread Metrics
        pip_unit = 0.01 if ('JPY' in symbol or 'XAU' in symbol or 'BTC' in symbol) else 0.0001
        sl_pips = sl_dist / pip_unit if pip_unit > 0 else 1.0

        # Low-Volatility Rejection Check
        min_sl_pips = 10.0 if 'XAU' in symbol else (50.0 if 'BTC' in symbol else 4.0)
        if sl_pips < min_sl_pips:
            rejection_reasons.append(f"Low Volatility: SL distance ({sl_pips:.1f} pips) below minimum execution threshold ({min_sl_pips} pips)")

        # Query live spread
        spread_pips = 1.5
        try:
            from market_data.models import MarketQuoteSpread
            latest_spread = MarketQuoteSpread.objects.filter(instrument__symbol=symbol).first()
            if latest_spread and hasattr(latest_spread, 'spread_pips'):
                spread_pips = latest_spread.spread_pips
        except Exception:
            pass

        # Abnormal spread / liquidity filter
        max_spread = 20.0 if 'XAU' in symbol else (50.0 if 'BTC' in symbol else 5.0)
        if spread_pips > max_spread:
            rejection_reasons.append(f"Abnormal Spread: Current spread ({spread_pips:.1f} pips) exceeds liquidity limit ({max_spread} pips)")

        spread_cost_ratio = (spread_pips / max(sl_pips, 0.1)) * 100.0
        if spread_cost_ratio > cls.MAX_SPREAD_COST_RATIO:
            rejection_reasons.append(
                f"Spread cost excessive ({spread_cost_ratio:.1f}% of SL distance exceeds {cls.MAX_SPREAD_COST_RATIO}% limit)"
            )


        # 4. Position Sizing (Lot Size Calculation)
        # Dollar Risk = Account Balance * (risk_percentage / 100)
        risk_amount = account_balance * (risk_percentage / 100.0)

        # Pip value approximation per standard lot (1.0 lot):
        # Forex standard lot = $10 / pip. Gold = $10 / 0.10 move.
        if 'JPY' in symbol:
            pip_val_per_lot = 6.80 # Approx USD per pip on USDJPY standard lot
        elif 'XAU' in symbol:
            pip_val_per_lot = 10.0 # $1 move = $100 on 100oz standard contract
        elif 'BTC' in symbol:
            pip_val_per_lot = 1.0
        else:
            pip_val_per_lot = 10.0 # EURUSD, GBPUSD, AUDUSD = $10/pip

        sl_cost_per_lot = max(sl_pips * pip_val_per_lot, 1.0)
        recommended_lots = round(risk_amount / sl_cost_per_lot, 2)
        recommended_lots = max(0.01, min(recommended_lots, 50.0)) # Clamp between 0.01 and 50.0 lots

        # ── Godzilla Leverage Cap Integration ─────────────────────────────────
        # Apply the Godzilla volatility-adjusted leverage cap:
        #   Max_Leverage = L_0 / (1 + σ_t)  → limits max dollar exposure
        # Max exposure in lots = (account_balance × max_leverage) / (entry × 1000)
        if godzilla_sigma > 0 and entry > 0:
            from .godzilla import godzilla_leverage_cap
            effective_max_lev = godzilla_max_lev if godzilla_max_lev > 0 else \
                godzilla_leverage_cap(godzilla_sigma, base_leverage=10.0)
            max_dollar_exposure = account_balance * effective_max_lev
            godzilla_max_lots = max_dollar_exposure / (entry * 1000.0)
            godzilla_max_lots = max(godzilla_max_lots, 0.01)
            if recommended_lots > godzilla_max_lots:
                recommended_lots = round(godzilla_max_lots, 4)
                rejection_reasons_info = (
                    f"σ_t={godzilla_sigma:.4f} | MaxLev={effective_max_lev:.1f}x | "
                    f"Godzilla cap applied: lots reduced to {recommended_lots}"
                )
                # Not a rejection — just an informational sizing cap
                # Add to reasoning as a note (not a hard block)
                if effective_max_lev < 2.0:
                    rejection_reasons.append(
                        f"Godzilla EXTREME VOL: σ_t={godzilla_sigma:.4f}, MaxLev={effective_max_lev:.1f}x — "
                        f"position micro-capped to {recommended_lots:.4f} lots"
                    )

        # 5. Low confidence check
        if confidence < 50.0:
            rejection_reasons.append(f"Confidence score ({confidence:.1f}%) is below minimum execution threshold (50%)")

        is_allowed = len(rejection_reasons) == 0

        # 6. Persist RiskDecision
        cls._save_decision(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            entry=entry,
            sl=stop_loss,
            tp=take_profit,
            rr=rr_ratio,
            balance=account_balance,
            risk_pct=risk_percentage,
            risk_amt=risk_amount,
            lots=recommended_lots,
            spread=spread_pips,
            spread_ratio=spread_cost_ratio,
            is_allowed=is_allowed,
            rejections=rejection_reasons
        )

        return RiskEvaluation(
            is_allowed=is_allowed,
            direction=direction,
            recommended_lots=recommended_lots,
            risk_amount_currency=round(risk_amount, 2),
            risk_percentage=risk_percentage,
            risk_reward_ratio=rr_ratio,
            current_spread_pips=round(spread_pips, 2),
            spread_cost_ratio_pct=round(spread_cost_ratio, 2),
            rejection_reasons=rejection_reasons,
            risk_level='CONSERVATIVE' if risk_percentage <= 1.0 else 'MODERATE'
        )

    @classmethod
    def _save_decision(cls, symbol: str, direction: str, confidence: float, entry: float, sl: float,
                       tp: float, rr: float, balance: float, risk_pct: float, risk_amt: float,
                       lots: float, spread: float, spread_ratio: float, is_allowed: bool,
                       rejections: list):
        """Save risk decision to database for auditing and trade compliance"""
        try:
            from signals.models import RiskDecision
            RiskDecision.objects.create(
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                entry_price=entry,
                stop_loss=sl,
                take_profit_1=tp,
                risk_reward_ratio=rr,
                account_balance=balance,
                risk_percentage=risk_pct,
                risk_amount_currency=risk_amt,
                recommended_lot_size=lots,
                current_spread_pips=spread,
                spread_cost_ratio_pct=spread_ratio,
                is_trade_allowed=is_allowed,
                rejection_reasons=rejections,
                risk_level='CONSERVATIVE' if risk_pct <= 1.0 else 'MODERATE'
            )
        except Exception:
            pass
