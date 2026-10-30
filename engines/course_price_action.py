"""Causal implementation of the course's 4H / 1H / 15m / 5m price-action plan.

A decision is made only after the M5 confirmation candle has closed and is
executable at the next M5 open.  No forming higher-timeframe candle is read.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np
import pandas as pd

from .ict_location import _atr, _confirmed_pivots, _structure
from .institutional_setup import (
    ALLOWED_SYMBOLS, MIN_RR, TF_MINUTES, closed_candles,
    in_killzone, normalize_symbol,
)


STRATEGY_VERSION = 'course-price-action-4h-1h-15m-v1'
COURSE_TIMEFRAMES = ('M5', 'M15', 'H1', 'H4')
MIN_HISTORY = {'M5': 100, 'M15': 100, 'H1': 120, 'H4': 50}
ZONE_TOUCH_ATR = 0.35
ZONE_PADDING_ATR = 0.10
RVOL_LOOKBACK = 20
# The lesson asks for participation confirmation, not an arbitrary 1.20x
# threshold.  At-or-above its recent median keeps volume relevant without
# discarding valid course setups solely because participation is normal.
MIN_RVOL = 1.00
PROFILE_H1_BARS = 24
PROFILE_BINS = 24


def is_course_confirmation_clock(as_of) -> bool:
    """Only the first M5 close after a completed M15 setup can qualify.

    The course's M5 leg is a confirmation, not a second independent setup;
    evaluating later candles repeats identical H4/H1/M15 work without adding
    information.
    """
    stamp = pd.Timestamp(as_of).tz_convert('UTC')
    return stamp.minute % 15 == 5


@dataclass
class CourseDecision:
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


def _course_pattern(m15: pd.DataFrame, direction: str):
    """Return a completed course pattern.  Never reads a forming candle."""
    first, middle, last = m15.iloc[-3], m15.iloc[-2], m15.iloc[-1]
    prior = middle
    body = abs(float(last.close - last.open))
    candle_range = float(last.high - last.low)
    if candle_range <= 0:
        return None
    if direction == 'BUY':
        engulfing = (prior.close < prior.open and last.close > last.open and
                     last.open <= prior.close and last.close >= prior.open)
        morning_star = (first.close < first.open and
                        abs(float(middle.close - middle.open)) <= 0.5 * abs(float(first.close - first.open)) and
                        last.close > last.open and body >= abs(float(first.close - first.open)) and
                        last.close > first.high)
        lower_wick = min(float(last.open), float(last.close)) - float(last.low)
        upper_wick = float(last.high) - max(float(last.open), float(last.close))
        hammer = last.close > last.open and lower_wick >= 2 * body and upper_wick <= body
        if morning_star:
            return 'MORNING_STAR'
        if engulfing:
            return 'BULLISH_ENGULFING'
        if hammer:
            return 'BULLISH_HAMMER'
    else:
        engulfing = (prior.close > prior.open and last.close < last.open and
                     last.open >= prior.close and last.close <= prior.open)
        evening_star = (first.close > first.open and
                        abs(float(middle.close - middle.open)) <= 0.5 * abs(float(first.close - first.open)) and
                        last.close < last.open and body >= abs(float(first.close - first.open)) and
                        last.close < first.low)
        upper_wick = float(last.high) - max(float(last.open), float(last.close))
        lower_wick = min(float(last.open), float(last.close)) - float(last.low)
        shooting_star = last.close < last.open and upper_wick >= 2 * body and lower_wick <= body
        if evening_star:
            return 'EVENING_STAR'
        if engulfing:
            return 'BEARISH_ENGULFING'
        if shooting_star:
            return 'BEARISH_SHOOTING_STAR'
    return None


def _strong_h1_zone(h1: pd.DataFrame, direction: str, reference: float):
    """Find a causal H1 zone with at least three confirmed same-side reactions."""
    atr = _atr(h1)
    kind = 'LOW' if direction == 'BUY' else 'HIGH'
    points = [item for item in _confirmed_pivots(h1) if item[0] == kind]
    tolerance = ZONE_TOUCH_ATR * atr
    candidates = []
    for _, _, anchor in points:
        cluster = [item for item in points if abs(item[2] - anchor) <= tolerance]
        if len(cluster) < 3:
            continue
        prices = [item[2] for item in cluster]
        lower, upper = min(prices) - tolerance, max(prices) + tolerance
        # A support must not be materially above price and a resistance must
        # not be materially below it; this keeps the next opposing level as TP.
        if direction == 'BUY' and lower > reference + tolerance:
            continue
        if direction == 'SELL' and upper < reference - tolerance:
            continue
        distance = min(abs(reference - lower), abs(reference - upper))
        candidates.append((distance, lower, upper, cluster, atr))
    if not candidates:
        return None
    _, lower, upper, cluster, atr = min(candidates, key=lambda item: item[0])
    return {'lower': float(lower), 'upper': float(upper), 'touches': len(cluster), 'atr': atr,
            'pivot_prices': [float(item[2]) for item in cluster]}


def _volume(frame: pd.DataFrame):
    for name in ('volume', 'tick_volume'):
        if name in frame:
            values = pd.to_numeric(frame[name], errors='coerce').astype(float)
            if np.isfinite(values.to_numpy()).all() and (values >= 0).all():
                return values, name
    return None, None


def _relative_volume(frame: pd.DataFrame):
    values, field = _volume(frame)
    if values is None or len(values) <= RVOL_LOOKBACK:
        return None
    baseline = float(values.iloc[-1 - RVOL_LOOKBACK:-1].median())
    if baseline <= 0:
        return None
    return {'field': field, 'current': float(values.iloc[-1]), 'baseline_median': baseline,
            'rvol': float(values.iloc[-1] / baseline)}


def _fixed_h1_profile(h1: pd.DataFrame):
    """A fixed, causal 24-H1-bar volume-at-price proxy, never a visible range."""
    values, field = _volume(h1)
    if values is None or len(h1) < PROFILE_H1_BARS:
        return None
    sample = h1.iloc[-PROFILE_H1_BARS:]
    weights = values.iloc[-PROFILE_H1_BARS:].to_numpy(dtype=float)
    prices = ((sample.high + sample.low + sample.close) / 3.0).to_numpy(dtype=float)
    if weights.sum() <= 0 or not np.isfinite(prices).all():
        return None
    lower, upper = float(sample.low.min()), float(sample.high.max())
    if upper <= lower:
        return None
    counts, edges = np.histogram(prices, bins=PROFILE_BINS, range=(lower, upper), weights=weights)
    index = int(np.argmax(counts))
    poc_low, poc_high = float(edges[index]), float(edges[index + 1])
    return {'method': 'fixed_24_H1_bar_typical_price_volume_proxy', 'volume_field': field,
            'poc_low': poc_low, 'poc_high': poc_high, 'poc': (poc_low + poc_high) / 2.0,
            'bin_width': poc_high - poc_low, 'window_bars': PROFILE_H1_BARS}


def evaluate_course_price_action(frames, symbol, *, as_of=None, spread=0.0) -> CourseDecision:
    """4H direction → 1H zone → M15 setup → M5 closed confirmation/entry."""
    result = CourseDecision(evidence={'strategy_version': STRATEGY_VERSION})
    symbol = normalize_symbol(symbol)
    stamp = pd.Timestamp(as_of if as_of is not None else datetime.now(timezone.utc))
    if stamp.tzinfo is None:
        result.reasons.append('as_of must include a timezone')
        return result
    stamp = stamp.tz_convert('UTC')
    result.evidence.update(symbol=symbol, checked_at=stamp.isoformat(), hierarchy={
        'H4': 'direction_and_structure', 'H1': 'three_or_more_touch_support_resistance_zone',
        'M15': 'closed_reversal_setup_and_breakout_level', 'M5': 'closed_confirmation_candle_entry',
    })
    if symbol not in ALLOWED_SYMBOLS:
        result.reasons.append('Outside approved assets')
        return result
    if not in_killzone(stamp):
        result.reasons.append('Outside M15 London/NY killzones')
        return result
    try:
        spread = float(spread)
        if not np.isfinite(spread) or spread < 0:
            raise ValueError('Invalid spread')
        closed = {tf: closed_candles(frames.get(tf), tf, stamp) for tf in COURSE_TIMEFRAMES}
    except (TypeError, ValueError, KeyError) as exc:
        result.reasons.append(str(exc))
        return result
    for tf, data in closed.items():
        if len(data) < MIN_HISTORY[tf]:
            result.reasons.append(f'{tf}: only {len(data)} completed bars; need {MIN_HISTORY[tf]}')
            return result
        if stamp - (data.index[-1] + pd.Timedelta(minutes=TF_MINUTES[tf])) > pd.Timedelta(minutes=TF_MINUTES[tf] * 1.5):
            result.reasons.append(f'{tf}: stale completed data')
            return result

    direction, h4_evidence = _structure(closed['H4'])
    result.evidence['H4'] = h4_evidence | {'direction': direction}
    if direction == 'WAIT':
        result.reasons.append('H4 direction/structure is not confirmed')
        return result

    m15, m5, h1 = closed['M15'], closed['M5'], closed['H1']
    m15_last = m15.iloc[-1]
    zone = _strong_h1_zone(h1, direction, float(m15_last.close))
    if zone is None:
        result.reasons.append('No causal H1 support/resistance zone with at least three confirmed reactions')
        return result
    touched = float(m15_last.low) <= zone['upper'] and float(m15_last.high) >= zone['lower']
    result.evidence['H1_zone'] = zone | {'touched_by_last_M15': touched}
    if not touched:
        result.reasons.append('Latest M15 candle has not returned to the H1 zone')
        return result
    profile = _fixed_h1_profile(h1)
    if profile is None:
        result.reasons.append('Usable H1 volume is required for the fixed-range profile context')
        return result
    profile_near_zone = profile['poc_low'] <= zone['upper'] and profile['poc_high'] >= zone['lower']
    result.evidence['H1_volume_profile'] = profile | {'poc_overlaps_h1_zone': profile_near_zone}

    m15_pattern = _course_pattern(m15, direction)
    if m15_pattern is None:
        result.reasons.append('No completed M15 course reversal candle at the H1 zone')
        return result
    m15_rvol = _relative_volume(m15)
    if m15_rvol is None:
        result.reasons.append('Usable M15 volume is required for the course confirmation')
        return result
    m15_body = abs(float(m15_last.close - m15_last.open))
    m15_range = float(m15_last.high - m15_last.low)
    m15_rvol['body_to_range'] = m15_body / m15_range if m15_range > 0 else None
    m15_rvol['absorption_style'] = bool(m15_rvol['body_to_range'] is not None and m15_rvol['body_to_range'] <= 0.55)
    result.evidence['M15_volume_confirmation'] = m15_rvol
    if m15_rvol['rvol'] < MIN_RVOL:
        result.reasons.append(f'M15 relative volume {m15_rvol["rvol"]:.2f}x is below the required {MIN_RVOL:.2f}x')
        return result
    m15_closed_at = m15.index[-1] + pd.Timedelta(minutes=TF_MINUTES['M15'])
    m5_closed_at = m5.index[-1] + pd.Timedelta(minutes=TF_MINUTES['M5'])
    if m5_closed_at <= m15_closed_at:
        result.reasons.append('Awaiting a post-M15 M5 confirmation candle')
        return result
    m5_pattern = _course_pattern(m5, direction)
    if m5_pattern is None:
        result.reasons.append('No completed M5 course confirmation candle')
        return result
    m5_last = m5.iloc[-1]
    # The 5m leg confirms its own local change in control.  Requiring it to
    # clear the whole 15m reversal candle was an extra rule, not the course
    # method, and removed otherwise valid 5m confirmation entries.
    m5_previous = m5.iloc[-2]
    confirmed_breakout = (float(m5_last.close) > float(m5_previous.high) if direction == 'BUY'
                           else float(m5_last.close) < float(m5_previous.low))
    if not confirmed_breakout:
        result.reasons.append('M5 confirmation has not closed beyond its local prior candle')
        return result
    reference = float(m5_last.close)
    atr = _atr(m15)
    buffer = max(spread, ZONE_PADDING_ATR * atr)
    invalidation = (min(float(m15_last.low), float(m5_last.low), zone['lower']) - buffer if direction == 'BUY'
                    else max(float(m15_last.high), float(m5_last.high), zone['upper']) + buffer)
    risk = reference - invalidation if direction == 'BUY' else invalidation - reference
    opposing_kind = 'HIGH' if direction == 'BUY' else 'LOW'
    pools = [item[2] for item in _confirmed_pivots(h1) if item[0] == opposing_kind]
    eligible = ([price for price in pools if price - reference >= MIN_RR * risk] if direction == 'BUY'
                else [price for price in pools if reference - price >= MIN_RR * risk])
    target = min(eligible) if direction == 'BUY' and eligible else (max(eligible) if eligible else None)
    if target is None:
        result.reasons.append('No confirmed opposing H1 support/resistance target offering minimum 2R')
        return result
    reward = target - reference if direction == 'BUY' else reference - target
    rr = reward / risk if risk > 0 else -1
    if risk <= 0 or rr + 1e-9 < MIN_RR:
        result.reasons.append('Invalid course entry geometry')
        return result
    result.allowed, result.direction = True, direction
    result.entry, result.stop_loss, result.take_profit, result.risk_reward = reference, invalidation, float(target), rr
    result.setup_type = f'COURSE_{m15_pattern}_{m5_pattern}_H1_{"SUPPORT" if direction == "BUY" else "RESISTANCE"}'
    result.evidence['M15_setup'] = {'pattern': m15_pattern, 'closed_at': m15_closed_at.isoformat(), 'atr': atr}
    result.evidence['M5_entry'] = {'pattern': m5_pattern, 'signal_closed_at': m5_closed_at.isoformat(),
                                   'confirmed_breakout': True, 'entry_on': 'next_observed_M5_open'}
    result.evidence['H1_target'] = float(target)
    return result
