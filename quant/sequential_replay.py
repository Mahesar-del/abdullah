"""Stepwise paper replay of the fixed structural entry hypothesis.

Input OHLC is broker Bid. Optional ask_open/high/low/close are observed Ask
bars. Otherwise an absolute per-bar ``spread`` column overrides the explicitly
configured constant-spread assumption. No full-unified/news/ML edge is claimed.
"""
from collections import Counter
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from engines.institutional_setup import (
    ALLOWED_SYMBOLS, MIN_BARS, MIN_RR, STRATEGY_VERSION, TIMEFRAMES,
    TF_MINUTES, evaluate_setup, in_killzone, normalize_symbol,
)


def _stamp(value):
    result = pd.Timestamp(value)
    if result.tzinfo is None:
        raise ValueError('Replay dates and candle indexes must be timezone aware')
    return result.tz_convert('UTC')


def _json(value):
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _number(value, label, *, positive=False):
    result = float(value)
    if not math.isfinite(result) or (result <= 0 if positive else result < 0):
        raise ValueError(f'{label} must be finite and {"positive" if positive else "nonnegative"}')
    return result


def _validate_frames(frames):
    output = {}
    required = set(TIMEFRAMES)
    if not required.issubset(frames):
        raise ValueError(f'Missing required frames: {sorted(required - set(frames))}')
    for tf, frame in frames.items():
        frame = frames.get(tf)
        if frame is None or not isinstance(frame.index, pd.DatetimeIndex):
            raise ValueError(f'{tf}: UTC OHLC frame is required')
        if frame.index.tz is None or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
            raise ValueError(f'{tf}: timestamps must be aware, unique and sorted')
        if not {'open', 'high', 'low', 'close'}.issubset(frame.columns):
            raise ValueError(f'{tf}: missing OHLC columns')
        # Price values are checked only when a bar is observed, never by scanning
        # future OHLC before the decision cursor reaches it.
        frame = frame.copy(deep=False)
        frame.index = frame.index.tz_convert('UTC')
        output[tf] = frame
    return output


def _tail_ema(values, span):
    """Exact adjust=False EMA for one already-visible finite prefix.

    It deliberately starts at the same oldest (up-to-400th) bar supplied to
    ``evaluate_setup``.  Thus it is an online-equivalent prefilter, not an
    indicator calculated with future observations or hidden longer history.
    """
    alpha = 2.0 / (span + 1.0)
    result = float(values[0])
    for value in values[1:]:
        result += alpha * (float(value) - result)
    return result


def _spread(row, configured, *, close=False):
    side = 'close' if close else 'open'
    if f'ask_{side}' in row.index:
        return _number(float(row[f'ask_{side}']) - float(row[side]), 'Observed spread'), 'OBSERVED_ASK_OHLC'
    if 'spread' in row.index:
        return _number(row['spread'], 'Per-bar absolute spread'), 'PER_BAR_SPREAD_ASSUMPTION'
    return configured, 'CONSTANT_SPREAD_ASSUMPTION'


def _open_prices(row, configured):
    bid = _number(row['open'], 'Bid open', positive=True)
    spread, source = _spread(row, configured)
    ask = _number(row['ask_open'], 'Ask open', positive=True) if 'ask_open' in row.index else bid + spread
    return bid, ask, spread, source


def _closed_prices(row, configured):
    bid = {key: _number(row[key], f'Bid {key}', positive=True) for key in ('open', 'high', 'low', 'close')}
    if bid['low'] > min(bid['open'], bid['close']) or bid['high'] < max(bid['open'], bid['close']) or bid['high'] < bid['low']:
        raise ValueError('Invalid observed Bid candle geometry')
    columns = [f'ask_{key}' for key in ('open', 'high', 'low', 'close')]
    if any(key in row.index for key in columns) and not all(key in row.index for key in columns):
        raise ValueError('Partial Ask OHLC columns cannot define an executable price path')
    spread, source = _spread(row, configured, close=True)
    if all(key in row.index for key in columns):
        ask = {key: _number(row[f'ask_{key}'], f'Ask {key}', positive=True) for key in bid}
        if any(ask[key] < bid[key] for key in bid):
            raise ValueError('Observed Ask is below Bid')
        if ask['low'] > min(ask['open'], ask['close']) or ask['high'] < max(ask['open'], ask['close']) or ask['high'] < ask['low']:
            raise ValueError('Invalid observed Ask candle geometry')
    else:
        ask = {key: value + spread for key, value in bid.items()}
    return bid, ask, spread, source


@dataclass
class _Position:
    identifier: int
    direction: str
    signal_at: pd.Timestamp
    entry_at: pd.Timestamp
    expires_at: pd.Timestamp | None
    entry: float
    initial_stop: float
    stop: float
    target: float
    risk_distance: float
    risk_cash: float
    entry_spread: float
    spread_source: str
    setup_type: str
    be_active: bool = False
    partial_taken: bool = False
    remaining_fraction: float = 1.0
    realized_r: float = 0.0


def run_sequential_replay(
    frames, symbol, start=None, end=None, *, spread=0.0, slippage=0.0,
    commission=0.0, initial_balance=100000.0, risk_pct=1.0,
    validity_hours=4.0, exit_policy='fixed_expiry', on_event=None, evaluator=None,
    decision_timeframe='M15', decision_prefilter=None,
):
    """Replay observations in time order, using at most 400 completed bars/TF.

    Costs are absolute instrument-price units: full spread, and slippage and
    commission PER SIDE. Bars supplied by the caller are never fabricated.
    Structural decisions are queued at the selected completed decision candle
    and entered at the next observed decision-timeframe open only if the
    ORIGINAL levels still provide at least 2R.
    ``fixed_expiry`` closes after the configured validity.  ``gold_h1_trail``
    takes 50% at +1R, protects the remainder at breakeven, then trails behind
    subsequently confirmed H1 pivots; it has no fixed position expiry.

    This is a causal structural-entry experiment, NOT a replay of unknown
    historical news, full unified scoring, broker fills or market depth.
    """
    # A caller may supply a separate pure causal evaluator, for example the
    # ICT location hypothesis.  It receives the same closed-only 400-bar
    # frame window as the default setup evaluator and never gains execution
    # rights through this research function.
    evaluator = evaluator or evaluate_setup
    use_default_prefilters = evaluator is evaluate_setup
    symbol = normalize_symbol(symbol)
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError('Replay is restricted to XAUUSD, US30 and SPX500')
    frames = _validate_frames(frames)
    decision_timeframe = str(decision_timeframe).upper()
    if decision_timeframe not in frames:
        raise ValueError(f'{decision_timeframe}: decision frame is not supplied')
    spread, slippage, commission = [_number(v, name) for v, name in
                                    ((spread, 'Spread'), (slippage, 'Slippage'), (commission, 'Commission'))]
    balance = _number(initial_balance, 'Initial balance', positive=True)
    initial_balance = balance
    risk_pct = _number(risk_pct, 'Risk percentage', positive=True)
    if risk_pct > 100:
        raise ValueError('Risk percentage cannot exceed 100')
    validity_hours = _number(validity_hours, 'Validity hours', positive=True)
    if exit_policy not in {'fixed_expiry', 'gold_h1_trail'}:
        raise ValueError('exit_policy must be fixed_expiry or gold_h1_trail')
    bars = frames[decision_timeframe]
    if bars.empty:
        raise ValueError(f'{decision_timeframe} history is empty')
    start_at = _stamp(start) if start is not None else bars.index[0]
    end_at = _stamp(end) if end is not None else bars.index[-1] + pd.Timedelta(minutes=15)
    if end_at < start_at:
        raise ValueError('Replay end precedes start')
    duration = pd.Timedelta(minutes=TF_MINUTES[decision_timeframe])
    endings = {tf: frame.index + pd.Timedelta(minutes=TF_MINUTES[tf]) for tf, frame in frames.items()}
    closes = {tf: frame.close.to_numpy(dtype=float, copy=False) for tf, frame in frames.items()}
    opens = {tf: frame.open.to_numpy(dtype=float, copy=False) for tf, frame in frames.items()}
    highs = {tf: frame.high.to_numpy(dtype=float, copy=False) for tf, frame in frames.items()}
    lows = {tf: frame.low.to_numpy(dtype=float, copy=False) for tf, frame in frames.items()}
    events, trades, equity = [], [], []
    rejected, spread_sources = Counter(), Counter()
    position = pending = None
    next_id, peak_equity, max_dd = 1, balance, 0.0
    last_mark = balance
    last_observation = None
    counts = Counter()

    def emit(kind, at, **details):
        event = _json(dict(type=kind, at=at, symbol=symbol, **details))
        events.append(event)
        if on_event is not None:
            on_event(dict(event))

    def mark(at, observed_exit=None):
        nonlocal peak_equity, max_dd, last_mark, last_observation
        value = balance
        if position is not None and observed_exit is not None:
            sign = 1 if position.direction == 'BUY' else -1
            leg_r = (sign * (observed_exit - sign * slippage - position.entry) - 2 * commission) / position.risk_distance
            value += position.risk_cash * (position.realized_r + position.remaining_fraction * leg_r)
        peak_equity = max(peak_equity, value)
        max_dd = max(max_dd, (peak_equity - value) / peak_equity if peak_equity > 0 else 0)
        last_mark, last_observation = value, at
        equity.append(_json(dict(at=at, balance=round(balance, 6), equity=round(value, 6))))

    def close(at, raw_price, reason, *, ambiguous=False, gap=False):
        nonlocal position, balance
        sign = 1 if position.direction == 'BUY' else -1
        fill = raw_price - sign * slippage
        leg_r = (sign * (fill - position.entry) - 2 * commission) / position.risk_distance
        pnl_r = position.realized_r + position.remaining_fraction * leg_r
        cash = position.risk_cash * pnl_r
        balance += cash
        trade = dict(
            id=position.identifier, symbol=symbol, direction=position.direction,
            signal_at=position.signal_at, entry_at=position.entry_at, exit_at=at,
            entry_price=position.entry, exit_price=fill, initial_stop=position.initial_stop,
            final_stop=position.stop, take_profit=position.target,
            initial_risk_distance=position.risk_distance, risk_amount=position.risk_cash,
            entry_spread=position.entry_spread, spread_source=position.spread_source,
            setup_type=position.setup_type, exit_reason=reason, pnl_r=pnl_r,
            pnl_cash=cash, balance_after=balance, ambiguous_bar=ambiguous, gap_fill=gap,
            be_active=position.be_active, partial_taken=position.partial_taken,
            partial_realized_r=position.realized_r,
        )
        trades.append(_json(trade))
        emit('EXIT', at, trade=trade)
        position = None
        mark(at)

    def visible_frames(at):
        visible = {}
        latest = {}
        for tf, frame in frames.items():
            cutoff = int(endings[tf].searchsorted(at, side='right'))
            prefix = frame.iloc[max(0, cutoff - 400):cutoff]
            # Runtime guard, not merely a promise in comments. No strategy
            # invocation can receive a higher-timeframe candle before it closes.
            if len(prefix) and prefix.index[-1] + pd.Timedelta(minutes=TF_MINUTES[tf]) > at:
                raise RuntimeError(f'Future {tf} candle reached a decision')
            visible[tf] = prefix
            latest[tf] = None if prefix.empty else prefix.index[-1] + pd.Timedelta(minutes=TF_MINUTES[tf])
        return visible, latest

    def aligned_direction(at):
        """Return strict shared trend, WAIT, or None when full validation is needed.

        This removes obviously non-aligned decisions before creating three
        pandas copies.  Each EMA is calculated from the same completed,
        maximum-400-bar prefix later passed to the authoritative setup gate.
        """
        directions = []
        for tf, frame in frames.items():
            cutoff = int(endings[tf].searchsorted(at, side='right'))
            if cutoff < MIN_BARS:
                return None
            if frame.index[cutoff - 1] + pd.Timedelta(minutes=TF_MINUTES[tf]) < at - pd.Timedelta(minutes=TF_MINUTES[tf] * 1.5):
                return None
            values = closes[tf][max(0, cutoff - 400):cutoff]
            # Invalid or non-finite values are left to the authoritative gate;
            # they must never be hidden by an optimisation shortcut.
            if not np.isfinite(values).all() or (values <= 0).any():
                return None
            e50, e200, price = _tail_ema(values, 50), _tail_ema(values, 200), float(values[-1])
            directions.append('BUY' if price > e50 > e200 else ('SELL' if price < e50 < e200 else 'WAIT'))
        return directions[0] if len(set(directions)) == 1 and directions[0] != 'WAIT' else 'WAIT'

    def trigger_possible(at, direction):
        """Exact cheap rejection of M15 bars that cannot be a reclaim setup."""
        cutoff = int(endings['M15'].searchsorted(at, side='right'))
        start = max(0, cutoff - 400)
        if cutoff - start < 6:
            return None
        values = closes['M15'][start:cutoff]
        high, low, opened = highs['M15'][cutoff - 1], lows['M15'][cutoff - 1], opens['M15'][cutoff - 1]
        previous = closes['M15'][cutoff - 2]
        ema20_before = _tail_ema(values[:-1], 20)
        swing_low = float(lows['M15'][cutoff - 6:cutoff - 1].min())
        swing_high = float(highs['M15'][cutoff - 6:cutoff - 1].max())
        close = float(values[-1])
        if direction == 'BUY':
            return ((low < swing_low < close and close > opened) or
                    (low <= ema20_before < close and close > opened and close > previous))
        return ((high > swing_high > close and close < opened) or
                (high >= ema20_before > close and close < opened and close < previous))

    mark(start_at)
    first = int(bars.index.searchsorted(start_at, side='left'))
    last = int(bars.index.searchsorted(end_at, side='right'))
    for opened_at, row in bars.iloc[first:last].iterrows():
        closed_at = opened_at + duration
        try:
            bid_open, ask_open, entry_spread, source = _open_prices(row, spread)
        except (ValueError, TypeError) as exc:
            rejected['INVALID_OPEN_DATA'] += 1
            emit('DATA_GAP', opened_at, reason=str(exc))
            continue
        counts['observed_opens'] += 1
        # Gap prices exist at the OPEN. Only these values, not the forthcoming
        # high/low/close, may settle an already-open position at this point.
        if position is not None:
            price = bid_open if position.direction == 'BUY' else ask_open
            stop_hit = price <= position.stop if position.direction == 'BUY' else price >= position.stop
            tp_hit = price >= position.target if position.direction == 'BUY' else price <= position.target
            if stop_hit:
                close(opened_at, price, 'BE_STOP' if position.be_active else 'SL', gap=True)
            elif tp_hit:
                close(opened_at, price, 'TP', gap=True)
            elif position.expires_at is not None and opened_at >= position.expires_at:
                close(opened_at, price, 'EXPIRED', gap=True)
            else:
                mark(opened_at, price)

        if pending is not None and position is None:
            proposal, signal_at = pending
            pending = None
            if opened_at < signal_at:
                raise RuntimeError('Pending setup entered before its decision')
            expires_at = signal_at + pd.Timedelta(hours=validity_hours)
            if opened_at >= expires_at or not in_killzone(opened_at):
                rejected['PENDING_EXPIRED_OR_OUTSIDE_KILLZONE'] += 1
                emit('ENTRY_CANCELLED', opened_at, signal_at=signal_at, reason='Expired setup or entry outside killzone')
            elif balance <= 0:
                rejected['NO_CAPITAL'] += 1
                emit('ENTRY_CANCELLED', opened_at, signal_at=signal_at, reason='No positive capital remains')
            else:
                sign = 1 if proposal.direction == 'BUY' else -1
                entry_fill = (ask_open if sign == 1 else bid_open) + sign * slippage
                stop, target = float(proposal.stop_loss), float(proposal.take_profit)
                risk_distance = sign * (entry_fill - stop)
                reward = sign * (target - entry_fill)
                rr = reward / risk_distance if risk_distance > 0 else -1
                if risk_distance <= 0 or reward <= 0 or rr + 1e-9 < MIN_RR:
                    rejected['NEXT_OPEN_LEVELS_OR_RR'] += 1
                    emit('ENTRY_CANCELLED', opened_at, signal_at=signal_at,
                         reason='Next executable open no longer offers valid original levels and 2R', risk_reward=rr)
                elif entry_spread > 0.2 * risk_distance:
                    rejected['NEXT_OPEN_EXCESS_SPREAD'] += 1
                    emit('ENTRY_CANCELLED', opened_at, signal_at=signal_at, reason='Spread exceeds 20% of initial stop distance')
                else:
                    position = _Position(
                        next_id, proposal.direction, signal_at, opened_at,
                        (None if exit_policy == 'gold_h1_trail' else expires_at),
                        entry_fill, stop, stop, target, risk_distance,
                        balance * risk_pct / 100.0, entry_spread, source, proposal.setup_type,
                    )
                    next_id += 1
                    spread_sources[source] += 1
                    emit('ENTRY', opened_at, id=position.identifier, direction=position.direction,
                         entry_price=entry_fill, stop_loss=stop, take_profit=target,
                         risk_reward=rr, risk_amount=position.risk_cash, signal_at=signal_at)
                    mark(opened_at, bid_open if sign == 1 else ask_open)

        if closed_at > end_at:
            # A forming/future bar's range is not observable by the replay end.
            continue
        try:
            bid, ask, closing_spread, source = _closed_prices(row, spread)
        except (ValueError, TypeError) as exc:
            rejected['INVALID_COMPLETED_DATA'] += 1
            emit('DATA_GAP', closed_at, reason=str(exc))
            continue
        counts['completed_bars'] += 1
        if position is not None:
            prices = bid if position.direction == 'BUY' else ask
            if position.expires_at is not None and position.expires_at < closed_at:
                # Non-aligned custom expiry has no exact quote. Do not award
                # a target from the post-expiry part of this OHLC bar.
                close(closed_at, prices['close'], 'EXPIRED_LATE_OBSERVATION')
            else:
                hit_stop = prices['low'] <= position.stop if position.direction == 'BUY' else prices['high'] >= position.stop
                hit_target = prices['high'] >= position.target if position.direction == 'BUY' else prices['low'] <= position.target
                if hit_stop:
                    close(closed_at, position.stop, 'BE_STOP' if position.be_active else 'SL', ambiguous=hit_target)
                elif hit_target:
                    close(closed_at, position.target, 'TP')
                elif position.expires_at is not None and closed_at >= position.expires_at:
                    close(closed_at, prices['close'], 'EXPIRED')
                else:
                    reached_r = (prices['high'] - position.entry >= position.risk_distance
                                 if position.direction == 'BUY' else position.entry - prices['low'] >= position.risk_distance)
                    if not position.be_active and reached_r:
                        sign = 1 if position.direction == 'BUY' else -1
                        position.stop = position.entry + sign * closing_spread
                        position.be_active = True
                        emit('BE_ARMED', closed_at, id=position.identifier, stop_loss=position.stop,
                             effective_from='NEXT_OBSERVED_BAR', spread=closing_spread)
                    if exit_policy == 'gold_h1_trail' and not position.partial_taken and reached_r:
                        position.realized_r += 0.5
                        position.remaining_fraction = 0.5
                        position.partial_taken = True
                        emit('PARTIAL_1R', closed_at, id=position.identifier,
                             fraction=0.5, realized_r=position.realized_r,
                             remainder_fraction=position.remaining_fraction)
                    if exit_policy == 'gold_h1_trail' and position.partial_taken and closed_at.minute == 0:
                        from engines.ict_location import _confirmed_pivots
                        cutoff = int(endings['H1'].searchsorted(closed_at, side='right'))
                        h1_visible = frames['H1'].iloc[max(0, cutoff - 400):cutoff]
                        pivots = _confirmed_pivots(h1_visible)
                        kind = 'LOW' if position.direction == 'BUY' else 'HIGH'
                        candidates = [item[2] for item in pivots if item[0] == kind]
                        if candidates:
                            sign = 1 if position.direction == 'BUY' else -1
                            candidate_stop = candidates[-1] - sign * closing_spread
                            improves = candidate_stop > position.stop if sign == 1 else candidate_stop < position.stop
                            if improves:
                                position.stop = candidate_stop
                                emit('H1_TRAIL', closed_at, id=position.identifier,
                                     stop_loss=position.stop, pivot=kind)
                    mark(closed_at, prices['close'])
        # A flat account has no mark-to-market movement.  Recording an equity
        # snapshot on every M5 close only duplicates the same balance millions
        # of times in a long course replay, without changing entries, exits or
        # drawdown.  Keep the initial mark and every position/exit mark above;
        # this makes the report sparse while preserving all trading results.

        # The decision clock advances only AFTER that entire candle is known.
        # While a position is held there is no new overlapping setup/entry.
        if position is not None or pending is not None or not in_killzone(closed_at):
            continue
        if decision_prefilter is not None and not decision_prefilter(closed_at):
            rejected['DECISION_CLOCK_PREFILTER'] += 1
            continue
        if use_default_prefilters:
            fast_direction = aligned_direction(closed_at)
            if fast_direction == 'WAIT':
                rejected['M15/H1/H4 do not share the strict Close/EMA50/EMA200 chain'] += 1
                continue
            if fast_direction is not None and not trigger_possible(closed_at, fast_direction):
                rejected['No completed liquidity-sweep reclaim or EMA20 pullback reclaim'] += 1
                continue
        visible, latest = visible_frames(closed_at)
        if any(len(visible[tf]) < MIN_BARS for tf in frames):
            rejected['WARMUP_INSUFFICIENT'] += 1
            continue
        counts['strategy_decisions'] += 1
        if use_default_prefilters:
            proposal = evaluator(visible, symbol, decision_timeframe, as_of=closed_at, spread=closing_spread)
        else:
            proposal = evaluator(visible, symbol, as_of=closed_at, spread=closing_spread)
        if not proposal.allowed:
            for reason in proposal.reasons:
                rejected[reason] += 1
            continue
        pending = proposal, closed_at
        emit('SETUP', closed_at, direction=proposal.direction, setup_type=proposal.setup_type,
             reference_entry=proposal.entry, stop_loss=proposal.stop_loss,
             take_profit=proposal.take_profit, latest_completed=latest)

    open_positions = []
    if position is not None:
        open_positions.append(_json(dict(
            id=position.identifier, symbol=symbol, direction=position.direction,
            signal_at=position.signal_at, entry_at=position.entry_at,
            entry_price=position.entry, initial_stop=position.initial_stop,
            current_stop=position.stop, take_profit=position.target,
            expires_at=position.expires_at, risk_amount=position.risk_cash,
            original_risk_distance=position.risk_distance, be_active=position.be_active,
            partial_taken=position.partial_taken, partial_realized_r=position.realized_r,
            unrealized_pnl=last_mark - balance, marked_at=last_observation,
            note='OPEN at replay end; not forcibly converted to a closed trade',
        )))
    returns_r = [float(trade['pnl_r']) for trade in trades]
    gains = sum(value for value in returns_r if value > 0)
    losses = -sum(value for value in returns_r if value < 0)
    wins, loss_count = sum(value > 0 for value in returns_r), sum(value < 0 for value in returns_r)
    metadata = dict(
        strategy_version=(STRATEGY_VERSION if use_default_prefilters else getattr(evaluator, '__name__', 'custom_causal_evaluator')),
        scope='CAUSAL_PRICE_ENTRY_RULES_ONLY_NOT_FULL_UNIFIED',
        requested_start=start_at, requested_end=end_at, symbol=symbol,
        history_buffer_bars_per_timeframe=400, strategy_timeframes=list(TIMEFRAMES),
        decision_timeframe=decision_timeframe, entry_timing=f'NEXT_OBSERVED_{decision_timeframe}_OPEN',
        exit_resolution=f'COMPLETED_{decision_timeframe}_OHLC_STOP_FIRST; BE_ACTIVE_FROM_NEXT_BAR',
        exit_policy=exit_policy,
        validity_hours=validity_hours, costs_price_units=dict(full_spread=spread, slippage_per_side=slippage,
                                                          commission_per_side=commission),
        spread_priority='Observed Ask OHLC > per-bar absolute spread > configured constant assumption',
        spread_sources=dict(spread_sources), initial_balance=initial_balance,
        risk_pct_per_trade=risk_pct, parameter_selection='FIXED_RULES_NO_OPTIMIZATION',
        unknown_historical_filters=['unified confluence', 'point-in-time news', 'macro releases', 'broker execution constraints'],
        limitations=['OHLC cannot establish exact intrabar tick order; stop-first is a conservative convention',
                     'No observed broker order fills, swap schedule or liquidity/depth reconstruction',
                     'History availability/gaps must be reported by the source collector; no bars are synthesized'],
        counts=dict(counts), rejected=dict(rejected),
    )
    return _json(dict(
        metadata=metadata, events=events, trades=trades, equity=equity,
        open_positions=open_positions,
        pending_setup=None if pending is None else dict(decision_at=pending[1], direction=pending[0].direction,
                                                        note='No next executable open observed within replay window'),
        summary=dict(closed_trades=len(trades), wins=wins, losses=loss_count,
                     breakeven=len(trades) - wins - loss_count,
                     win_rate_pct=100.0 * wins / len(trades) if trades else None,
                     net_r=sum(returns_r), expectancy_r=sum(returns_r) / len(trades) if trades else None,
                     profit_factor=gains / losses if losses else None,
                     profit_factor_unbounded=bool(gains and not losses),
                     final_balance=balance, final_marked_equity=last_mark,
                     net_return_pct=(balance / initial_balance - 1) * 100,
                     max_drawdown_pct=max_dd * 100, open_positions=len(open_positions)),
    ))
