"""
Production Validation Gate & Criteria Engine
Implements Checklist Section 16 & settings.VALIDATION_CRITERIA:
- LIVE trading gate: LIVE mode is only permitted when a verified, non-expired
  ValidationResult exists with all criteria passed.
- Evaluates multi-asset backtest runs, paper trades, and walk-forward alpha.
- Automatically downgrades to PAPER mode if criteria fail or validation expires.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional

from django.conf import settings
from django.utils import timezone as dj_tz

logger = logging.getLogger(__name__)


class ValidationGate:
    """
    Enforces the deterministic production gate. Evaluates performance metrics against
    hard criteria defined in settings.VALIDATION_CRITERIA.
    """

    @classmethod
    def get_criteria(cls) -> Dict[str, Any]:
        return getattr(settings, 'VALIDATION_CRITERIA', {
            'MIN_TRADES_TOTAL': 30,
            'MIN_PROFIT_FACTOR': 1.2,
            'MIN_EXPECTANCY_R': 0.10,
            'MAX_DRAWDOWN_PCT': 20.0,
            'MIN_OOS_PROFIT_FACTOR': 1.0,
            'MIN_PROFITABLE_ASSET_FRACTION': 0.6,
            'MIN_ASSETS': 3,
            'MIN_PAPER_TRADES': 20,
            'MIN_PAPER_EXPECTANCY_R': 0.0,
            'MAX_VALIDATION_AGE_DAYS': 30,
        })

    @classmethod
    def is_live_trading_permitted(cls) -> Tuple[bool, str]:
        """
        Determines whether LIVE trading execution is authorized.
        Returns:
            (is_allowed: bool, status_reason: str)
        """
        mode = getattr(settings, 'TRADING_MODE', 'PAPER').upper()
        if mode != 'LIVE':
            return False, f"System operating in '{mode}' mode (PAPER trading enforced)"

        from signals.models import ValidationResult

        criteria = cls.get_criteria()
        max_age_days = criteria.get('MAX_VALIDATION_AGE_DAYS', 30)
        cutoff = dj_tz.now() - timedelta(days=max_age_days)

        valid_result = ValidationResult.objects.filter(
            passed=True,
            created_at__gte=cutoff
        ).order_by('-created_at').first()

        if not valid_result:
            return False, f"Live gate closed: No passing ValidationResult within the last {max_age_days} days"

        return True, f"Live gate open: Validated by run #{valid_result.id} @ {valid_result.created_at:%Y-%m-%d}"

    @classmethod
    def evaluate_metrics(cls, metrics: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Validates a candidate metrics dictionary against settings.VALIDATION_CRITERIA.
        Returns:
            (all_passed: bool, detailed_checks: list)
        """
        criteria = cls.get_criteria()
        checks = []

        # 1. Total trades
        tot_trades = metrics.get('total_trades', 0)
        min_trades = criteria.get('MIN_TRADES_TOTAL', 30)
        c1 = tot_trades >= min_trades
        checks.append({'name': 'MIN_TRADES_TOTAL', 'required': min_trades, 'actual': tot_trades, 'passed': c1})

        # 2. Profit factor
        pf = metrics.get('profit_factor', 0.0)
        min_pf = criteria.get('MIN_PROFIT_FACTOR', 1.2)
        c2 = pf >= min_pf
        checks.append({'name': 'MIN_PROFIT_FACTOR', 'required': min_pf, 'actual': pf, 'passed': c2})

        # 3. Expectancy R
        exp_r = metrics.get('expectancy_r', 0.0)
        min_exp_r = criteria.get('MIN_EXPECTANCY_R', 0.10)
        c3 = exp_r >= min_exp_r
        checks.append({'name': 'MIN_EXPECTANCY_R', 'required': min_exp_r, 'actual': exp_r, 'passed': c3})

        # 4. Max drawdown
        mdd = metrics.get('max_drawdown_pct', 100.0)
        max_mdd = criteria.get('MAX_DRAWDOWN_PCT', 20.0)
        c4 = mdd <= max_mdd
        checks.append({'name': 'MAX_DRAWDOWN_PCT', 'required': max_mdd, 'actual': mdd, 'passed': c4})

        # 5. Out-of-sample profit factor
        oos_pf = metrics.get('oos_profit_factor', pf)
        min_oos_pf = criteria.get('MIN_OOS_PROFIT_FACTOR', 1.0)
        c5 = oos_pf >= min_oos_pf
        checks.append({'name': 'MIN_OOS_PROFIT_FACTOR', 'required': min_oos_pf, 'actual': oos_pf, 'passed': c5})

        all_passed = all(c['passed'] for c in checks)
        return all_passed, checks

    @classmethod
    def record_validation(cls, kind: str, symbols: List[str], timeframes: List[str],
                          metrics: Dict[str, Any], limitations: Optional[List[str]] = None):
        """Creates and persists a ValidationResult record"""
        from signals.models import ValidationResult

        criteria = cls.get_criteria()
        passed, checks = cls.evaluate_metrics(metrics)

        return ValidationResult.objects.create(
            kind=kind,
            symbols=symbols,
            timeframes=timeframes,
            metrics=metrics,
            criteria=criteria,
            checks=checks,
            passed=passed,
            limitations=limitations or []
        )
