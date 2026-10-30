"""Shared broker-data and entry gates for scanner and manual API generation."""
from datetime import datetime, timezone as utc_timezone, timedelta
import math
import pandas as pd

from django.core.cache import cache
from django.utils import timezone
from engines.institutional_setup import (
    ALLOWED_SYMBOLS, TIMEFRAMES, STRATEGY_VERSION, SetupDecision,
    closed_candles, evaluate_setup, in_killzone,
)


def record_status(symbol, timeframe, state, reasons=(), evidence=None, confidence=None):
    if confidence is not None and not math.isfinite(float(confidence)):
        confidence = None
    row = dict(symbol=symbol, timeframe=timeframe, state=state, reasons=list(reasons),
               checked_at=timezone.now().isoformat(), strategy_version=STRATEGY_VERSION,
               evidence=evidence or {}, confidence=confidence)
    cache.set(f'institutional-setup:{symbol}:{timeframe}', row, timeout=600)
    return row


def current_status():
    return [cache.get(f'institutional-setup:{symbol}:{tf}') or
            dict(symbol=symbol, timeframe=tf, state='NOT_CHECKED', reasons=['Awaiting scanner pass'])
            for symbol in ALLOWED_SYMBOLS for tf in TIMEFRAMES]


def _fresh_broker_quote(symbol, broker_symbol, now):
    """Persist only observed broker bid/ask, never an estimated two-pip spread."""
    from market_data.models import Instrument, MarketQuoteSpread
    import MetaTrader5 as mt5
    tick = mt5.symbol_info_tick(broker_symbol)
    if not tick:
        raise ValueError('Broker bid/ask quote unavailable')
    bid, ask = float(tick.bid), float(tick.ask)
    tick_at = datetime.fromtimestamp(float(tick.time), tz=utc_timezone.utc)
    if not all(math.isfinite(p) and p > 0 for p in (bid, ask)) or ask < bid:
        raise ValueError('Broker bid/ask is invalid')
    if now - tick_at > timedelta(minutes=2) or tick_at > now + timedelta(seconds=30):
        raise ValueError('Broker quote is stale or future dated')
    inst = Instrument.objects.get(symbol=symbol)
    last = MarketQuoteSpread.objects.filter(instrument=inst, provider='mt5_terminal').first()
    if last is None or last.timestamp < tick_at:
        MarketQuoteSpread.objects.create(instrument=inst, timestamp=tick_at, bid=bid, ask=ask,
                                         spread=ask - bid, provider='mt5_terminal', is_live=True)
    return {'bid': bid, 'ask': ask, 'spread': ask - bid, 'observed_at': tick_at.isoformat(),
            'provider': 'mt5_terminal', 'broker_symbol': broker_symbol}


def prepare_setup(fetcher, symbol, timeframe, as_of=None):
    now = as_of or timezone.now()
    if timeframe == 'M15' and not in_killzone(now):
        rejected = evaluate_setup({}, symbol, timeframe, as_of=now)
        record_status(symbol, timeframe, 'WAIT', rejected.reasons, rejected.evidence)
        return {}, None, rejected, None
    frames = {tf: fetcher.fetch(symbol, tf, limit=400) for tf in TIMEFRAMES}
    rejected = SetupDecision()
    if any(frame is None or frame.attrs.get('provider') != 'mt5' for frame in frames.values()):
        rejected.reasons = ['Actual broker candles required; proxy/futures or cached unknown-source data cannot authorize this setup']
        record_status(symbol, timeframe, 'DATA_UNAVAILABLE', rejected.reasons)
        return frames, None, rejected, None
    future = [tf for tf, frame in frames.items()
              if isinstance(frame.index, pd.DatetimeIndex) and frame.index.tz is not None
              and not frame.empty and frame.index[-1] > pd.Timestamp(now) + pd.Timedelta(seconds=30)]
    if future:
        rejected.reasons = [f'Broker clock anomaly: future-dated {", ".join(future)} candles; UTC history must be verified']
        record_status(symbol, timeframe, 'DATA_UNAVAILABLE', rejected.reasons)
        return frames, None, rejected, None
    candidate = evaluate_setup(frames, symbol, timeframe, as_of=now)
    if not candidate.allowed:
        record_status(symbol, timeframe, 'WAIT', candidate.reasons, candidate.evidence)
        return frames, None, candidate, None
    try:
        quote = _fresh_broker_quote(symbol, frames[timeframe].attrs['broker_symbol'], now)
    except Exception as exc:
        candidate.allowed, candidate.direction = False, 'WAIT'
        candidate.reasons = [f'Fresh broker quote required: {exc}']
        record_status(symbol, timeframe, 'DATA_UNAVAILABLE', candidate.reasons, candidate.evidence)
        return frames, None, candidate, None
    # Freeze completed history at the decision instant. A bar that was forming
    # when fetched must never become a "completed" bar merely because slower
    # confluence engines crossed its closing time.
    frames = {tf: closed_candles(frame, tf, now) for tf, frame in frames.items()}
    for frame in frames.values():
        frame.attrs['snapshot_as_of'] = now.isoformat()
    record_status(symbol, timeframe, 'CANDIDATE', ['Awaiting unified confluence/news/risk gates'], candidate.evidence)
    return frames, closed_candles(frames[timeframe], timeframe, now), candidate, quote


def validate_proposal(frames, symbol, timeframe, unified, quote, as_of=None):
    now = as_of or timezone.now()
    try:
        observed = datetime.fromisoformat(quote['observed_at'])
        fresh = observed.tzinfo is not None and timedelta(0) <= now - observed <= timedelta(minutes=2)
    except (KeyError, TypeError, ValueError):
        fresh = False
    snapshot = next((frame.attrs.get('snapshot_as_of') for frame in frames.values()
                     if frame is not None and frame.attrs.get('snapshot_as_of')), None)
    boundary_crossed = snapshot is not None and pd.Timestamp(now).floor('15min') > pd.Timestamp(snapshot).floor('15min')
    if boundary_crossed:
        result = SetupDecision(reasons=['A new M15 candle closed during analysis; refresh all timeframe evidence'])
    elif not fresh:
        result = SetupDecision(reasons=['Broker quote expired while the analysis was running'])
    elif unified.direction not in ('BUY', 'SELL') or not unified.is_trade_allowed:
        reasons = list(unified.risk_rejection_reasons or []) + list(unified.warnings or [])
        result = SetupDecision(reasons=reasons or ['Unified confluence did not approve this setup'])
    elif not math.isfinite(float(unified.confidence)) or float(unified.confidence) < 75:
        result = SetupDecision(reasons=[f'Confluence score {unified.confidence} below 75; score is not a calibrated win probability'])
    else:
        result = evaluate_setup(frames, symbol, timeframe, as_of=now,
                                direction=unified.direction, entry=unified.entry,
                                stop_loss=unified.stop_loss, take_profit=unified.take_profit_1,
                                spread=quote['spread'])
        result.evidence['execution_quote'] = quote
    record_status(symbol, timeframe, 'QUALIFIED' if result.allowed else 'WAIT', result.reasons,
                  result.evidence, confidence=float(unified.confidence))
    return result


def create_signal_once(**fields):
    """Handle the unique completed-candle key during scanner/API races."""
    from django.db import IntegrityError, transaction
    from .models import Signal
    try:
        with transaction.atomic():
            return Signal.objects.create(**fields)
    except IntegrityError:
        if Signal.objects.filter(instrument=fields['instrument'], timeframe=fields['timeframe'],
                                 setup_bar_opened_at=fields['setup_bar_opened_at']).exists():
            return None
        raise
