"""Causal, inspectable entry requirements; a research hypothesis, not a profit claim.

The live confluence/news/risk engines remain additional gates. This module uses
only completed broker candles and has no network, database, or order side effects.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


SYMBOL_ALIASES = {'GC=F': 'XAUUSD', '^DJI': 'US30'}
TIMEFRAME_ALIASES = {'5M': 'M5', '15M': 'M15', '1H': 'H1', '4H': 'H4'}
ALLOWED_SYMBOLS = ('XAUUSD', 'US30', 'SPX500')
# M5 is enabled exclusively for the course price-action confirmation leg.
# Existing institutional and ICT engines keep their M15/H1/H4 scope below.
SUPPORTED_TIMEFRAMES = ('M5', 'M15', 'H1', 'H4')
TIMEFRAMES = ('M15', 'H1', 'H4')
TF_MINUTES = {'M5': 5, 'M15': 15, 'H1': 60, 'H4': 240}
MIN_BARS = 200
MIN_RR = 2.0
STRATEGY_VERSION = 'closed-trend-reclaim-v2'

# Gold needs actual completed-candle momentum in addition to structure. Index
# behaviour is qualified separately by the unified cash-session analysis.
GOLD_PROFILE = {
    'min_body_atr': 0.50,
    'min_close_location': 0.70,
    'ema_slope_bars': 5,
    'max_spread_risk_fraction': 0.12,
}


@dataclass
class SetupDecision:
    allowed: bool = False
    direction: str = 'WAIT'
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward: float = 0.0
    setup_type: str = ''
    reasons: List[str] = field(default_factory=list)
    evidence: Dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def normalize_symbol(symbol):
    symbol = str(symbol or '').strip().upper()
    return SYMBOL_ALIASES.get(symbol, symbol)


def normalize_timeframe(timeframe):
    timeframe = str(timeframe or '').strip().upper()
    return TIMEFRAME_ALIASES.get(timeframe, timeframe)


def in_killzone(as_of):
    stamp = pd.Timestamp(as_of)
    if stamp.tzinfo is None:
        raise ValueError('Killzone timestamp must include a timezone')
    hour = stamp.tz_convert('UTC').hour
    return 7 <= hour < 11 or 13 <= hour < 17


def closed_candles(frame, timeframe, as_of):
    """Return validated bars whose full timeframe has elapsed by as_of."""
    timeframe = normalize_timeframe(timeframe)
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError('Only M5, M15, H1 and H4 are permitted')
    if frame is None or not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError(f'{timeframe}: timezone-aware OHLC history is required')
    if frame.index.tz is None:
        raise ValueError(f'{timeframe}: candle timestamps must include a timezone')
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f'{timeframe}: duplicate or out-of-order timestamps')
    stamp = pd.Timestamp(as_of)
    if stamp.tzinfo is None:
        raise ValueError('as_of must include a timezone')
    stamp = stamp.tz_convert('UTC')
    data = frame.copy()
    data.index = data.index.tz_convert('UTC')
    data = data[data.index + pd.Timedelta(minutes=TF_MINUTES[timeframe]) <= stamp]
    cols = ['open', 'high', 'low', 'close']
    if any(col not in data for col in cols):
        raise ValueError(f'{timeframe}: missing OHLC columns')
    data[cols] = data[cols].astype(float)
    if not np.isfinite(data[cols].to_numpy()).all() or (data[cols] <= 0).any().any():
        raise ValueError(f'{timeframe}: non-finite or non-positive prices')
    if ((data.high < data[['open', 'close', 'low']].max(axis=1)) |
            (data.low > data[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError(f'{timeframe}: invalid candle geometry')
    return data


def evaluate_setup(frames, symbol, timeframe='M15', as_of=None, direction=None,
                   entry=None, stop_loss=None, take_profit=None, spread=0.0):
    """Verify trend, a completed reclaim trigger, structural invalidation and 2R.

    Supplying no levels produces a structural candidate for research. Supplying
    live proposal levels checks those exact levels; it never stretches a target
    merely to turn a rejected proposal into an accepted one.
    """
    result = SetupDecision(evidence={'strategy_version': STRATEGY_VERSION})
    symbol, timeframe = normalize_symbol(symbol), normalize_timeframe(timeframe)
    stamp = pd.Timestamp(as_of if as_of is not None else datetime.now(timezone.utc))
    if stamp.tzinfo is None:
        result.reasons.append('as_of must include a timezone')
        return result
    stamp = stamp.tz_convert('UTC')
    result.evidence.update(symbol=symbol, timeframe=timeframe, checked_at=stamp.isoformat())
    if symbol not in ALLOWED_SYMBOLS or timeframe not in TIMEFRAMES:
        result.reasons.append('Outside approved assets/timeframes')
        return result
    if timeframe == 'M15' and not in_killzone(stamp):
        result.reasons.append('Outside M15 killzones [07:00,11:00) / [13:00,17:00) UTC')
        return result

    closed, trends = {}, {}
    for tf in TIMEFRAMES:
        try:
            data = closed_candles(frames.get(tf), tf, stamp)
        except (ValueError, TypeError, KeyError) as exc:
            result.reasons.append(str(exc))
            return result
        if len(data) < MIN_BARS:
            result.reasons.append(f'{tf}: only {len(data)} completed bars; need {MIN_BARS}')
            return result
        last_end = data.index[-1] + pd.Timedelta(minutes=TF_MINUTES[tf])
        if stamp - last_end > pd.Timedelta(minutes=TF_MINUTES[tf] * 1.5):
            result.reasons.append(f'{tf}: history is stale; last bar closed {last_end.isoformat()}')
            return result
        series = data.close
        e50 = float(series.ewm(span=50, adjust=False).mean().iloc[-1])
        e200 = float(series.ewm(span=200, adjust=False).mean().iloc[-1])
        price = float(series.iloc[-1])
        bias = 'BUY' if price > e50 > e200 else ('SELL' if price < e50 < e200 else 'WAIT')
        trends[tf] = {'direction': bias, 'close': price, 'ema50': e50, 'ema200': e200,
                      'bar_closed_at': last_end.isoformat()}
        closed[tf] = data
    result.evidence['trends'] = trends
    biases = {item['direction'] for item in trends.values()}
    if len(biases) != 1 or 'WAIT' in biases:
        result.reasons.append('M15/H1/H4 do not share the strict Close/EMA50/EMA200 chain')
        return result
    candidate = biases.pop()
    result.evidence['candidate_direction'] = candidate
    if direction is not None and direction != candidate:
        result.reasons.append(f'Proposed {direction} conflicts with {candidate} multi-timeframe bias')
        return result

    data = closed[timeframe]
    last, previous = data.iloc[-1], data.iloc[-2]
    tr = pd.concat([data.high - data.low, (data.high - data.close.shift()).abs(),
                    (data.low - data.close.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        result.reasons.append('Invalid M15 ATR')
        return result

    # Gold only accepts a reclaim after momentum is aligned on each permitted
    # timeframe and the completed M15 candle closes with displacement.
    if symbol == 'XAUUSD':
        lookback = GOLD_PROFILE['ema_slope_bars']
        m15_ema20 = data.close.ewm(span=20, adjust=False).mean()
        h1_ema50 = closed['H1'].close.ewm(span=50, adjust=False).mean()
        h4_ema50 = closed['H4'].close.ewm(span=50, adjust=False).mean()
        slopes = {
            'M15_EMA20': float(m15_ema20.iloc[-1] - m15_ema20.iloc[-1 - lookback]),
            'H1_EMA50': float(h1_ema50.iloc[-1] - h1_ema50.iloc[-1 - lookback]),
            'H4_EMA50': float(h4_ema50.iloc[-1] - h4_ema50.iloc[-1 - lookback]),
        }
        candle_range = float(last.high - last.low)
        body = abs(float(last.close - last.open))
        close_location = ((float(last.close - last.low) / candle_range) if candidate == 'BUY'
                          else (float(last.high - last.close) / candle_range)) if candle_range > 0 else 0.0
        result.evidence['gold_profile'] = {
            'name': 'GOLD_MOMENTUM_RECLAIM', 'atr': atr, 'body_atr': body / atr,
            'close_location': close_location, 'ema_slopes': slopes,
        }
        expected_sign = 1 if candidate == 'BUY' else -1
        if any(expected_sign * slope <= 0 for slope in slopes.values()):
            result.reasons.append('Gold requires aligned M15/H1/H4 EMA momentum slopes')
            return result
        if body < GOLD_PROFILE['min_body_atr'] * atr:
            result.reasons.append('Gold trigger body is below the required 0.50 ATR displacement')
            return result
        if close_location < GOLD_PROFILE['min_close_location']:
            result.reasons.append('Gold trigger did not close in the directional 30% of its range')
            return result
    ema20_before = float(data.close.ewm(span=20, adjust=False).mean().iloc[-2])
    swing_low = float(data.low.iloc[-6:-1].min())
    swing_high = float(data.high.iloc[-6:-1].max())
    if candidate == 'BUY':
        sweep = last.low < swing_low < last.close and last.close > last.open
        reclaim = (last.low <= ema20_before < last.close and last.close > last.open
                   and last.close > previous.close)
    else:
        sweep = last.high > swing_high > last.close and last.close < last.open
        reclaim = (last.high >= ema20_before > last.close and last.close < last.open
                   and last.close < previous.close)
    result.evidence['trigger'] = {'bar_opened_at': data.index[-1].isoformat(),
                                  'swing_low': swing_low, 'swing_high': swing_high,
                                  'ema20_before_trigger': ema20_before}
    if not (sweep or reclaim):
        result.reasons.append('No completed liquidity-sweep reclaim or EMA20 pullback reclaim')
        return result
    result.setup_type = 'LIQUIDITY_SWEEP_RECLAIM' if sweep else 'TREND_PULLBACK_RECLAIM'
    try:
        spread = float(spread)
        if not np.isfinite(spread) or spread < 0 or not np.isfinite(atr) or atr <= 0:
            raise ValueError('Invalid spread/ATR')
        price = float(last.close if entry is None else entry)
        buffer = max(spread, 0.1 * atr)
        invalidation = min(swing_low, float(last.low)) if candidate == 'BUY' else max(swing_high, float(last.high))
        structural_stop = invalidation - buffer if candidate == 'BUY' else invalidation + buffer
        sl = float(structural_stop if stop_loss is None else stop_loss)
        distance = abs(price - sl)
        target = float((price + 2 * distance if candidate == 'BUY' else price - 2 * distance)
                       if take_profit is None else take_profit)
        if not all(np.isfinite(value) and value > 0 for value in (price, sl, target)):
            raise ValueError('Non-finite/non-positive entry, SL or TP')
    except (TypeError, ValueError) as exc:
        result.reasons.append(str(exc))
        return result
    valid_geometry = sl < price < target if candidate == 'BUY' else target < price < sl
    outside_structure = sl < invalidation if candidate == 'BUY' else sl > invalidation
    if not valid_geometry or not outside_structure:
        result.reasons.append('SL/TP must have valid direction and SL must sit beyond structural invalidation')
        return result
    rr = abs(target - price) / distance
    result.evidence.update(atr=atr, structural_invalidation=invalidation, spread=spread)
    if rr + 1e-9 < MIN_RR:
        result.reasons.append(f'Target offers {rr:.3f}R; minimum is {MIN_RR:.1f}R')
        return result
    max_spread_fraction = (GOLD_PROFILE['max_spread_risk_fraction']
                           if symbol == 'XAUUSD' else 0.2)
    if spread > max_spread_fraction * distance:
        result.reasons.append(f'Spread exceeds {max_spread_fraction:.0%} of stop distance')
        return result
    result.allowed, result.direction = True, candidate
    result.entry, result.stop_loss, result.take_profit = price, sl, target
    result.risk_reward = rr
    return result
