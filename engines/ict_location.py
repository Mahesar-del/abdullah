"""Causal ICT/SMC location hypothesis for research, not an institutional claim.

Every label is operational rather than visual: pivots are confirmed only after
``PIVOT_BARS`` subsequently closed candles; a signal can therefore never use a
future swing, Fair Value Gap, or liquidity pool.  The module has no network,
database, or execution side effect.  Macro/news and correlated-market vetoes
remain separate point-in-time data requirements.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .institutional_setup import (
    ALLOWED_SYMBOLS, MIN_RR, TIMEFRAMES, TF_MINUTES, closed_candles,
    in_killzone, normalize_symbol,
)


STRATEGY_VERSION = 'ict-location-sweep-mss-fvg-v1'
PIVOT_BARS = 3
MIN_HISTORY = {'M15': 100, 'H1': 70, 'H4': 50}


@dataclass
class LocationDecision:
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


def _atr(frame: pd.DataFrame) -> float:
    tr = pd.concat([
        frame.high - frame.low,
        (frame.high - frame.close.shift()).abs(),
        (frame.low - frame.close.shift()).abs(),
    ], axis=1).max(axis=1)
    value = float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1])
    if not np.isfinite(value) or value <= 0:
        raise ValueError('Invalid ATR')
    return value


def _confirmed_pivots(frame: pd.DataFrame, width: int = PIVOT_BARS):
    """Return only pivots whose confirmation candles have already closed."""
    highs, lows = frame.high.to_numpy(dtype=float), frame.low.to_numpy(dtype=float)
    n = len(frame)
    if n <= 2 * width:
        return []
    # This is the vectorised equivalent of the explicit left/right comparison
    # below.  The frame is already the closed-only prefix at the decision
    # clock, so no value beyond that clock participates in a pivot.
    is_high = np.zeros(n, dtype=bool)
    is_low = np.zeros(n, dtype=bool)
    active = np.ones(n - 2 * width, dtype=bool)
    for distance in range(1, width + 1):
        center = slice(width, n - width)
        active &= highs[center] >= highs[width - distance:n - width - distance]
        active &= highs[center] > highs[width + distance:n - width + distance]
    is_high[width:n - width] = active
    active = np.ones(n - 2 * width, dtype=bool)
    for distance in range(1, width + 1):
        center = slice(width, n - width)
        active &= lows[center] <= lows[width - distance:n - width - distance]
        active &= lows[center] < lows[width + distance:n - width + distance]
    is_low[width:n - width] = active
    # Last ``width`` bars cannot be pivots yet: their right-side confirmation
    # is unavailable at this decision time.
    points = []
    for pos in np.flatnonzero(is_high | is_low):
        if is_high[pos]:
            points.append(('HIGH', int(pos), float(highs[pos])))
        if is_low[pos]:
            points.append(('LOW', int(pos), float(lows[pos])))
    return points


def _structure(frame: pd.DataFrame) -> Tuple[str, Dict]:
    pivots = _confirmed_pivots(frame)
    highs = [item for item in pivots if item[0] == 'HIGH']
    lows = [item for item in pivots if item[0] == 'LOW']
    evidence = {
        'confirmed_pivot_count': len(pivots),
        'last_highs': [round(item[2], 8) for item in highs[-2:]],
        'last_lows': [round(item[2], 8) for item in lows[-2:]],
    }
    if len(highs) < 2 or len(lows) < 2:
        return 'WAIT', evidence
    hh, hl = highs[-1][2] > highs[-2][2], lows[-1][2] > lows[-2][2]
    lh, ll = highs[-1][2] < highs[-2][2], lows[-1][2] < lows[-2][2]
    return ('BUY' if hh and hl else 'SELL' if lh and ll else 'WAIT'), evidence


def _latest_before(pivots, kind: str, before: int):
    candidates = [item for item in pivots if item[0] == kind and item[1] < before]
    return candidates[-1] if candidates else None


def _dealing_range(frame: pd.DataFrame):
    pivots = _confirmed_pivots(frame)
    highs = [item for item in pivots if item[0] == 'HIGH']
    lows = [item for item in pivots if item[0] == 'LOW']
    if not highs or not lows:
        return None
    high, low = highs[-1], lows[-1]
    if high[1] < low[1]:
        high = _latest_before(pivots, 'HIGH', len(frame))
    if low[1] < high[1]:
        low = _latest_before(pivots, 'LOW', len(frame))
    if high is None or low is None or high[2] <= low[2]:
        return None
    return float(low[2]), float(high[2])


def evaluate_ict_location(frames, symbol, *, as_of=None, spread=0.0) -> LocationDecision:
    """Require H4/H1 structure plus M15 sweep, MSS displacement and FVG.

    The output is a candidate to be entered only at the *next* executable M15
    open by a caller.  It deliberately refuses to manufacture a 2R target: an
    opposing confirmed H1 liquidity pool must already offer it.
    """
    result = LocationDecision(evidence={'strategy_version': STRATEGY_VERSION})
    symbol = normalize_symbol(symbol)
    stamp = pd.Timestamp(as_of if as_of is not None else datetime.now(timezone.utc))
    if stamp.tzinfo is None:
        result.reasons.append('as_of must include a timezone')
        return result
    stamp = stamp.tz_convert('UTC')
    result.evidence.update(symbol=symbol, checked_at=stamp.isoformat(),
                           pivot_confirmation_bars=PIVOT_BARS)
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
        closed = {tf: closed_candles(frames.get(tf), tf, stamp) for tf in TIMEFRAMES}
    except (TypeError, ValueError, KeyError) as exc:
        result.reasons.append(str(exc))
        return result
    for tf, data in closed.items():
        if len(data) < MIN_HISTORY[tf]:
            result.reasons.append(f'{tf}: only {len(data)} completed bars; need {MIN_HISTORY[tf]}')
            return result
        last_end = data.index[-1] + pd.Timedelta(minutes=TF_MINUTES[tf])
        if stamp - last_end > pd.Timedelta(minutes=TF_MINUTES[tf] * 1.5):
            result.reasons.append(f'{tf}: stale completed data')
            return result

    h4_bias, h4_evidence = _structure(closed['H4'])
    h1_bias, h1_evidence = _structure(closed['H1'])
    result.evidence['higher_timeframe_structure'] = {'H4': h4_evidence | {'bias': h4_bias},
                                                      'H1': h1_evidence | {'bias': h1_bias}}
    if h4_bias == 'WAIT' or h4_bias != h1_bias:
        result.reasons.append('H4 and H1 confirmed market structure are not aligned')
        return result
    direction = h4_bias

    h4_range = _dealing_range(closed['H4'])
    if h4_range is None:
        result.reasons.append('No confirmed H4 dealing range')
        return result
    range_low, range_high = h4_range
    equilibrium = (range_low + range_high) / 2
    m15 = closed['M15']
    last = m15.iloc[-1]
    entry = float(last.close)
    if direction == 'BUY' and entry > equilibrium:
        result.reasons.append('BUY is not in H4 discount')
        return result
    if direction == 'SELL' and entry < equilibrium:
        result.reasons.append('SELL is not in H4 premium')
        return result

    pivots = _confirmed_pivots(m15)
    atr = _atr(m15)
    buffer = max(spread, 0.1 * atr)

    # An ICT location is a sequence, not a label stamped on a single bar.
    # We scan only the last 16 completed M15 bars.  At every historical event
    # a pivot is eligible only after its own right-side confirmation had closed.
    sequence = None
    for sweep_pos in range(max(6, len(m15) - 16), len(m15) - 3):
        prior = [item for item in pivots if item[1] + PIVOT_BARS < sweep_pos]
        prior_highs = [item for item in prior if item[0] == 'HIGH']
        prior_lows = [item for item in prior if item[0] == 'LOW']
        if not prior_highs or not prior_lows:
            continue
        liquidity = prior_lows[-1] if direction == 'BUY' else prior_highs[-1]
        sweep_bar = m15.iloc[sweep_pos]
        swept = ((float(sweep_bar.low) < liquidity[2] and float(sweep_bar.close) > liquidity[2])
                 if direction == 'BUY' else
                 (float(sweep_bar.high) > liquidity[2] and float(sweep_bar.close) < liquidity[2]))
        if not swept:
            continue
        mss_level = prior_highs[-1] if direction == 'BUY' else prior_lows[-1]
        for mss_pos in range(sweep_pos + 1, len(m15) - 2):
            mss_bar = m15.iloc[mss_pos]
            displaced = abs(float(mss_bar.close - mss_bar.open)) >= 0.5 * atr
            shifted = (float(mss_bar.close) > mss_level[2] if direction == 'BUY'
                       else float(mss_bar.close) < mss_level[2])
            if not (shifted and displaced):
                continue
            for fvg_pos in range(mss_pos, len(m15) - 1):
                if direction == 'BUY':
                    lower, upper = float(m15.high.iloc[fvg_pos - 2]), float(m15.low.iloc[fvg_pos])
                    formed = upper > lower
                    retested = float(last.low) <= upper and float(last.close) >= (lower + upper) / 2
                else:
                    lower, upper = float(m15.high.iloc[fvg_pos]), float(m15.low.iloc[fvg_pos - 2])
                    formed = upper > lower
                    retested = float(last.high) >= lower and float(last.close) <= (lower + upper) / 2
                if formed and retested:
                    sequence = {
                        'sweep_pos': sweep_pos, 'mss_pos': mss_pos, 'fvg_pos': fvg_pos,
                        'liquidity': liquidity, 'mss_level': mss_level,
                        'fvg_low': lower, 'fvg_high': upper,
                        'displacement': displaced,
                    }
    if sequence is None:
        result.reasons.append('No completed sweep → displaced MSS → FVG → retest sequence')
        return result
    if direction == 'BUY':
        invalidation = min(float(m15.low.iloc[sequence['sweep_pos']]), sequence['liquidity'][2]) - buffer
        pools = [item for item in _confirmed_pivots(closed['H1']) if item[0] == 'HIGH' and item[2] > entry]
        risk_distance = entry - invalidation
        eligible_targets = [item for item in pools if item[2] - entry >= MIN_RR * risk_distance]
        target_pool = min(eligible_targets, key=lambda item: item[2]) if eligible_targets else None
    else:
        invalidation = max(float(m15.high.iloc[sequence['sweep_pos']]), sequence['liquidity'][2]) + buffer
        pools = [item for item in _confirmed_pivots(closed['H1']) if item[0] == 'LOW' and item[2] < entry]
        risk_distance = invalidation - entry
        eligible_targets = [item for item in pools if entry - item[2] >= MIN_RR * risk_distance]
        target_pool = max(eligible_targets, key=lambda item: item[2]) if eligible_targets else None
    result.evidence['m15_location'] = {
        'direction': direction, 'h4_range': {'low': range_low, 'high': range_high, 'equilibrium': equilibrium},
        'swept_liquidity': sequence['liquidity'][2], 'opposing_mss_level': sequence['mss_level'][2],
        'sweep_bar_opened_at': m15.index[sequence['sweep_pos']].isoformat(),
        'mss_bar_opened_at': m15.index[sequence['mss_pos']].isoformat(),
        'fvg_bar_opened_at': m15.index[sequence['fvg_pos']].isoformat(),
        'fvg': {'low': sequence['fvg_low'], 'high': sequence['fvg_high']}, 'atr': atr,
    }
    if target_pool is None:
        result.reasons.append('No confirmed opposing H1 liquidity target offering minimum 2R')
        return result
    target = float(target_pool[2])
    risk = (entry - invalidation) if direction == 'BUY' else (invalidation - entry)
    reward = (target - entry) if direction == 'BUY' else (entry - target)
    rr = reward / risk if risk > 0 else -1
    if risk <= 0 or reward <= 0 or rr + 1e-9 < MIN_RR:
        result.reasons.append('Confirmed opposing H1 liquidity does not offer minimum 2R')
        return result
    result.allowed, result.direction = True, direction
    result.entry, result.stop_loss, result.take_profit, result.risk_reward = entry, invalidation, target, rr
    result.setup_type = 'ICT_LOCATION_SWEEP_MSS_FVG'
    result.evidence['target_liquidity'] = target
    return result
