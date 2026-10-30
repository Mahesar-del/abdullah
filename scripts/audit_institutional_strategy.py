"""Read-only broker-history coverage and causal structural-candidate benchmark.

This is NOT a replay of the full unified/news/risk/live-execution pipeline. It
never imports Django, trains a model, changes account flags or sends orders.
MT5 reads run in a subprocess with a hard timeout because IPC can hang despite
the terminal's initialize timeout. Only report/cache artifacts are written.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BROKER_SYMBOLS = {'XAUUSD': 'XAUUSD', 'US30': 'US30', 'SPX500': 'US500'}
TIMEFRAME_MINUTES = {'M15': 15, 'H1': 60, 'H4': 240}


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _worker(symbol: str, count: int) -> dict:
    """Only terminal initialize/info/history reads; no login or order functions."""
    import MetaTrader5 as mt5

    if not mt5.initialize(timeout=3000):
        return {'status': 'UNAVAILABLE', 'error': str(mt5.last_error())}
    broker = BROKER_SYMBOLS[symbol]
    info = mt5.symbol_info(broker)
    if info is None:
        return {'status': 'UNAVAILABLE', 'error': f'Broker symbol {broker} is unavailable'}
    # Deliberately do not call symbol_select: audit does not alter Market Watch.
    specs = {key: getattr(info, key, None) for key in (
        'point', 'digits', 'spread', 'spread_float', 'chart_mode',
        'trade_contract_size', 'trade_tick_size', 'trade_tick_value',
    )}
    result = {'status': 'OK', 'broker_symbol': broker, 'specifications': specs, 'frames': {}}
    for name in TIMEFRAME_MINUTES:
        rates = mt5.copy_rates_from_pos(broker, getattr(mt5, 'TIMEFRAME_' + name), 0, count)
        if rates is None or len(rates) == 0:
            result['frames'][name] = {'error': str(mt5.last_error()), 'rates': []}
        else:
            frame = pd.DataFrame(rates)
            result['frames'][name] = {'rates': frame.to_dict(orient='records')}
    return result


def read_broker_history(symbol: str, count: int, timeout: float) -> dict:
    command = [sys.executable, '-u', str(Path(__file__).resolve()),
               '--worker', symbol, '--bars', str(count)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {'status': 'UNAVAILABLE', 'broker_symbol': BROKER_SYMBOLS[symbol],
                'error': f'MT5 IPC exceeded hard {timeout:g}s timeout; child terminated'}
    if completed.returncode:
        return {'status': 'UNAVAILABLE', 'broker_symbol': BROKER_SYMBOLS[symbol],
                'error': completed.stderr.strip()[-1500:] or f'Worker exit {completed.returncode}'}
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {'status': 'UNAVAILABLE', 'broker_symbol': BROKER_SYMBOLS[symbol],
                'error': 'History worker returned no valid JSON result'}


def prepare_frames(raw: dict, as_of: pd.Timestamp) -> tuple[dict, dict]:
    frames, coverage = {}, {}
    for tf, minutes in TIMEFRAME_MINUTES.items():
        item = raw.get('frames', {}).get(tf, {})
        records = item.get('rates', [])
        if not records:
            coverage[tf] = {'returned_bars': 0, 'error': item.get('error', 'No broker bars')}
            continue
        data = pd.DataFrame(records)
        data['time'] = pd.to_datetime(data['time'], unit='s', utc=True)
        data = data.set_index('time')
        duplicates = int(data.index.duplicated().sum())
        if duplicates or not data.index.is_monotonic_increasing:
            coverage[tf] = {'returned_bars': len(data), 'error': 'Duplicate/out-of-order broker bars'}
            continue
        # MT5 officially returns UTC. A future bar OPEN (as opposed to a current
        # unfinished bar) cannot be silently discarded: doing so could disguise
        # a broker/server offset and shift every historical killzone decision.
        future = data.index > as_of + pd.Timedelta(seconds=30)
        largest_future_ahead = max(0.0, float((data.index[-1] - as_of).total_seconds()))
        complete = data[data.index + pd.Timedelta(minutes=minutes) <= as_of].copy()
        columns = ['open', 'high', 'low', 'close']
        invalid = (~np.isfinite(complete[columns].to_numpy())).any()
        invalid = invalid or (complete[columns] <= 0).any().any()
        invalid = invalid or (complete.high < complete[['open', 'close', 'low']].max(axis=1)).any()
        invalid = invalid or (complete.low > complete[['open', 'close', 'high']].min(axis=1)).any()
        if invalid:
            coverage[tf] = {'returned_bars': len(data), 'error': 'Invalid broker OHLC values'}
            continue
        if 'tick_volume' in complete:
            complete['volume'] = complete['tick_volume']
        digest = hashlib.sha256(complete.to_csv(float_format='%.10g').encode('utf-8')).hexdigest()
        deltas = complete.index.to_series().diff().dt.total_seconds().dropna()
        coverage[tf] = {
            'status': 'CLOCK_ANOMALY' if future.any() else 'OK',
            'returned_bars': len(data), 'completed_bars': len(complete),
            'future_bars': int(future.sum()),
            'largest_future_ahead_seconds': largest_future_ahead,
            'clock_tolerance_seconds': 30,
            'source_first_bar_open_utc': data.index[0].isoformat(),
            'source_last_bar_open_utc': data.index[-1].isoformat(),
            'first_bar_open_utc': complete.index[0].isoformat() if len(complete) else None,
            'last_bar_open_utc': complete.index[-1].isoformat() if len(complete) else None,
            'last_bar_close_utc': (complete.index[-1] + pd.Timedelta(minutes=minutes)).isoformat() if len(complete) else None,
            'gaps_larger_than_one_bar': int((deltas > minutes * 60).sum()),
            'gap_note': 'Counts include legitimate market closures; no candles filled or synthesized',
            'sha256_csv': digest,
        }
        frames[tf] = complete
    return frames, coverage


def simulate_position(bars: pd.DataFrame, start: int, direction: str, entry: float,
                      stop: float, target: float, point: float, slippage_points: float,
                      commission_bps: float, max_hold_bars: int = 8) -> dict:
    """Conservative Bid/Ask OHLC execution with fixed initial risk.

    SL wins ambiguous SL+TP candles. A newly earned BE shield only becomes
    effective on the NEXT candle: the same candle's earlier low/high is never
    used retrospectively. Gap stops fill at the adverse open, not the old stop.
    """
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError('Initial risk must be positive')
    slip = point * slippage_points
    current_stop, shield = stop, False
    exit_price, reason = None, 'TIME_EXIT'
    last_index = min(len(bars) - 1, start + max_hold_bars - 1)
    activated_at = None
    for index in range(start, last_index + 1):
        bar = bars.iloc[index]
        spread = max(0.0, float(bar.get('spread', 0))) * point
        # MT5 chart_mode=0 bars are Bid; short exits buy at Ask.
        add = spread if direction == 'SELL' else 0.0
        opening, high, low = float(bar.open) + add, float(bar.high) + add, float(bar.low) + add
        stopped_open = opening <= current_stop if direction == 'BUY' else opening >= current_stop
        stopped_range = low <= current_stop if direction == 'BUY' else high >= current_stop
        target_range = high >= target if direction == 'BUY' else low <= target
        if stopped_open:
            exit_price = opening - slip if direction == 'BUY' else opening + slip
            reason = 'BE_STOP' if shield else 'STOP_LOSS_GAP'
        elif stopped_range:
            exit_price = current_stop - slip if direction == 'BUY' else current_stop + slip
            reason = 'BE_STOP' if shield else 'STOP_LOSS'
        elif target_range:
            exit_price = target - slip if direction == 'BUY' else target + slip
            reason = 'TAKE_PROFIT'
        if exit_price is not None:
            last_index = index
            break
        # This stop cannot participate in the range checks above.
        earned_shield = high - entry >= risk if direction == 'BUY' else entry - low >= risk
        if not shield and earned_shield:
            current_stop = entry + spread if direction == 'BUY' else entry - spread
            shield, activated_at = True, bars.index[index].isoformat()
    if exit_price is None:
        last = bars.iloc[last_index]
        spread = max(0.0, float(last.get('spread', 0))) * point
        exit_price = float(last.close) - slip if direction == 'BUY' else float(last.close) + spread + slip
    commission_price = (abs(entry) + abs(exit_price)) * commission_bps / 10000.0
    net_change = (exit_price - entry if direction == 'BUY' else entry - exit_price) - commission_price
    return {
        'opened_at_utc': bars.index[start].isoformat(),
        'exit_bar_open_utc': bars.index[last_index].isoformat(),
        'direction': direction, 'entry': entry, 'initial_stop': stop, 'target': target,
        'exit': exit_price, 'reason': reason, 'realized_r': net_change / risk,
        'commission_price_units': commission_price, 'be_earned_bar_open_utc': activated_at,
        'exit_index': last_index,
    }


def benchmark(frames: dict, symbol: str, specs: dict, holdout: float = 0.2,
              commission_bps: float = 0.0, slippage_points: float = 1.0,
              max_hold_bars: int = 8) -> dict:
    from engines.institutional_setup import evaluate_setup, STRATEGY_VERSION
    from quant.metrics_r import compute_metrics_r

    if set(frames) != set(TIMEFRAME_MINUTES):
        return {'status': 'NOT_RUN', 'reason': 'All three genuine broker timeframes are required'}
    if specs.get('chart_mode') != 0:
        return {'status': 'NOT_RUN', 'reason': 'Only broker Bid-based chart bars are supported by this execution model'}
    point = float(specs.get('point') or 0)
    if point <= 0:
        return {'status': 'NOT_RUN', 'reason': 'Broker point specification is missing'}
    data = frames['M15']
    split_index = max(1, int(len(data) * (1.0 - holdout)))
    if split_index >= len(data) - 1:
        return {'status': 'NOT_RUN', 'reason': 'Insufficient real M15 history for a holdout'}
    start, last_exit = split_index, -1
    trades, rejection_counts = [], Counter()
    eligible_candidates = 0
    for index in range(start, len(data)):
        if index <= last_exit:
            continue
        as_of = data.index[index]
        if not (7 <= as_of.hour < 11 or 13 <= as_of.hour < 17):
            continue
        # Select only completed history and retain a consistent 400-bar EMA
        # context. The current/future execution candle never enters the signal.
        context = {}
        for tf, minutes in TIMEFRAME_MINUTES.items():
            end = frames[tf].index.searchsorted(as_of - pd.Timedelta(minutes=minutes), side='right')
            context[tf] = frames[tf].iloc[max(0, end - 400):end]
        entry_bar = data.iloc[index]
        spread = max(0.0, float(entry_bar.get('spread', 0))) * point
        decision = evaluate_setup(context, symbol, as_of=as_of, spread=spread)
        if not decision.allowed:
            rejection_counts[decision.reasons[0] if decision.reasons else 'Unknown rejection'] += 1
            continue
        eligible_candidates += 1
        # Entry price is only available at the next bar's open. Set structural
        # stop and a predeclared 2R target relative to that actual fill, not a
        # hypothetical previous close. This policy is never tuned on holdout.
        entry = float(entry_bar.open)
        entry += spread + point * slippage_points if decision.direction == 'BUY' else -point * slippage_points
        final = evaluate_setup(context, symbol, as_of=as_of, direction=decision.direction,
                               entry=entry, spread=spread)
        if not final.allowed:
            rejection_counts['Next-bar geometry/spread rejected'] += 1
            continue
        trade = simulate_position(data, index, final.direction, final.entry,
                                  final.stop_loss, final.take_profit, point,
                                  slippage_points, commission_bps, max_hold_bars)
        trade['setup_type'] = final.setup_type
        trade['signal_bar_open_utc'] = context['M15'].index[-1].isoformat()
        # An unclosed history-boundary trade is not a completed observation.
        if trade['reason'] == 'TIME_EXIT' and trade['exit_index'] == len(data) - 1 and index + max_hold_bars > len(data):
            rejection_counts['Incomplete holding window at history boundary'] += 1
            continue
        last_exit = trade.pop('exit_index')
        trades.append(trade)
    metrics = compute_metrics_r([t['realized_r'] for t in trades])
    return json_safe({
        'status': 'COMPLETED', 'strategy_version': STRATEGY_VERSION,
        'scope': 'Structural candidate benchmark ONLY; not full unified/news/risk/live pipeline',
        'holdout_fraction': holdout, 'formation_bars': split_index,
        'holdout_first_bar_utc': data.index[split_index].isoformat(),
        'holdout_last_bar_utc': data.index[-1].isoformat(),
        'parameter_fitting': 'None; fixed rules and costs, no optimization on either partition',
        'eligible_candidates': eligible_candidates, 'rejections': dict(rejection_counts),
        'metrics': metrics, 'trades': trades,
        'sufficient_sample_100_trades': len(trades) >= 100,
        'eligible_for_live': False,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=BROKER_SYMBOLS, help=argparse.SUPPRESS)
    parser.add_argument('--bars', type=int, default=6000)
    parser.add_argument('--timeout', type=float, default=15.0)
    parser.add_argument('--coverage-only', action='store_true')
    parser.add_argument('--holdout', type=float, default=0.2)
    parser.add_argument('--commission-bps', type=float, default=None)
    parser.add_argument('--slippage-points', type=float, default=1.0)
    parser.add_argument('--max-hold-bars', type=int, default=8)
    parser.add_argument('--symbols', nargs='+', choices=BROKER_SYMBOLS, default=list(BROKER_SYMBOLS))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--publish-latest', action='store_true',
                        help='Also publish this report as latest, preserving its previous version')
    args = parser.parse_args(argv)
    if args.worker:
        try:
            result = _worker(args.worker, args.bars)
        except Exception as exc:
            result = {'status': 'UNAVAILABLE', 'error': str(exc)}
        print(json.dumps(json_safe(result), allow_nan=False))
        return 0
    if args.bars < 400 or args.timeout <= 0 or not 0 < args.holdout < 1:
        parser.error('bars >= 400, timeout > 0, and 0 < holdout < 1 are required')
    if args.slippage_points < 0 or (args.commission_bps is not None and args.commission_bps < 0) or args.max_hold_bars < 1:
        parser.error('Costs must be non-negative and max-hold-bars >= 1')
    now = datetime.now(timezone.utc)
    report_path = args.output or ROOT / 'quant_reports' / 'institutional_strategy_latest.json'
    cache_dir = ROOT / 'quant_reports' / ('institutional_strategy_cache_' + now.strftime('%Y%m%dT%H%M%SZ'))
    report = {
        'generated_at_utc': now.isoformat(), 'source': 'Direct read-only MT5 broker history',
        'requested_bars_per_timeframe': args.bars, 'assets': {},
        'cost_policy': {
            'spread': 'Actual historical bar spread points times broker point; intrabar spread variation unavailable',
            'slippage_points_each_fill': args.slippage_points,
            'slippage_source': 'Explicit research assumption, not measured realized broker slippage',
            'commission_bps_each_side': args.commission_bps,
            'commission_known': args.commission_bps is not None,
            'swap': 'Not modeled; max holding horizon is bounded and this is not a live-readiness report',
            'max_hold_M15_bars': args.max_hold_bars,
        },
        'limitations': [
            'No synthesized bars, filled gaps, invented executions, or guessed missing history',
            'Broker-loaded history may be shorter than requested; reported dates are authoritative',
            'OHLC cannot reveal intrabar path; stop first if ambiguous, BE effective next bar',
            'Actual latency, order rejection, news blackouts and full unified confluence are not replayed',
            'No institutional profitability or live authorization conclusion can be drawn from this benchmark',
            'Future bar openings beyond 30 seconds invalidate the UTC timestamp basis; no automatic timezone correction is made',
        ],
        'eligible_for_live': False,
    }
    for symbol in args.symbols:
        print(f'Reading {symbol}: up to {args.bars} genuine bars per timeframe...', flush=True)
        raw = read_broker_history(symbol, args.bars, args.timeout)
        asset = {'status': raw.get('status'), 'broker_symbol': BROKER_SYMBOLS[symbol]}
        if raw.get('status') != 'OK':
            asset['error'] = raw.get('error', 'Unknown broker error')
            report['assets'][symbol] = asset
            print(f'{symbol}: {asset["error"]}', flush=True)
            continue
        frames, coverage = prepare_frames(raw, pd.Timestamp(now))
        asset.update(specifications=raw['specifications'], coverage=coverage)
        bad_clock = any(item.get('future_bars', 0) > 0 for item in coverage.values())
        if bad_clock:
            asset['status'] = 'CLOCK_ANOMALY'
            asset['timestamp_basis_verified'] = False
            asset['benchmark'] = {
                'status': 'NOT_RUN',
                'reason': 'Broker bar openings occur in the future relative to UTC; historical killzone times are unverified',
                'eligible_for_live': False,
            }
        cache_dir.mkdir(parents=True, exist_ok=True)
        for tf, frame in frames.items():
            filename = cache_dir / f'{symbol}_{tf}.csv'
            frame.to_csv(filename, float_format='%.10g')
            coverage[tf]['cache_file'] = str(filename)
        if not args.coverage_only and not bad_clock:
            asset['benchmark'] = benchmark(
                frames, symbol, raw['specifications'], args.holdout,
                args.commission_bps or 0.0, args.slippage_points, args.max_hold_bars,
            )
        report['assets'][symbol] = asset
        print(f'{symbol}: ' + ', '.join(f'{tf}={item.get("completed_bars",0)} completed bars' for tf,item in coverage.items()), flush=True)
    available = sum(asset['status'] == 'OK' for asset in report['assets'].values())
    anomalies = [symbol for symbol, asset in report['assets'].items() if asset['status'] == 'CLOCK_ANOMALY']
    report['status'] = ('CLOCK_ANOMALY' if anomalies else 'SOURCE_UNAVAILABLE' if not available
                        else 'COVERAGE_ONLY' if args.coverage_only else 'RESEARCH_BENCHMARK')
    if anomalies:
        report['clock_validation'] = {
            'passed': False, 'affected_symbols': anomalies,
            'policy': 'MT5 timestamps treated as UTC exactly as returned; no timezone shifting',
            'prior_benchmark_validity': 'INVALIDATED: earlier reports filtered future bars without verifying source UTC clock',
            'required_resolution': 'Verify broker/server timestamp basis against independently observed UTC before any session-based replay',
        }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(json_safe(report), indent=2, allow_nan=False), encoding='utf-8')
    if args.publish_latest and report_path.resolve() != (ROOT / 'quant_reports' / 'institutional_strategy_latest.json').resolve():
        latest = ROOT / 'quant_reports' / 'institutional_strategy_latest.json'
        preserved = latest.with_name('institutional_strategy_latest_pre_clock_check.json')
        if latest.exists() and not preserved.exists():
            shutil.copy2(latest, preserved)
        if anomalies:
            report['invalidated_prior_reports'] = [str(path) for path in sorted(
                (ROOT / 'quant_reports').glob('institutional_strategy_*_pre_clock_check.json'))]
            report['canonical_clock_check_report'] = str(report_path.resolve())
        latest.write_text(json.dumps(json_safe(report), indent=2, allow_nan=False), encoding='utf-8')
    print(f'Report: {report_path}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
