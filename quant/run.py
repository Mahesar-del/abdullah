"""Research runner.

Examples (on YOUR machine, with internet):
    python -m quant.run                                  # all 5 markets, daily, yfinance
    python -m quant.run --symbols EURUSD XAUUSD --interval 1d
    python -m quant.run --source csv --csv-dir data/     # files named EURUSD.csv, XAUUSD.csv ...
    python -m quant.run --source synthetic-null          # pipeline smoke test (NOT real results)
"""
import argparse
import os
import numpy as np
import pandas as pd

from .config import ASSETS, periods_per_year
from . import data as D
from . import synthetic as S
from .backtest import walk_forward, metrics, trade_stats, bootstrap_sharpe, fit_latest
from .portfolio import combine
from .strategies import REGISTRY

# Go-live gate (paper trading first!). Deliberately strict.
GATE = dict(min_sharpe=0.5, min_boot_p5=0.0, max_dd=-0.20, min_trades=30)


def load(sym, a, args):
    if args.source == "yfinance":
        return D.load_yfinance(a.yahoo, args.interval)
    if args.source == "csv":
        return D.load_csv(os.path.join(args.csv_dir, f"{sym}.csv"))
    if args.source == "db":
        return D.load_django_db(args.db, sym, args.db_tf)
    import zlib; seed = zlib.crc32(sym.encode()) % 10_000
    return S.null_walk(3000, seed) if args.source == "synthetic-null" else S.regime_trend(3000, seed)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=list(ASSETS))
    ap.add_argument("--source", default="yfinance", choices=["yfinance", "csv", "db", "synthetic-null", "synthetic-trend"])
    ap.add_argument("--interval", default="1d", choices=["1d", "1h", "4h"])
    ap.add_argument("--csv-dir", default="data")
    ap.add_argument("--db", default="db.sqlite3")
    ap.add_argument("--db-tf", default="H4")
    ap.add_argument("--train-years", type=float, default=3.0)
    ap.add_argument("--test-years", type=float, default=1.0)
    ap.add_argument("--target-vol", type=float, default=0.10)
    ap.add_argument("--out", default="quant_reports")
    ap.add_argument("--select-metric", default="expectancy", choices=["expectancy", "sharpe"], help="Train selection metric (never win rate)")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    synthetic = args.source.startswith("synthetic")
    if synthetic:
        print("\n*** SYNTHETIC DATA — this only tests the pipeline. NOT evidence of real profitability. ***\n")

    sleeves, rows, latest, trials = {}, [], [], 0
    pnl_trades = {}
    trap_warnings = []
    for sym in args.symbols:
        a = ASSETS[sym]
        ppy = periods_per_year(a, args.interval)
        try:
            df = load(sym, a, args)
        except Exception as e:
            print(f"[skip] {sym}: {e}")
            continue
        if len(df) < 1000:
            print(f"[warn] {sym}: only {len(df)} bars — too short for meaningful validation.")
        train, test = int(args.train_years * ppy), int(args.test_years * ppy)
        for st in REGISTRY:
            try:
                oos, log, n_tr = walk_forward(
                    df, st, a.cost_bps, ppy, train, test, args.target_vol, selection_metric=args.select_metric
                )
            except ValueError as e:
                print(f"[skip] {sym}/{st}: {e}")
                continue
            trials += n_tr
            name = f"{sym}/{st}"
            sleeves[name] = oos["ret"]
            m, t = metrics(oos["ret"], ppy), trade_stats(oos["pos"], oos["ret"])
            g = metrics(oos["gross"], ppy)

            # Win-Rate Trap Warning: High win rate masking poor payoff / negative expectancy
            if t["is_win_rate_trap"] or (t["win_rate"] > 0.55 and t["profit_factor"] < 1.20):
                trap_warnings.append(
                    f"[WIN-RATE TRAP] Sleeve '{name}': Win Rate={t['win_rate']:.1%} (>55%) but Profit Factor={t['profit_factor']:.2f} (<1.20). Net Expectancy={t['expectancy_R']:+.2f}R."
                )

            rows.append(dict(
                sleeve=name,
                win_rate=f"{t['win_rate']:.1%}",
                avg_win_R=f"+{t['avg_win_R']:.2f}R",
                avg_loss_R=f"-{t['avg_loss_R']:.2f}R",
                profit_factor=f"{t['profit_factor']:.2f}",
                expectancy_R=f"{t['expectancy_R']:+.2f}R",
                break_even_win_rate=f"{t['break_even_win_rate']:.1%}",
                verdict=t["edge_verdict"],
                trades=t["trades"],
                sharpe_net=round(m["sharpe"], 2),
                cagr=f"{m['cagr']:.1%}",
                maxdd=f"{m['maxdd']:.1%}"
            ))
            try:
                latest.append((sym, st, fit_latest(df, st, a.cost_bps, ppy, train, args.target_vol, selection_metric=args.select_metric)))
            except Exception:
                pass
    if not sleeves:
        print("No sleeves produced. Check data source.")
        return 1

    tbl = pd.DataFrame(rows)
    print("OUT-OF-SAMPLE results per sleeve (params chosen on TRAIN window only, net of costs)")
    # Print institutional table prioritizing Expectancy, Payoff, Break-Even and Verdict
    display_cols = [
        "sleeve", "win_rate", "avg_win_R", "avg_loss_R", "profit_factor",
        "expectancy_R", "break_even_win_rate", "verdict"
    ]
    print(tbl[display_cols].to_string(index=False))
    tbl.to_csv(os.path.join(args.out, "sleeves.csv"), index=False)

    if trap_warnings:
        print("\n--- WIN-RATE TRAP WARNINGS ---")
        for tw in trap_warnings:
            print(f"  WARNING: {tw}")
        print("  Notice: Never optimize or rank by win rate alone. High win rate with poor payoff yields negative expectancy.\n")

    port = combine(sleeves, ppy=252, target_vol=args.target_vol)
    # start the portfolio where at least one sleeve has OOS data
    port = port.loc[pd.DataFrame(sleeves).dropna(how="all").index.min():]
    pm = metrics(port["ret"], 252)
    lo, hi, p_pos = bootstrap_sharpe(port["ret"], 252)
    avg_trades = int(tbl["trades"].sum())
    print("\nPORTFOLIO (equal-risk sleeves, vol-targeted, drawdown governor)")
    print(f"  OOS years: {pm['years']:.1f} | Sharpe: {pm['sharpe']:.2f}  (bootstrap 5-95%: {lo:.2f} .. {hi:.2f}, P[>0]={p_pos:.0%})")
    print(f"  CAGR: {pm['cagr']:.1%} | Vol: {pm['vol']:.1%} | MaxDD: {pm['maxdd']:.1%} | Calmar: {pm['calmar']:.2f} | total trades: {avg_trades}")
    print(f"  Parameter trials tried (selection/overfit risk): {trials}")

    from .gate import GoLiveGate
    pm_gate = dict(pm)
    pm_gate["boot_p5"] = lo
    sleeve_trades = {r["sleeve"]: int(r["trades"]) for r in tbl.to_dict("records")}
    ok, gate_reasons = GoLiveGate.evaluate_backtest_gate(pm_gate, sleeve_trades)

    print("\nVERDICT:", "PASS -> eligible for PAPER trading (requires >=3 months paper tracking before live)" if ok
          else f"FAIL -> do NOT trade live. Gate failed: {'; '.join(gate_reasons[:2])}")
    if not ok and gate_reasons:
        print("  Gate Failures:")
        for r in gate_reasons:
            print(f"    - {r}")
    if synthetic:
        print("(synthetic data: verdict is only a pipeline check)")

    # --- today's targets (for paper trading) ---
    if latest:
        n = len(latest)
        lv, mu = float(port["lev"].iloc[-1]), float(port["dd_mult"].iloc[-1])
        expo = {}
        for sym, st, f in latest:
            expo[sym] = expo.get(sym, 0.0) + f["exposure"] / n * lv * mu
        print(f"\nTARGET EXPOSURE for the next bar (x equity, +long/-short) | portfolio lev={lv:.2f} dd_mult={mu:.2f}")
        for sym, e in expo.items():
            print(f"  {sym:8s} {e:+.2f}x")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        eq = (1 + port["ret"]).cumprod()
        fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        ax[0].plot(eq.index, eq.values)
        ax[0].set_title("Portfolio OOS equity" + (" (SYNTHETIC)" if synthetic else ""))
        ax[1].fill_between(eq.index, (eq / eq.cummax() - 1).values, 0, color="tab:red", alpha=0.4)
        ax[1].set_title("Drawdown")
        fig.tight_layout()
        fig.savefig(os.path.join(args.out, "portfolio.png"), dpi=110)
    except Exception as e:
        print("(chart skipped:", e, ")")
    port.to_csv(os.path.join(args.out, "portfolio.csv"))
    print(f"\nSaved reports to {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
