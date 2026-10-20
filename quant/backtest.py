"""Cost-aware, causal backtester + walk-forward validation.

Timing (no lookahead):  signal & vol-weight known at close t  ->  position held over bar t+1  ->  earns ret[t+1].
Costs: every unit of notional traded pays cost_bps (one-way).
"""
import itertools
import numpy as np
import pandas as pd

from .strategies import REGISTRY


def _apply_band(target: np.ndarray, band: float) -> np.ndarray:
    """No-trade band: avoid paying costs for tiny re-sizings. Exits/flips are always executed."""
    out = np.zeros_like(target)
    cur = 0.0
    for i, t in enumerate(target):
        if t == 0 and cur != 0:
            cur = 0.0
        elif np.sign(t) != np.sign(cur):
            cur = t
        elif abs(t - cur) > band:
            cur = t
        out[i] = cur
    return out


def sleeve_returns(df, signal, cost_bps, ppy, target_vol=0.10, max_lev=3.0, band=0.10):
    """Volatility-targeted position from a direction signal; returns net-of-cost bar returns."""
    ret = df["close"].pct_change().fillna(0.0)
    vol = ret.ewm(span=30, min_periods=20).std() * np.sqrt(ppy)
    w = (target_vol / vol).clip(upper=max_lev).fillna(0.0)
    target = (signal * w).shift(1).fillna(0.0)
    pos = pd.Series(_apply_band(target.to_numpy(), band), index=df.index)
    turnover = pos.diff().abs().fillna(pos.abs())
    gross = pos * ret
    net = gross - turnover * cost_bps / 1e4
    return pd.DataFrame({"ret": net, "gross": gross, "pos": pos, "turnover": turnover})


def metrics(ret: pd.Series, ppy: int) -> dict:
    r = ret.dropna()
    if len(r) < 30 or r.std() == 0:
        return dict(sharpe=0.0, cagr=0.0, vol=0.0, maxdd=0.0, calmar=0.0, years=len(r) / ppy)
    eq = (1 + r).cumprod()
    years = len(r) / ppy
    cagr = eq.iloc[-1] ** (1 / years) - 1
    dd = (eq / eq.cummax() - 1).min()
    sh = r.mean() / r.std() * np.sqrt(ppy)
    return dict(sharpe=float(sh), cagr=float(cagr), vol=float(r.std() * np.sqrt(ppy)),
                maxdd=float(dd), calmar=float(cagr / abs(dd)) if dd < 0 else 0.0, years=float(years))


def trade_stats(pos: pd.Series, ret: pd.Series, risk_unit: float = 0.01, run_bootstrap: bool = True) -> dict:
    """Per-trade stats; a trade = consecutive bars with the same position sign.
    
    Returns comprehensive R-multiple metrics (where 1R = risk_unit, default 1% = 0.01).
    """
    sign = np.sign(pos)
    run = (sign != sign.shift()).cumsum()
    pnls = [ret[g.index].sum() for _, g in pos.groupby(run) if np.sign(g.iloc[0]) != 0]
    if not pnls:
        return dict(
            trades=0, n_trades=0, win_rate=0.0, loss_rate=0.0, profit_factor=0.0,
            expectancy=0.0, expectancy_R=0.0, avg_win=0.0, avg_loss=0.0,
            avg_win_R=0.0, avg_loss_R=0.0, payoff_ratio=0.0,
            break_even_win_rate=0.0, expectancy_ci_95=(0.0, 0.0), expectancy_p5=0.0,
            is_win_rate_trap=False, edge_verdict="Insufficient data (n=0)"
        )
    p = np.array(pnls)
    r_trades = p / risk_unit if (risk_unit and risk_unit > 0) else p
    from .metrics_r import compute_metrics_r
    m_r = compute_metrics_r(r_trades, run_bootstrap=run_bootstrap)

    wins, losses = p[p > 0], p[p <= 0]
    return dict(
        trades=m_r["n_trades"],
        n_trades=m_r["n_trades"],
        win_rate=m_r["win_rate"],
        loss_rate=m_r["loss_rate"],
        profit_factor=m_r["profit_factor"],
        expectancy=float(p.mean()),
        expectancy_R=m_r["expectancy_R"],
        avg_win=float(wins.mean()) if len(wins) else 0.0,
        avg_loss=float(abs(losses.mean())) if len(losses) else 0.0,
        avg_win_R=m_r["avg_win_R"],
        avg_loss_R=m_r["avg_loss_R"],
        payoff_ratio=m_r["payoff_ratio"],
        break_even_win_rate=m_r["break_even_win_rate"],
        expectancy_ci_95=m_r["expectancy_ci_95"],
        expectancy_p5=m_r["expectancy_p5"],
        win_rate_ci_95=m_r["win_rate_ci_95"],
        is_win_rate_trap=m_r["is_win_rate_trap"],
        edge_verdict=m_r["edge_verdict"],
    )


def select_parameters(scores: dict, metric_name: str = "expectancy_R"):
    """Selects parameter candidate strictly by score (expectancy or Sharpe).
    NEVER selects, ranks, or breaks ties by win rate.
    """
    if not scores:
        raise ValueError("Candidate scores dict cannot be empty.")
    return max(scores.keys(), key=lambda c: scores[c])


def bootstrap_sharpe(ret: pd.Series, ppy: int, block: int = 20, n: int = 1000, seed: int = 0):
    """Block-bootstrap -> (5th pct, 95th pct, P[Sharpe>0]). Quantifies 'was this just luck?'"""
    x = ret.dropna().to_numpy()
    L = len(x)
    if L < block * 3:
        return (float("nan"),) * 3
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(L / block))
    starts = rng.integers(0, L - block + 1, size=(n, nb))
    idx = (starts[:, :, None] + np.arange(block)).reshape(n, -1)[:, :L]
    s = x[idx]
    sd = s.std(axis=1)
    sd[sd == 0] = np.nan
    sh = s.mean(axis=1) / sd * np.sqrt(ppy)
    return float(np.nanpercentile(sh, 5)), float(np.nanpercentile(sh, 95)), float(np.nanmean(sh > 0))


def walk_forward(df, strat, cost_bps, ppy, train_bars, test_bars, target_vol=0.10, max_lev=3.0, selection_metric="expectancy"):
    """Pick params on the TRAIN window only, trade them on the NEXT unseen window, roll forward.
    Selection is driven by net expectancy_R (or Sharpe) on the TRAIN window.
    NEVER selects or ranks by win rate.
    Returns (out-of-sample sleeve DataFrame, log of chosen params, number of param trials)."""
    fn, grid = REGISTRY[strat]
    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    cache = {}
    for combo in combos:
        sig = fn(df, **dict(zip(keys, combo)))
        cache[combo] = sleeve_returns(df, sig, cost_bps, ppy, target_vol, max_lev)

    oos, log, start = [], [], train_bars
    while start < len(df):
        end = min(start + test_bars, len(df))
        tr = slice(start - train_bars, start)
        if selection_metric == "sharpe":
            scores = {c: metrics(cache[c]["ret"].iloc[tr], ppy)["sharpe"] for c in combos}
        else:
            scores = {}
            for c in combos:
                t_stats = trade_stats(cache[c]["pos"].iloc[tr], cache[c]["ret"].iloc[tr], run_bootstrap=False)
                scores[c] = t_stats["expectancy_R"]

        best = select_parameters(scores, metric_name=selection_metric)
        oos.append(cache[best].iloc[start:end])
        log.append({"fold_start": df.index[start], "params": dict(zip(keys, best)), f"train_{selection_metric}": scores[best]})
        start = end
    if not oos:
        raise ValueError(f"Not enough data: {len(df)} bars < train window {train_bars}.")
    return pd.concat(oos), log, len(combos)


def fit_latest(df, strat, cost_bps, ppy, train_bars, target_vol=0.10, max_lev=3.0, selection_metric="expectancy"):
    """Params chosen on the most recent train window -> today's desired exposure (for paper trading).
    Selected strictly by net expectancy_R (or Sharpe) on the TRAIN window. Never by win rate."""
    fn, grid = REGISTRY[strat]
    keys = list(grid.keys())
    scores = {}
    sig_cache = {}
    for combo in itertools.product(*[grid[k] for k in keys]):
        sig = fn(df, **dict(zip(keys, combo)))
        r = sleeve_returns(df, sig, cost_bps, ppy, target_vol, max_lev)
        if selection_metric == "sharpe":
            s = metrics(r["ret"].iloc[-train_bars:], ppy)["sharpe"]
        else:
            t = trade_stats(r["pos"].iloc[-train_bars:], r["ret"].iloc[-train_bars:], run_bootstrap=False)
            s = t["expectancy_R"]
        scores[combo] = s
        sig_cache[combo] = sig

    combo = select_parameters(scores, metric_name=selection_metric)
    sig = sig_cache[combo]
    best_score = scores[combo]
    ret = df["close"].pct_change().fillna(0.0)
    vol = ret.ewm(span=30, min_periods=20).std() * np.sqrt(ppy)
    w = (target_vol / vol).clip(upper=max_lev).fillna(0.0)
    return {
        "params": dict(zip(keys, combo)),
        "train_score": best_score,
        f"train_{selection_metric}": best_score,
        "train_sharpe": best_score if selection_metric == "sharpe" else None,
        "exposure": float(sig.iloc[-1] * w.iloc[-1]),
    }
