"""Export completed MT5 bid OHLCV with a labelled ask-price reconstruction.

MT5 exposes bid OHLC plus per-bar spread, not historical ask OHLC.  The export
therefore reconstructs ask values as bid + (spread points × symbol point) and
must not be presented as tick-exact ask history.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path


TIMEFRAMES = {'M5': 300, 'M15': 900, 'H1': 3600, 'H4': 14400}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--year', required=True, type=int)
    args = parser.parse_args()
    import MetaTrader5 as mt5

    if not mt5.initialize(timeout=5000):
        raise RuntimeError(f'MT5 initialize failed: {mt5.last_error()}')
    try:
        info = mt5.symbol_info(args.symbol)
        if info is None:
            raise RuntimeError(f'MT5 symbol unavailable: {args.symbol}')
        begin = datetime(args.year, 1, 1, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        end = min(datetime(args.year + 1, 1, 1, tzinfo=timezone.utc), now)
        if end <= begin:
            raise ValueError('Requested year has not begun')
        for name, seconds in TIMEFRAMES.items():
            constant = getattr(mt5, f'TIMEFRAME_{name}')
            rates = mt5.copy_rates_range(args.symbol, constant, begin, end)
            if rates is None:
                raise RuntimeError(f'MT5 {name} history unavailable: {mt5.last_error()}')
            rows = []
            for rate in rates:
                opened = datetime.fromtimestamp(int(rate['time']), tz=timezone.utc)
                if opened + timedelta(seconds=seconds) > now:
                    continue
                spread = float(rate['spread']) * float(info.point)
                bid = {key: float(rate[key]) for key in ('open', 'high', 'low', 'close')}
                rows.append({'ts': int(rate['time']), 'o': bid['open'], 'h': bid['high'], 'l': bid['low'], 'c': bid['close'],
                             'ao': bid['open'] + spread, 'ah': bid['high'] + spread,
                             'al': bid['low'] + spread, 'ac': bid['close'] + spread,
                             'v': int(rate['tick_volume']), 'spread_reconstructed': True})
            target = args.output_dir / args.symbol / name / f'{args.year}.json.gz'
            target.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(target, 'wt', encoding='utf-8') as handle:
                json.dump(rows, handle, separators=(',', ':'))
            print(json.dumps({'timeframe': name, 'completed_bars': len(rows),
                              'path': str(target.resolve()), 'ask_history': 'reconstructed_from_mt5_bar_spread'}))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
