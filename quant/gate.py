"""Institutional Go-Live Gate (Code-Enforced Gatekeeper).

HARD RULE: Live trading is NEVER enabled by default. Auto-trading stays strictly paper.
Going live is a manual flag that is only allowed when this code-enforced gate passes.

Gate Criteria:
1. Walk-Forward Backtest:
   - Portfolio net Sharpe >= 0.50
   - Maximum Drawdown better than -15.0% (MaxDD >= -0.15)
   - Bootstrap 5th percentile Sharpe > 0.0
   - At least 100 out-of-sample trades PER sleeve used
2. Paper Trading Requirement:
   - At least 3 months (>= 90 calendar days) of continuous paper trading history
   - Realised paper-trading performance consistent with backtest (expectancy > 0)
"""
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import numpy as np


class GoLiveGate:
    MIN_SHARPE = 0.50
    MAX_DRAWDOWN = -0.15       # Drawdown must be better than -15.0%
    MIN_BOOT_P5 = 0.0          # 5th percentile bootstrap Sharpe must be strictly positive
    MIN_TRADES_PER_SLEEVE = 100
    MIN_PAPER_DAYS = 90        # 3 months minimum paper trading duration

    @classmethod
    def evaluate_backtest_gate(cls, portfolio_metrics: Dict[str, float], sleeve_trades: Dict[str, int]) -> Tuple[bool, List[str]]:
        """Validates walk-forward backtest statistics against institutional standards.

        Returns (passed: bool, failure_reasons: List[str]).
        """
        reasons = []

        sharpe = portfolio_metrics.get("sharpe", 0.0)
        max_dd = portfolio_metrics.get("maxdd", -1.0)
        boot_p5 = portfolio_metrics.get("boot_p5", -1.0)

        if sharpe < cls.MIN_SHARPE:
            reasons.append(f"Sharpe ratio ({sharpe:.2f}) < required minimum {cls.MIN_SHARPE:.2f}")

        if max_dd < cls.MAX_DRAWDOWN:
            reasons.append(f"Max Drawdown ({max_dd:.1%}) worse than allowed limit {cls.MAX_DRAWDOWN:.1%}")

        if boot_p5 <= cls.MIN_BOOT_P5:
            reasons.append(f"Bootstrap 5th percentile Sharpe ({boot_p5:.2f}) <= {cls.MIN_BOOT_P5:.2f} (edge not statistically significant)")

        if not sleeve_trades:
            reasons.append("No active sleeve trade records provided for verification")
        else:
            for sleeve, trades in sleeve_trades.items():
                if trades < cls.MIN_TRADES_PER_SLEEVE:
                    reasons.append(f"Sleeve '{sleeve}' trades ({trades}) < required minimum {cls.MIN_TRADES_PER_SLEEVE}")

        return len(reasons) == 0, reasons

    @classmethod
    def evaluate_paper_trading_gate(cls, paper_trades: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """Validates that at least 3 months of live paper trading records exist

        with consistent, non-negative expectancy.
        """
        reasons = []
        if not paper_trades or len(paper_trades) < 20:
            reasons.append(f"Insufficient paper trade sample size ({len(paper_trades) if paper_trades else 0} closed trades, >=20 required)")
            return False, reasons

        # Check calendar span
        timestamps = [t.get("closed_at") or t.get("recorded_at") for t in paper_trades if t.get("closed_at") or t.get("recorded_at")]
        if not timestamps:
            reasons.append("Paper trades lack recorded timestamps")
            return False, reasons

        min_ts = min(timestamps)
        max_ts = max(timestamps)
        duration_days = (max_ts - min_ts).days if hasattr((max_ts - min_ts), "days") else 0

        if duration_days < cls.MIN_PAPER_DAYS:
            reasons.append(f"Paper trading history duration ({duration_days} days) < 90 days required (3 months)")

        # Realized expectancy check
        realized_r = [float(t.get("pnl_r", 0.0)) for t in paper_trades if t.get("pnl_r") is not None]
        if realized_r:
            avg_r = np.mean(realized_r)
            if avg_r <= 0.0:
                reasons.append(f"Paper trading realized expectancy is non-positive ({avg_r:+.2f}R <= 0.0)")

        return len(reasons) == 0, reasons

    @classmethod
    def can_go_live(cls, portfolio_metrics: Dict[str, float], sleeve_trades: Dict[str, int], paper_trades: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, Dict[str, Any]]:
        """Final unified gatekeeper.

        Returns (can_go_live: bool, report: dict).
        """
        bt_ok, bt_reasons = cls.evaluate_backtest_gate(portfolio_metrics, sleeve_trades)
        paper_ok, paper_reasons = cls.evaluate_paper_trading_gate(paper_trades or [])

        all_ok = bt_ok and paper_ok
        all_reasons = bt_reasons + paper_reasons

        report = {
            "can_go_live": all_ok,
            "backtest_gate_passed": bt_ok,
            "paper_trading_gate_passed": paper_ok,
            "rejection_reasons": all_reasons,
            "verdict": "ELIGIBLE FOR LIVE (Manual Confirmation Required)" if all_ok else "LIVE TRADING BLOCKED (Gate Failed)",
        }
        return all_ok, report
