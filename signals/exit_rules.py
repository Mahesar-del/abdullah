"""Causal, conservative exit replay for recorded signal/paper results.

OHLC does not reveal whether a high or low happened first. Existing stops win
ties, and a newly armed breakeven stop never applies to an earlier bar extreme.
Live monitoring uses only a fresh observed close, not an unfinished bar's range.
"""
from dataclasses import dataclass
from datetime import timedelta
import math

import pandas as pd


@dataclass
class ExitEvaluation:
    state: dict
    outcome: str | None = None
    exit_price: float | None = None
    exit_at: object | None = None
    note: str = ''


def _utc(value):
    stamp = pd.Timestamp(value)
    return stamp.tz_localize('UTC') if stamp.tzinfo is None else stamp.tz_convert('UTC')


def evaluate_signal_exit(
    df, *, direction, entry, stop_loss, take_profit, generated_at, now,
    half_spread=0.0, slippage=0.0, commission=0.0, prior_state=None,
    valid_until=None, price_basis='mid', entry_is_executable=False,
):
    """Evaluate completed M1 bars and a recent price, preserving the entry basis.

    Cost inputs are captured once. ``price_basis='bid'`` is used for MT5 candles;
    unknown legacy/proxy feeds retain the prior midpoint modeling convention.
    No missing past ticks or original trade fills are reconstructed as facts.
    """
    generated_at, now = _utc(generated_at), _utc(now)
    expiry = _utc(valid_until) if valid_until is not None else None
    one_minute = timedelta(minutes=1)
    state = dict(prior_state or {})
    values = [entry, stop_loss, take_profit, half_spread, slippage, commission]
    if direction not in ('BUY', 'SELL') or not all(math.isfinite(float(v)) for v in values):
        return ExitEvaluation(state, note='Invalid direction or non-finite price/cost input')
    if any(float(v) < 0 for v in [half_spread, slippage, commission]):
        return ExitEvaluation(state, note='Negative execution costs are invalid')
    if df is None or df.empty or not {'open', 'high', 'low', 'close'}.issubset(df.columns):
        return ExitEvaluation(state, note='No evaluable market bars')
    bars = df.copy()
    bars.index = pd.to_datetime(bars.index, utc=True)
    bars = bars[~bars.index.duplicated(keep='last')].sort_index()
    bars = bars[bars.index <= now]
    if bars.empty:
        return ExitEvaluation(state, note='Only future bars were supplied')

    if not state:
        sign = 1.0 if direction == 'BUY' else -1.0
        if entry_is_executable:
            fill_entry = float(entry)
        elif price_basis == 'bid':
            fill_entry = float(entry) + (2.0 * float(half_spread) if direction == 'BUY' else 0.0) + sign * float(slippage)
        else:
            fill_entry = float(entry) + sign * (float(half_spread) + float(slippage))
        initial_risk = abs(fill_entry - float(stop_loss))
        valid_levels = (
            float(stop_loss) < fill_entry < float(take_profit)
            if direction == 'BUY' else float(take_profit) < fill_entry < float(stop_loss)
        )
        if initial_risk <= 0 or not valid_levels:
            return ExitEvaluation(state, note='Invalid initial protective levels')
        # Available OHLC coverage is explicit. It is not proof of an unobserved
        # earlier trade path, especially when initializing a legacy signal.
        coverage = 'PARTIAL' if bars.index[0] > generated_at.ceil('min') else 'AVAILABLE_FROM_ENTRY'
        state = {
            'version': 1, 'fill_entry': fill_entry, 'initial_risk': initial_risk,
            'initial_stop': float(stop_loss), 'current_sl': float(stop_loss),
            'half_spread': float(half_spread), 'slippage': float(slippage),
            'commission': float(commission), 'be_active': False,
            'be_activated_at': None, 'last_bar_open': None,
            'initialized_at': now.isoformat(), 'history_coverage': coverage,
            'cost_basis': ('PAPER_QUOTE_REFERENCE_ENTRY__EXIT_COSTS_MODELED'
                           if entry_is_executable else 'MODELED_AT_FIRST_EVALUATION'),
            'price_basis': price_basis,
        }

    required = ('fill_entry', 'initial_risk', 'initial_stop', 'current_sl', 'half_spread', 'slippage', 'commission')
    if any(k not in state or not math.isfinite(float(state[k])) for k in required):
        return ExitEvaluation(state, note='Invalid persisted exit state; manual review required')
    if float(state['initial_risk']) <= 0:
        return ExitEvaluation(state, note='Invalid persisted original risk')
    fill_entry = float(state['fill_entry'])
    initial_risk = float(state['initial_risk'])
    half_spread = float(state['half_spread'])
    slippage = float(state['slippage'])
    price_basis = state.get('price_basis', 'mid')
    be_buffer = 2.0 * half_spread if price_basis == 'bid' else half_spread
    last_bar = _utc(state['last_bar_open']) if state.get('last_bar_open') else None

    def executable_prices(high, low, close, opening):
        # MT5 bars are Bid. A short closes at Ask; a long closes at Bid.
        shift = (0.0 if direction == 'BUY' else 2.0 * half_spread) if price_basis == 'bid' else (-half_spread if direction == 'BUY' else half_spread)
        return high + shift, low + shift, close + shift, opening + shift

    def resolved(outcome, price, stamp, note=''):
        return ExitEvaluation(dict(state), outcome, float(price), stamp.to_pydatetime(), note)

    def stop_result(stop, price, stamp, protected):
        # A gap may fill worse than the stop. Preserve observed adverse gaps.
        exit_fill = min(price, stop) - slippage if direction == 'BUY' else max(price, stop) + slippage
        net_move = (exit_fill - fill_entry) if direction == 'BUY' else (fill_entry - exit_fill)
        net_move -= 2.0 * float(state['commission'])
        # A protected stop is not a guaranteed zero-loss fill across a price gap.
        # Preserve the existing small-cost BE tolerance, but expose material losses.
        outcome = 'BREAKEVEN' if protected and net_move / initial_risk >= -0.05 else 'HIT_SL'
        return resolved(outcome, exit_fill, stamp)

    replay = bars[(bars.index >= generated_at) & (bars.index + one_minute <= now)]
    if last_bar is not None:
        replay = replay[replay.index > last_bar]
    if expiry is not None:
        replay = replay[replay.index + one_minute <= expiry]

    for opened_at, candle in replay.iterrows():
        raw = [float(candle[k]) for k in ('high', 'low', 'close', 'open')]
        if not all(math.isfinite(v) and v > 0 for v in raw):
            return ExitEvaluation(state, note='Invalid OHLC bar; evaluation stopped')
        high, low, close, opening = executable_prices(*raw)
        closed_at = opened_at + one_minute
        armed_at = _utc(state['be_activated_at']) if state.get('be_activated_at') else None
        protected = bool(state.get('be_active')) and armed_at is not None and opened_at >= armed_at
        stop = float(state['current_sl']) if protected else float(state['initial_stop'])
        state['last_bar_open'] = opened_at.isoformat()

        if direction == 'BUY':
            hit_stop, hit_target = low <= stop, high >= float(take_profit)
            if hit_stop:
                return stop_result(stop, min(opening, stop), closed_at, protected)
            if hit_target:
                return resolved('HIT_TP', float(take_profit) - slippage, closed_at)
            reached_r = high - fill_entry >= initial_risk
        else:
            hit_stop, hit_target = high >= stop, low <= float(take_profit)
            if hit_stop:
                return stop_result(stop, max(opening, stop), closed_at, protected)
            if hit_target:
                return resolved('HIT_TP', float(take_profit) + slippage, closed_at)
            reached_r = fill_entry - low >= initial_risk

        if not state.get('be_active') and reached_r:
            state['be_active'] = True
            state['current_sl'] = fill_entry + (be_buffer if direction == 'BUY' else -be_buffer)
            state['be_activated_at'] = closed_at.isoformat()

    # A final completed close is observed at bar end; an unfinished close has no
    # tick timestamp, so require its bar itself to start after signal generation.
    latest_at = bars.index[-1]
    latest = bars.iloc[-1]
    latest_completed = latest_at + one_minute <= now
    observed_at = latest_at + one_minute if latest_completed else latest_at
    fresh = latest_at >= generated_at and timedelta(0) <= now - observed_at <= timedelta(minutes=2)
    if not fresh:
        return ExitEvaluation(state, note='No fresh post-entry price; historical coverage may be incomplete')
    live_close = float(latest['close'])
    if not math.isfinite(live_close) or live_close <= 0:
        return ExitEvaluation(state, note='Invalid latest observed price')
    _, _, price, _ = executable_prices(live_close, live_close, live_close, live_close)
    # Do not take an expiry fill from an old cached bar or invent a price at a
    # missed expiry instant. A late observed expiry is explicitly timestamped now.
    if expiry is not None and now >= expiry:
        return resolved('EXPIRED', price - slippage if direction == 'BUY' else price + slippage, now,
                        'Expiry observed at current available price, not a reconstructed historical fill')

    price_observed_at = observed_at if latest_completed else now
    armed_at = _utc(state['be_activated_at']) if state.get('be_activated_at') else None
    protected = bool(state.get('be_active')) and armed_at is not None and price_observed_at >= armed_at
    stop = float(state['current_sl']) if protected else float(state['initial_stop'])
    if direction == 'BUY':
        if price <= stop:
            return stop_result(stop, price, now, protected)
        if price >= float(take_profit):
            return resolved('HIT_TP', float(take_profit) - slippage, now)
        reached_r = price - fill_entry >= initial_risk
    else:
        if price >= stop:
            return stop_result(stop, price, now, protected)
        if price <= float(take_profit):
            return resolved('HIT_TP', float(take_profit) + slippage, now)
        reached_r = fill_entry - price >= initial_risk
    if not state.get('be_active') and reached_r:
        state['be_active'] = True
        state['current_sl'] = fill_entry + (be_buffer if direction == 'BUY' else -be_buffer)
        state['be_activated_at'] = now.isoformat()
    return ExitEvaluation(state)
