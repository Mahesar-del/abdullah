# Free-data causal walk-forward summary

Generated 2026-10-28 from public EV Trading Labs historical simulator files.
The provider attributes its OHLCV aggregation to Dukascopy ticks.  These are
historical market quotes, **not** fills from the connected MetaQuotes-Demo
account.  No live/paper database trade and no MT5 order was created.

## Fixed rule, before the run

- Assets: XAUUSD, US30, SPX500 only.
- Bars: UTC M15/H1/H4 Bid/Ask OHLC.
- At each M15 close, the rule saw only completed bars; a qualifying setup was
  entered at the next observed M15 open.
- M15/H1/H4 strict EMA 50/200 alignment, London/NY killzones, minimum 2R
  target, and +1R break-even shield were kept fixed.
- Stop is assumed first when one M15 OHLC candle touches both stop and target.
  This is conservative.  Unknown slippage and commission were set to zero and
  are explicitly not broker-fill claims.
- No historical unified-news, macro, ML, depth, swap, or account-commission
  data was available; this is therefore a structural price-rule replay only.

## Results

| Asset | Public-history coverage | Closed trades | Win / loss / BE | Win rate | PF | Net R | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| XAUUSD | 2006-01-02 to 2025-12-31 | 1,093 | 519 / 574 / 0 | 47.48% | 0.923 | -39.50R | 45.27% |
| US30 | 2012-01-01 to 2025-12-31 | 602 | 278 / 323 / 1 | 46.18% | 0.946 | -15.89R | 29.28% |
| SPX500 | 2015-01-02 to 2025-12-31 | 468 | 219 / 249 / 0 | 46.79% | 0.892 | -25.63R | 40.64% |

## Decision

All three tested runs have profit factor below 1 and negative net R.  The
current fixed strategy is rejected for automatic execution.  Do not present
the older synthetic historical audit figures as validation for this rule.

## Coverage limits

- Free public current-year (2026) files are account-gated by the source, so
  they were not accessed or bypassed.
- The source begins US30 in 2012 and SPX500 in 2015; no claim is made for
  2006-to-present coverage of those assets.
- The raw result JSON files retain every decision/event/trade and provenance.
