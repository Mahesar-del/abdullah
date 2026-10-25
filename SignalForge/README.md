# SignalForge

Standalone, institutional-style market research for forex and gold. It is **research, not financial advice** and never promises profit. Signal direction is generated only by the transparent scoring engine; no LLM can change it.

## Run

```powershell
cd SignalForge
python -m pip install -r requirements.txt
python selftest.py
python run_signal.py GOLD --horizon swing --account 5000 --risk 1
python run_signal.py EURUSD --horizon intraday --watch 60
```

Each run saves JSON, Markdown and a PNG card to `outputs/`. `selftest.py` is offline and uses deterministic synthetic data.

## What is implemented

- Parallel collector/calendar orchestration with data-gap reporting; Yahoo is used only when available and is explicitly unofficial.
- Deterministic regime-aware trend, momentum, stretch and liquidity-proxy scoring. The exact same `config.WEIGHTS` drive live scoring and walk-forward backtests.
- Signal-at-close / next-bar-entry backtest, costs, 70/30 OOS split, Sharpe, t-stat, drawdown, hit-rate and circular-shift permutation p-value.
- Bootstrap scenario bands and first-touch target/stop probabilities, ATR risk sizing, break-even probability, warnings and validation verdict.
- Four-lens chart-reader metrics (physics, math, geology, history placeholder) and transparent gaps where long archives, screenshots, DXY/yield/VIX and FRED inputs are not yet loaded.

## Explicit limits

Future prices are never collected. Scenarios are simulations, not forecasts. Intraday timing is marked **UNVALIDATED** until multi-timeframe data alignment is added. Monthly history and COT/FRED/RSS integrations are planned adapters rather than fabricated data. Historical results may overfit; monthly averages understate crashes; liquidity is a proxy; gold was price-fixed before 1971; regime months are autocorrelated. Missing sources produce gaps rather than guesses.

## Recommended next work

Add licensed/free long-history loaders, an editable event CSV parser, multi-timeframe alignment, proper DXY/US10Y/VIX regressions, CFTC/COT and FRED clients, and a FastAPI layer. Keep all additions behind data-gap-safe adapters and preserve the scoring/backtest parity test.
