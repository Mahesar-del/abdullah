"""Bounded, read-only MT5 availability probe for a requested 2006-2026 period.

Only history availability is measured. No strategy, models, orders, account
settings, timezone correction or profitability calculations are performed.
Partial JSON-line worker output survives an IPC timeout, so a failed large
history request cannot erase the independently observed latest source clock.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {'XAUUSD': 'XAUUSD', 'US30': 'US30', 'SPX500': 'US500'}
TIMEFRAMES = {'M15': 900, 'H1': 3600, 'H4': 14400}


def stamp(epoch):
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()


def summarize(rates, seconds, as_of):
    if rates is None or len(rates) == 0:
        return {'status': 'NO_BARS', 'returned_bars': 0}
    times = np.asarray(rates['time'], dtype=np.int64)
    current = as_of.timestamp()
    differences = np.diff(times)
    future = times > current + 30
    return {
        'status': 'CLOCK_ANOMALY' if future.any() else 'AVAILABLE',
        'returned_bars': int(len(times)),
        'completed_bars_by_reference_utc': int((times + seconds <= current).sum()),
        'earliest_returned_open_utc': stamp(times.min()),
        'latest_returned_open_utc': stamp(times.max()),
        'first_returned_year': datetime.fromtimestamp(int(times.min()), timezone.utc).year,
        'future_bars': int(future.sum()),
        'largest_future_ahead_seconds': max(0.0, float(times.max() - current)),
        'duplicate_timestamps': int((differences == 0).sum()),
        'out_of_order_steps': int((differences < 0).sum()),
        'largest_timestamp_gap_seconds': int(differences.max()) if len(differences) else 0,
        'gaps_larger_than_one_timeframe': int((differences > seconds).sum()),
        'gap_interpretation': 'Includes market closures; exchange-calendar completeness has not been verified',
    }


def emit(stage, **fields):
    print(json.dumps({'stage': stage, **fields}, allow_nan=False), flush=True)


def worker(symbol, timeframe, start, as_of, recent_count):
    import MetaTrader5 as mt5

    if not mt5.initialize(timeout=2500):
        emit('connection', status='UNAVAILABLE', error=str(mt5.last_error()))
        return
    terminal = mt5.terminal_info()
    info = mt5.symbol_info(ASSETS[symbol])
    emit('connection', status='CONNECTED',
         terminal_max_bars=getattr(terminal, 'maxbars', None),
         symbol_available=info is not None,
         chart_price_basis='last' if getattr(info, 'chart_mode', 0) == 1 else 'bid')
    if info is None:
        emit('date_range', status='UNAVAILABLE', error='Broker symbol unavailable')
        return
    tf = getattr(mt5, 'TIMEFRAME_' + timeframe)
    # Query unfiltered latest bars FIRST. A date-range query ending at current
    # UTC would otherwise hide future source bars and falsely look clock-safe.
    latest = mt5.copy_rates_from_pos(ASSETS[symbol], tf, 0, recent_count)
    latest_summary = summarize(latest, TIMEFRAMES[timeframe], as_of)
    latest_summary['requested_bars'] = recent_count
    if latest is None:
        latest_summary['error'] = str(mt5.last_error())
    emit('recent_unfiltered', **latest_summary)
    # This is the long-history request. Returned coverage, not the requested
    # dates or the recent fallback, is the evidence for historical availability.
    history = mt5.copy_rates_range(ASSETS[symbol], tf, start, as_of)
    history_summary = summarize(history, TIMEFRAMES[timeframe], as_of)
    if history is None:
        history_summary['error'] = str(mt5.last_error())
    emit('date_range', **history_summary)


def parse_lines(output):
    if isinstance(output, bytes):
        output = output.decode('utf-8', errors='replace')
    stages = {}
    for line in (output or '').splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and 'stage' in row:
            stages[row.pop('stage')] = row
    return stages


def probe(symbol, timeframe, start, as_of, timeout, recent_count):
    command = [sys.executable, '-u', str(Path(__file__).resolve()), '--worker',
               '--symbols', symbol, '--timeframes', timeframe, '--start', start.isoformat(),
               '--as-of', as_of.isoformat(), '--recent-bars', str(recent_count)]
    timed_out = False
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        stages = parse_lines(process.stdout)
        if process.returncode:
            stages['worker_error'] = {'error': process.stderr.strip()[-1200:] or f'Exit {process.returncode}'}
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stages = parse_lines(exc.stdout)
        stages['worker_error'] = {'error': f'IPC hard timeout after {timeout:g}s; child terminated'}
    recent, ranged = stages.get('recent_unfiltered', {}), stages.get('date_range', {})
    anomalous = recent.get('future_bars', 0) > 0 or ranged.get('future_bars', 0) > 0
    actual = ranged if ranged.get('returned_bars', 0) else recent
    result = {
        'status': 'CLOCK_ANOMALY' if anomalous else 'AVAILABLE_RANGE' if ranged.get('returned_bars', 0) else 'RANGE_UNVERIFIED',
        'broker_symbol': ASSETS[symbol], 'timeframe': timeframe,
        'requested_start_utc': start.isoformat(), 'requested_end_utc': as_of.isoformat(),
        'hard_timeout_seconds': timeout, 'worker_timed_out': timed_out,
        'observations': stages,
        'earliest_verified_available_open_utc': actual.get('earliest_returned_open_utc'),
        'latest_verified_available_open_utc': actual.get('latest_returned_open_utc'),
        'coverage_evidence': 'Requested date-range result' if ranged.get('returned_bars', 0) else 'Recent-window fallback ONLY; maximum history remains unknown',
        'any_2006_bar_observed': actual.get('first_returned_year', 9999) <= 2006,
        'full_requested_period_verified': False,
        'clock_basis_verified': False if anomalous else None,
    }
    if ranged.get('returned_bars', 0):
        result['requested_start_year_returned'] = ranged['first_returned_year'] <= start.year
        maxbars = stages.get('connection', {}).get('terminal_max_bars')
        result['terminal_bar_limit_may_truncate'] = bool(maxbars and ranged['returned_bars'] >= maxbars)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--symbols', nargs='+', choices=ASSETS, default=list(ASSETS))
    parser.add_argument('--timeframes', nargs='+', choices=TIMEFRAMES, default=list(TIMEFRAMES))
    parser.add_argument('--start', default='2006-01-01T00:00:00+00:00')
    parser.add_argument('--as-of', default=None)
    parser.add_argument('--timeout', type=float, default=8)
    parser.add_argument('--recent-bars', type=int, default=1200)
    parser.add_argument('--output', type=Path, default=ROOT / 'quant_reports' / 'walkforward_2006_mt5_coverage.json')
    args = parser.parse_args(argv)
    start = datetime.fromisoformat(args.start)
    as_of = datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(timezone.utc)
    if start.tzinfo is None or as_of.tzinfo is None or start >= as_of:
        parser.error('Start/as-of must be timezone-aware and start must precede as-of')
    start, as_of = start.astimezone(timezone.utc), as_of.astimezone(timezone.utc)
    if args.worker:
        try:
            worker(args.symbols[0], args.timeframes[0], start, as_of, args.recent_bars)
        except Exception as exc:
            emit('worker_error', error=str(exc))
        return 0
    if args.timeout <= 0 or not 1 <= args.recent_bars <= 50000:
        parser.error('timeout > 0 and 1 <= recent-bars <= 50000 required')
    report = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'requested_user_end_date': '2026-10-28',
        'requested_start_utc': start.isoformat(), 'effective_end_utc': as_of.isoformat(),
        'scope': 'Broker historical-data availability only; no strategy trades or performance simulation',
        'source': 'MT5 SDK copy_rates_range plus separate unfiltered current-history clock probe',
        'utc_policy': 'Official MT5 UTC timestamps kept unchanged; no guessed broker offset, login or setting changes',
        'full_requested_period_verified': False, 'eligible_for_live': False,
        'status': 'IN_PROGRESS', 'assets': {},
        'limitations': [
            'Requested 2006 date is not evidence that 2006 bars exist or were returned',
            'Failure/timeout is not proof that no older broker history exists; it is an unverified range',
            'Recent-window fallback proves only its actual returned dates, not maximum historical depth',
            'Timestamp gaps include market closures; calendar-level completeness is not assessed',
            'A future latest bar invalidates session/killzone timing even if a bounded date query hides that future bar',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for symbol in args.symbols:
        report['assets'][symbol] = {}
        for timeframe in args.timeframes:
            print(f'Probing {symbol} {timeframe}: 2006 request and unfiltered clock...', flush=True)
            item = probe(symbol, timeframe, start, as_of, args.timeout, args.recent_bars)
            report['assets'][symbol][timeframe] = item
            args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
            print(f'{symbol} {timeframe}: {item["status"]}; earliest verified {item["earliest_verified_available_open_utc"]}', flush=True)
    rows = [item for asset in report['assets'].values() for item in asset.values()]
    report['status'] = ('CLOCK_ANOMALY' if any(row['status'] == 'CLOCK_ANOMALY' for row in rows)
                        else 'AVAILABILITY_ONLY_INCOMPLETE' if any(row['status'] == 'RANGE_UNVERIFIED' for row in rows)
                        else 'AVAILABILITY_ONLY')
    report['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    report['any_2006_bars_observed'] = any(row['any_2006_bar_observed'] for row in rows)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(f'Report: {args.output}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
