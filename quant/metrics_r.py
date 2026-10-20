"""Quantitative R-Multiple Performance Metrics & Bootstrap Engine.

Focuses strictly on EXPECTANCY and SHARPE, never evaluating systems by win rate alone.
Implements:
- Expectancy R = (win_rate * avg_win_R) - (loss_rate * avg_loss_R)
- Payoff ratio = avg_win_R / avg_loss_R
- Break-even win rate = 1 / (1 + payoff_ratio)
- Profit Factor = sum(Win R) / abs(sum(Loss R))
- Block-bootstrap 95% confidence intervals for Expectancy and Win Rate
- Win-Rate Trap Detection (win_rate > 55% but profit_factor < 1.20)
"""
from typing import Dict, List, Optional, Tuple, Union, Any
import numpy as np
import pandas as pd


def compute_metrics_r(
    trades_r: Union[List[float], np.ndarray, pd.Series],
    block_size: int = 5,
    n_bootstrap: int = 1000,
    seed: int = 42,
    run_bootstrap: bool = True
) -> Dict[str, Any]:
    """Computes comprehensive R-multiple expectancy and payoff metrics from trade outcomes.

    trades_r: list of net realized outcomes in R multiples (e.g. [+1.5, -1.0, +2.1, -1.0]).
    """
    if trades_r is None or len(trades_r) == 0:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "loss_rate": 0.0,
            "avg_win_R": 0.0,
            "avg_loss_R": 0.0,
            "payoff_ratio": 0.0,
            "profit_factor": 0.0,
            "expectancy_R": 0.0,
            "break_even_win_rate": 0.0,
            "expectancy_ci_95": (0.0, 0.0),
            "expectancy_p5": 0.0,
            "win_rate_ci_95": (0.0, 0.0),
            "is_win_rate_trap": False,
            "edge_verdict": "Insufficient data (n=0)",
        }

    arr = np.array(trades_r, dtype=float)
    n = len(arr)

    wins = arr[arr > 0]
    losses = arr[arr < 0]
    n_wins = len(wins)
    n_losses = len(losses)

    win_rate = float(n_wins / n) if n > 0 else 0.0
    loss_rate = float(n_losses / n) if n > 0 else 0.0

    avg_win_r = float(np.mean(wins)) if n_wins > 0 else 0.0
    avg_loss_r = float(abs(np.mean(losses))) if n_losses > 0 else 0.0

    sum_win_r = float(np.sum(wins)) if n_wins > 0 else 0.0
    sum_loss_r = float(abs(np.sum(losses))) if n_losses > 0 else 0.0

    if avg_loss_r > 0:
        payoff_ratio = float(avg_win_r / avg_loss_r)
    else:
        payoff_ratio = float("inf") if avg_win_r > 0 else 0.0

    if sum_loss_r > 0:
        profit_factor = float(sum_win_r / sum_loss_r)
    else:
        profit_factor = float("inf") if sum_win_r > 0 else 0.0

    expectancy_r = float((win_rate * avg_win_r) - (loss_rate * avg_loss_r))

    if payoff_ratio == float("inf"):
        break_even_wr = 0.0
    elif payoff_ratio > 0:
        break_even_wr = float(1.0 / (1.0 + payoff_ratio))
    else:
        break_even_wr = 1.0

    # Win-rate trap check: high win rate masking poor payoff / negative expectancy
    is_win_rate_trap = bool(win_rate > 0.55 and profit_factor < 1.20)

    # Block-Bootstrap for 95% Confidence Intervals (if requested)
    if run_bootstrap and n > 0:
        rng = np.random.default_rng(seed)
        eff_block = max(1, min(block_size, n // 2 if n >= 4 else 1))
        n_blocks = int(np.ceil(n / eff_block))

        boot_exp = []
        boot_wr = []

        for _ in range(n_bootstrap):
            # Sample starting indices
            if n > eff_block:
                starts = rng.integers(0, n - eff_block + 1, size=n_blocks)
                indices = np.concatenate([np.arange(s, s + eff_block) for s in starts])[:n]
            else:
                indices = rng.choice(n, size=n, replace=True)

            sample = arr[indices]
            boot_exp.append(float(np.mean(sample)))
            boot_wr.append(float(np.mean(sample > 0)))

        exp_ci_lower = float(np.percentile(boot_exp, 2.5))
        exp_ci_upper = float(np.percentile(boot_exp, 97.5))
        exp_p5 = float(np.percentile(boot_exp, 5.0))

        wr_ci_lower = float(np.percentile(boot_wr, 2.5))
        wr_ci_upper = float(np.percentile(boot_wr, 97.5))
    else:
        exp_ci_lower = expectancy_r
        exp_ci_upper = expectancy_r
        exp_p5 = expectancy_r
        wr_ci_lower = win_rate
        wr_ci_upper = win_rate

    # Objective edge determination
    if n < 100:
        verdict = f"Insufficient data (n={n}/100)"
    elif expectancy_r < 0:
        verdict = "Negative edge"
    elif exp_p5 > 0:
        verdict = "Positive edge"
    else:
        verdict = "Unproven edge (CI spans zero)"

    return {
        "n_trades": n,
        "win_rate": round(win_rate, 4),
        "loss_rate": round(loss_rate, 4),
        "avg_win_R": round(avg_win_r, 4),
        "avg_loss_R": round(avg_loss_r, 4),
        "payoff_ratio": round(payoff_ratio, 3) if payoff_ratio != float("inf") else float("inf"),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else float("inf"),
        "expectancy_R": round(expectancy_r, 4),
        "break_even_win_rate": round(break_even_wr, 4),
        "expectancy_ci_95": (round(exp_ci_lower, 4), round(exp_ci_upper, 4)),
        "expectancy_p5": round(exp_p5, 4),
        "win_rate_ci_95": (round(wr_ci_lower, 4), round(wr_ci_upper, 4)),
        "is_win_rate_trap": is_win_rate_trap,
        "edge_verdict": verdict,
    }
