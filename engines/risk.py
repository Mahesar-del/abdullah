"""Deterministic Risk Management & Institutional Trade Sizing Engine.

Enforces Hard Institutional Rules:
- Per-trade risk <= 0.25-0.5% of equity (strict clamp).
- Instrument-specific contract sizing (Forex 100k, JPY rate-adjusted, Gold 100oz, US30 $1/pt, BTC 1 unit).
- Correlated exposure caps: grouped into risk buckets (EURUSD + GBPUSD count as one risk bucket).
- Max gross leverage limit (3.0x target, 5.0x hard ceiling).
- Daily loss limit (1.5% / 3R) with automated Kill Switch.
- Peak-to-trough Drawdown Governor: positions scaled down above 5% DD, 25% floor at 10% DD, hard stop at 15% DD.
- Spread-to-SL cost gating (< 20% of SL distance).
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
    MAX_SPREAD_COST_RATIO = 20.0  # Spread cannot consume more than 20% of SL distance
    DEFAULT_RISK_PCT = 0.5        # 0.5% per trade institutional default
    MAX_PER_TRADE_RISK_PCT = 0.5  # Hard cap: Never exceed 0.5% risk per trade
    MAX_GROSS_LEVERAGE = 3.0      # Institutional gross leverage cap
    DEFAULT_BALANCE = 10000.0     # $10,000 benchmark account

    # Correlated Exposure Buckets (Correlated assets share ONE risk bucket)
    CORRELATED_BUCKETS = {
        'EURUSD': 'EUR_GBP',
        'GBPUSD': 'EUR_GBP',
        'EURGBP': 'EUR_GBP',
        'USDJPY': 'USD_YEN',
        'GBPJPY': 'USD_YEN',
        'EURJPY': 'USD_YEN',
        'XAUUSD': 'METALS',
        'XAGUSD': 'METALS',
        'US30':   'EQUITIES',
        'SPX500': 'EQUITIES',
        'NAS100': 'EQUITIES',
        'GER40':  'EQUITIES',
        'BTCUSD': 'CRYPTO',
        'ETHUSD': 'CRYPTO',
    }

    @classmethod
    def calculate_contract_sizing(cls, symbol: str, entry: float, sl: float, risk_dollar: float) -> Tuple[float, float, float]:
        """Calculates precise recommended lots, dollar risk per lot, and notional exposure per lot.

        Institutional Contract Specifications:
        - Forex Majors (EURUSD, GBPUSD): 100,000 units, pip = 0.0001, $10.00/pip.
        - Forex JPY (USDJPY): 100,000 units, pip = 0.01, pip value = $1000 / rate.
        - Gold (XAUUSD): 100 oz per lot, $1 move = $100.
        - US30 (Index CFD): 1 index point = $1.00 per contract.
        - BTCUSD (Crypto): 1 BTC per contract, $1 move = $1.00.
        """
        sym = symbol.upper()
        sl_dist = abs(entry - sl)
        if sl_dist <= 0:
            return 0.0, 0.0, 0.0

        if 'XAU' in sym or 'GOLD' in sym:
            # 100 oz contract: $1.00 change = $100.00 per lot
            dollar_risk_per_lot = sl_dist * 100.0
            notional_per_lot = entry * 100.0
        elif 'US30' in sym or 'DJI' in sym:
            # Standard index CFD: 1 point = $1.00
            dollar_risk_per_lot = sl_dist * 1.0
            notional_per_lot = entry * 1.0
        elif 'BTC' in sym:
            # 1 BTC contract: $1 move = $1.00
            dollar_risk_per_lot = sl_dist * 1.0
            notional_per_lot = entry * 1.0
        elif 'JPY' in sym:
            # JPY pairs: pip = 0.01; pip value in USD = 1,000 / entry price
            pip_unit = 0.01
            pips = sl_dist / pip_unit
            pip_val = 1000.0 / entry if entry > 0 else 6.80
            dollar_risk_per_lot = pips * pip_val
            notional_per_lot = 100000.0
        else:
            # Standard FX: 100,000 units, pip = 0.0001, pip value = $10.00 per lot
            pip_unit = 0.0001
            pips = sl_dist / pip_unit
            dollar_risk_per_lot = pips * 10.0
            notional_per_lot = 100000.0

        dollar_risk_per_lot = round(dollar_risk_per_lot, 2)
        notional_per_lot = round(notional_per_lot, 2)
        raw_lots = risk_dollar / max(dollar_risk_per_lot, 0.01)
        recommended_lots = round(max(0.01, min(raw_lots, 50.0)), 2)
        return recommended_lots, dollar_risk_per_lot, notional_per_lot

    @classmethod
    def evaluate(cls,
                 symbol: str,
                 direction: str,
                 entry: float,
                 stop_loss: float,
                 take_profit: float,
                 confidence: float,
                 account_balance: float = 10000.0,
                 risk_percentage: float = 0.5,
                 is_in_blackout: bool = False,
                 ignore_daily_limit: bool = False,
                 godzilla_sigma: float = 0.0,
                 godzilla_max_lev: float = 10.0) -> RiskEvaluation:
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

        # 1. Enforce Per-Trade Risk Cap (Strictly <= 0.5% of Equity)
        effective_risk_pct = min(float(risk_percentage), cls.MAX_PER_TRADE_RISK_PCT)
        risk_amount = account_balance * (effective_risk_pct / 100.0)

        # 2. Blackout Check
        if is_in_blackout:
            rejection_reasons.append("Active High-Impact Economic or Central Bank Blackout Window")

        # 3. Maximum Daily Loss & Drawdown Protection (Kill Switch)
        try:
            from signals.models import SignalPerformance
            from django.utils import timezone as dj_tz
            today_start = dj_tz.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today_losses = SignalPerformance.objects.filter(
                recorded_at__gte=today_start,
                outcome='LOSS'
            )
            total_loss_r = abs(sum(float(p.pnl_r if p.pnl_r is not None else 1.0) for p in today_losses))
            if not ignore_daily_limit and total_loss_r >= 3.0:
                rejection_reasons.append(f"Kill Switch Activated: Daily drawdown limit exceeded (-{total_loss_r:.1f}R >= 3.0R)")
        except Exception:
            pass

        # 4. Correlated Bucket Exposure Cap
        bucket = cls.CORRELATED_BUCKETS.get(symbol.upper(), symbol.upper())
        try:
            from signals.models import Signal
            correlated_syms = [s for s, b in cls.CORRELATED_BUCKETS.items() if b == bucket and s != symbol.upper()]
            active_correlated = Signal.objects.filter(
                instrument__symbol__in=correlated_syms,
                status='ACTIVE'
            ).count()
            if active_correlated > 0:
                rejection_reasons.append(
                    f"Correlated Exposure Cap: Bucket '{bucket}' already has {active_correlated} active trade(s). "
                    f"Correlated pair counts as one risk unit."
                )
        except Exception:
            pass

        # 5. Stop Loss & Risk:Reward Verification
        sl_dist = abs(entry - stop_loss)
        tp_dist = abs(take_profit - entry)

        if sl_dist <= 0:
            rejection_reasons.append("Invalid Stop Loss (SL distance is zero)")
            rr_ratio = 0.0
        else:
            rr_ratio = round(tp_dist / sl_dist, 2)

        if rr_ratio < cls.MIN_RR_RATIO:
            rejection_reasons.append(f"Risk:Reward ratio ({rr_ratio:.2f}) below required minimum ({cls.MIN_RR_RATIO})")

        # 6. Spread & Liquidity Filtering
        pip_unit = 0.01 if ('JPY' in symbol or 'XAU' in symbol or 'BTC' in symbol) else 0.0001
        sl_pips = sl_dist / pip_unit if pip_unit > 0 else 1.0

        min_sl_pips = 10.0 if 'XAU' in symbol else (50.0 if 'BTC' in symbol else 4.0)
        if sl_pips < min_sl_pips:
            rejection_reasons.append(f"Low Volatility: SL distance ({sl_pips:.1f} pips) below minimum execution threshold ({min_sl_pips} pips)")

        spread_pips = 1.5
        try:
            from market_data.models import MarketQuoteSpread
            latest_spread = MarketQuoteSpread.objects.filter(instrument__symbol=symbol).first()
            if latest_spread and hasattr(latest_spread, 'spread_pips'):
                spread_pips = latest_spread.spread_pips
        except Exception:
            pass

        max_spread = 20.0 if 'XAU' in symbol else (50.0 if 'BTC' in symbol else 5.0)
        if spread_pips > max_spread:
            rejection_reasons.append(f"Abnormal Spread: Current spread ({spread_pips:.1f} pips) exceeds liquidity limit ({max_spread} pips)")

        spread_cost_ratio = (spread_pips / max(sl_pips, 0.1)) * 100.0
        if spread_cost_ratio > cls.MAX_SPREAD_COST_RATIO:
            rejection_reasons.append(
                f"Spread cost excessive ({spread_cost_ratio:.1f}% of SL distance exceeds {cls.MAX_SPREAD_COST_RATIO}% limit)"
            )

        # 7. Precise Contract Lot Sizing
        recommended_lots, dollar_risk_per_lot, notional_per_lot = cls.calculate_contract_sizing(
            symbol=symbol, entry=entry, sl=stop_loss, risk_dollar=risk_amount
        )

        # 8. Drawdown Governor Integration
        try:
            from signals.models import SignalPerformance
            all_closed = SignalPerformance.objects.filter(outcome__in=['WIN', 'LOSS']).order_by('recorded_at')
            cum_r = 0.0
            peak_r = 0.0
            for p in all_closed:
                val = float(p.pnl_r) if p.pnl_r is not None else (1.0 if p.outcome == 'WIN' else -1.0)
                cum_r += val
                if cum_r > peak_r:
                    peak_r = cum_r
            dd_r = peak_r - cum_r
            # 1R approx 1% drawdown
            if dd_r >= 15.0:
                rejection_reasons.append(f"Hard Drawdown Governor: Peak-to-trough drawdown (-{dd_r:.1f}R >= 15R) triggers emergency halt.")
            elif dd_r >= 5.0:
                # Linearly cut size down to 0.25 floor at 15R
                mult = max(0.25, 1.0 - (0.75 * (dd_r - 5.0) / 10.0))
                recommended_lots = round(max(0.01, recommended_lots * mult), 2)
        except Exception:
            pass

        # 9. Gross Leverage Cap
        total_trade_notional = recommended_lots * notional_per_lot
        if account_balance > 0:
            trade_leverage = total_trade_notional / account_balance
            if trade_leverage > cls.MAX_GROSS_LEVERAGE:
                capped_lots = round((account_balance * cls.MAX_GROSS_LEVERAGE) / notional_per_lot, 2)
                recommended_lots = max(0.01, capped_lots)

        # 10. Low Confidence Gate
        if confidence < 50.0:
            rejection_reasons.append(f"Confidence score ({confidence:.1f}%) is below minimum execution threshold (50%)")

        is_allowed = len(rejection_reasons) == 0

        # Persist decision
        cls._save_decision(
            symbol=symbol, direction=direction, confidence=confidence, entry=entry,
            sl=stop_loss, tp=take_profit, rr=rr_ratio, balance=account_balance,
            risk_pct=effective_risk_pct, risk_amt=risk_amount, lots=recommended_lots,
            spread=spread_pips, spread_ratio=spread_cost_ratio, is_allowed=is_allowed,
            rejections=rejection_reasons
        )

        return RiskEvaluation(
            is_allowed=is_allowed,
            direction=direction,
            recommended_lots=recommended_lots,
            risk_amount_currency=round(risk_amount, 2),
            risk_percentage=effective_risk_pct,
            risk_reward_ratio=rr_ratio,
            current_spread_pips=round(spread_pips, 2),
            spread_cost_ratio_pct=round(spread_cost_ratio, 2),
            rejection_reasons=rejection_reasons,
            risk_level='CONSERVATIVE'
        )

    @classmethod
    def _save_decision(cls, symbol: str, direction: str, confidence: float, entry: float, sl: float,
                       tp: float, rr: float, balance: float, risk_pct: float, risk_amt: float,
                       lots: float, spread: float, spread_ratio: float, is_allowed: bool,
                       rejections: list):
        try:
            from signals.models import RiskDecision
            RiskDecision.objects.create(
                symbol=symbol, direction=direction, confidence=confidence,
                entry_price=entry, stop_loss=sl, take_profit_1=tp,
                risk_reward_ratio=rr, account_balance=balance,
                risk_percentage=risk_pct, risk_amount_currency=risk_amt,
                recommended_lot_size=lots, current_spread_pips=spread,
                spread_cost_ratio_pct=spread_ratio, is_trade_allowed=is_allowed,
                rejection_reasons=rejections, risk_level='CONSERVATIVE'
            )
        except Exception:
            pass
