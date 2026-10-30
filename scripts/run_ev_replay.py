"""Run a causal structural replay on cached public EV Trading Labs OHLC data."""
from __future__ import annotations

import argparse
from datetime import date
import gzip
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant.sequential_replay import run_sequential_replay
from engines.course_price_action import evaluate_course_price_action, is_course_confirmation_clock
from engines.ict_location import evaluate_ict_location


def _load_frame(cache: Path, symbol: str, timeframe: str, start: date, end: date):
    chunks, missing = [], []
    for year in range(start.year, end.year + 1):
        path = cache / symbol / timeframe / f'{year}.json.gz'
        if not path.exists():
            missing.append(year)
            continue
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            rows = json.load(handle)
        chunk = pd.DataFrame(rows)
        required = {'ts', 'o', 'h', 'l', 'c', 'ao', 'ah', 'al', 'ac'}
        if not required.issubset(chunk.columns):
            raise ValueError(f'{path} does not have complete Bid/Ask OHLC columns')
        selected = ['ts', 'o', 'h', 'l', 'c', 'ao', 'ah', 'al', 'ac']
        if 'v' in chunk.columns:
            selected.append('v')
        chunks.append(chunk[selected])
    if not chunks:
        raise ValueError(f'No {symbol} {timeframe} files cached')
    data = pd.concat(chunks, ignore_index=True)
    data['timestamp'] = pd.to_datetime(data.ts, unit='s', utc=True)
    data = data.set_index('timestamp').sort_index()
    data = data.loc[(data.index >= pd.Timestamp(start, tz='UTC')) & (data.index < pd.Timestamp(end, tz='UTC') + pd.Timedelta(days=1))]
    if data.index.has_duplicates:
        raise ValueError(f'{symbol} {timeframe} has duplicate timestamps')
    data = data.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close',
                                'ao': 'ask_open', 'ah': 'ask_high', 'al': 'ask_low', 'ac': 'ask_close',
                                'v': 'volume'})
    output = ['open', 'high', 'low', 'close', 'ask_open', 'ask_high', 'ask_low', 'ask_close']
    if 'volume' in data:
        output.append('volume')
    return data[output], missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', required=True, type=Path)
    parser.add_argument('--symbol', required=True, choices=('XAUUSD', 'US30', 'SPX500'))
    parser.add_argument('--start', required=True, type=date.fromisoformat)
    parser.add_argument('--warmup-start', type=date.fromisoformat,
                        help='Earlier history load date; decisions still start at --start.')
    parser.add_argument('--end', required=True, type=date.fromisoformat)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--risk-pct', default=1.0, type=float)
    parser.add_argument('--strategy', choices=('closed_trend_reclaim', 'ict_location', 'course_price_action'), default='closed_trend_reclaim')
    parser.add_argument('--slippage', default=0.0, type=float,
                        help='Per-side absolute price-unit assumption; source has quotes but not fills.')
    parser.add_argument('--commission', default=0.0, type=float,
                        help='Per-side absolute price-unit assumption; source has no account commission.')
    parser.add_argument('--exit-policy', choices=('fixed_expiry', 'gold_h1_trail'), default='fixed_expiry',
                        help='fixed_expiry uses the setup validity; gold_h1_trail takes 50% at 1R and trails H1 pivots.')
    args = parser.parse_args()
    frames, missing = {}, {}
    replay_timeframes = ('M5', 'M15', 'H1', 'H4') if args.strategy == 'course_price_action' else ('M15', 'H1', 'H4')
    history_start = args.warmup_start or args.start
    if history_start > args.start:
        raise ValueError('--warmup-start cannot be after --start')
    for timeframe in replay_timeframes:
        frames[timeframe], missing[timeframe] = _load_frame(args.cache_dir, args.symbol, timeframe, history_start, args.end)
    evaluator = ({'ict_location': evaluate_ict_location,
                  'course_price_action': evaluate_course_price_action}.get(args.strategy))
    result = run_sequential_replay(
        frames, args.symbol, start=pd.Timestamp(args.start, tz='UTC'),
        end=pd.Timestamp(args.end, tz='UTC') + pd.Timedelta(days=1),
        slippage=args.slippage, commission=args.commission, risk_pct=args.risk_pct, evaluator=evaluator,
        exit_policy=args.exit_policy, decision_timeframe='M5' if args.strategy == 'course_price_action' else 'M15',
        decision_prefilter=is_course_confirmation_clock if args.strategy == 'course_price_action' else None,
    )
    result['source'] = {
        'provider': 'EV Trading Labs public historical simulator files',
        'attribution': 'EV Trading Labs; provider describes OHLCV as aggregated from Dukascopy ticks',
        'data_kind': 'UTC historical bid/ask OHLC, not the connected MT5 broker feed',
        'bar_timestamp': 'UTC open timestamp supplied by source',
        'execution_scope': 'Historical quoted entry/exit path; exact tick order, fills, swap and account commission are not known',
        'strategy': args.strategy,
        'warmup_start': str(history_start),
        'exit_policy': args.exit_policy,
        'missing_year_files': missing,
        'timeframes': {key: {'bars': len(value), 'first_open_utc': None if value.empty else value.index[0].isoformat(),
                             'last_open_utc': None if value.empty else value.index[-1].isoformat()}
                       for key, value in frames.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'output': str(args.output.resolve()), 'summary': result['summary'], 'source': result['source']}, indent=2))


if __name__ == '__main__':
    main()
