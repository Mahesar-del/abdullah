# quant — institutional-style research & portfolio module

Alag, Django se independent module. Maqsad: **pehle saabit karo ke edge hai, phir trade karo.**

## Chalane ka tareeqa (apne computer par, internet ke saath)
```bash
pip install -r requirements.txt          # pandas, numpy, yfinance, matplotlib
python -m unittest quant.tests.test_quant -v     # machinery check (lookahead nahi, random data par edge nahi)
python -m quant.run                               # 5 markets, daily, 3 saal train / 1 saal test
python -m quant.run --symbols EURUSD XAUUSD --interval 1d
python -m quant.run --source csv --csv-dir data/  # apne MT5/Exness export (EURUSD.csv ...)
```
Output: `quant_reports/` mein sleeves.csv, portfolio.csv, portfolio.png + console par VERDICT aur aaj ke target exposures.

## Kya hai
| File | Kaam |
|---|---|
| `data.py` | yfinance / CSV / Django-DB loaders |
| `config.py` | har market ki **cost_bps** — apne broker ke asli spread+commission se REPLACE karein |
| `strategies.py` | 3 baseline sleeves: EMA trend, Donchian breakout, mean-reversion (chhote param grids) |
| `backtest.py` | causal, cost-aware backtester, **walk-forward** (params sirf past par chune jate hain), bootstrap Sharpe CI |
| `portfolio.py` | equal-risk combination, portfolio vol-targeting, drawdown governor |
| `run.py` | CLI + **go-live gate** (Sharpe >= 0.5, bootstrap 5% > 0, MaxDD >= -20%, >= 30 trades) |

## Zaroori baatein
- Verdict **PASS** ka matlab sirf "paper trading ke laayak" hai, live nahi. Paper trading 2-3 mahine, phir chhote size se live.
- **FAIL** aaye to wo bhi ek kaamyab result hai: aapne paise lagaye baghair ghalat strategy pakad li.
- Win rate yahan target nahi. Mean-reversion sleeves ki win rate 60-70% hoti hai phir bhi loss mein ho sakti hain.
- Costs (`config.py`) aur data (broker ka apna feed vs yfinance) result badal sakte hain. Intraday (`--interval 1h`) mein yfinance sirf 730 din deta hai.
- Koi guarantee nahi ke aap ke markets par edge nikalega.
