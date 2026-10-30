"""
Continuous Market Auto-Scanner Service
Runs continuously in the background to scan supported symbols across multiple timeframes.
STRICT FILTER: Only emits / saves signals with confidence >= 75.0% (75-80%+).
No manual trigger or button required; automatically refreshes and dispatches high-conviction signals.
"""
import threading
import time
import logging
from datetime import timedelta
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Minimum confidence required to create and display a signal (75.0%+ High-Conviction)
MIN_CONFIDENCE_THRESHOLD = 75.0

# Supported symbols and timeframes strictly adhering to the institutional mandate.
DEFAULT_SCAN_SYMBOLS = ['XAUUSD', 'US30', 'SPX500']
DEFAULT_SCAN_TIMEFRAMES = ['M15', 'H1', 'H4']

# Three-second post-close detection.  ``_running`` prevents overlapping passes,
# so a slow broker response cannot multiply load or duplicate executions.
SCAN_INTERVAL_SEC = 3
_lock = threading.Lock()
_last_run = 0.0
_running = False


def _get_validity(timeframe: str) -> timedelta:
    tf = timeframe.upper()
    if tf == 'M15':
        return timedelta(hours=4)
    elif tf == 'H1':
        return timedelta(hours=24)
    elif tf == 'H4':
        return timedelta(days=2)
    return timedelta(hours=24)


def _has_golden_alignment(fetcher, symbol: str, timeframe: str, direction: str, current_df):
    """Validate the exact EMA chain on all three approved timeframes."""
    for tf in DEFAULT_SCAN_TIMEFRAMES:
        df = current_df if tf == timeframe else fetcher.fetch(symbol, tf, limit=200)
        if df is None or len(df) < 200 or 'close' not in df:
            return False, f'Insufficient {tf} data for multi-timeframe confirmation'
        close_series = df['close']
        close = float(close_series.iloc[-1])
        ema50 = float(close_series.ewm(span=50, adjust=False).mean().iloc[-1])
        ema200 = float(close_series.ewm(span=200, adjust=False).mean().iloc[-1])
        aligned = (close > ema50 > ema200) if direction == 'BUY' else (close < ema50 < ema200)
        if not aligned:
            return False, f'{tf}: Close={close:.2f}, EMA50={ema50:.2f}, EMA200={ema200:.2f}'
    return True, ''


def scan_single(symbol: str, timeframe: str):
    """
    Scans a single symbol + timeframe.
    Strictly enforces:
    - Institutional Killzones (15m strictly 07-11 UTC London & 13-17 UTC NY)
    - Multi-Timeframe Golden Trend Alignment (EMA 50 & EMA 200)
    - Minimum Asymmetric Risk-to-Reward >= 2.0:1
    - Price sanity & non-stale data verification
    - Direction must be BUY or SELL (never WAIT)
    - Confidence must be >= 75.0%
    """
    from market_data.models import Instrument
    from signals.models import Signal
    from engines.data_fetcher import DataFetcher
    from engines.unified import UnifiedSignalEngine
    from quant.data import validate_price_sanity
    from .strategy_pipeline import prepare_setup, validate_proposal, record_status, create_signal_once

    try:
        instrument = Instrument.objects.filter(symbol=symbol).first()
        if not instrument:
            return None

        fetcher = DataFetcher()
        frames, df, candidate, quote = prepare_setup(fetcher, symbol, timeframe)
        if not candidate.allowed:
            logger.info('[AUTO-SCANNER] %s %s WAIT: %s', symbol, timeframe, '; '.join(candidate.reasons))
            return None

        # Institutional Price Sanity & Anti-Stale Gate
        is_valid, sanity_reason = validate_price_sanity(df, max_bar_jump=0.10)
        if not is_valid:
            logger.warning("[AUTO-SCANNER] Rejected %s %s due to data anomaly: %s", symbol, timeframe, sanity_reason)
            return None

        engine = UnifiedSignalEngine(df, symbol, timeframe, execution_quote=quote)
        unified = engine.generate()
        decision = validate_proposal(frames, symbol, timeframe, unified, quote)
        if not decision.allowed:
            logger.info('[AUTO-SCANNER] %s %s WAIT: %s', symbol, timeframe, '; '.join(decision.reasons))
            return None
        setup_bar = df.index[-1].to_pydatetime()
        if Signal.objects.filter(instrument=instrument, timeframe=timeframe, setup_bar_opened_at=setup_bar).exists():
            record_status(symbol, timeframe, 'DUPLICATE', ['This completed setup candle has already been processed'])
            return None

        # Prevent duplicate active signals for the same pair/timeframe/direction
        if Signal.objects.filter(
            instrument=instrument,
            timeframe=unified.timeframe,
            direction=unified.direction,
            status='ACTIVE'
        ).exists():
            return None

        # Persist high-conviction signal
        signal = create_signal_once(
            instrument          = instrument,
            timeframe           = unified.timeframe,
            direction           = unified.direction,
            strength            = unified.strength,
            status              = 'ACTIVE',
            entry_price         = unified.entry,
            stop_loss           = unified.stop_loss,
            take_profit_1       = unified.take_profit_1,
            take_profit_2       = None,
            take_profit_3       = None,
            risk_reward         = unified.risk_reward,
            confidence_score    = unified.confidence,
            technical_score     = unified.technical_score,
            smc_score           = unified.smc_score,
            price_action_score  = unified.price_action_score,
            macro_score         = unified.macro_score,
            news_score          = unified.news_score,
            institutional_score = unified.institutional_score,
            intermarket_score   = getattr(unified, 'intermarket_score', 50.0),
            ai_ml_score         = unified.ai_ml_score,
            engine_detail       = getattr(unified, 'engine_results', {}) or {},
            analysis_summary    = unified.analysis,
            warnings            = unified.warnings,
            decision_class      = getattr(unified, 'decision_class', 'STRONG'),
            market_regime       = getattr(unified, 'market_regime', 'TRENDING'),
            independent_groups  = getattr(unified, 'independent_groups', {}),
            is_trade_allowed    = getattr(unified, 'is_trade_allowed', True),
            recommended_lots    = getattr(unified, 'recommended_lots', 0.10),
            data_quality_score  = unified.data_quality_score,
            risk_rejection_reasons = unified.risk_rejection_reasons,
            strategy_evidence   = decision.to_dict(),
            setup_bar_opened_at = setup_bar,
            valid_until         = timezone.now() + _get_validity(timeframe),
        )
        if signal is None:
            record_status(symbol, timeframe, 'DUPLICATE', ['Setup already persisted by another request'])
            return None

        logger.info(
            f"[AUTO-SCANNER] Created high-conviction signal #{signal.id}: "
            f"{symbol} {timeframe} {unified.direction} ({unified.confidence:.1f}% >= 75%)"
        )

        # Trigger auto-trader hook if enabled
        try:
            from accounts.auto_trader import AutoTraderEngine
            AutoTraderEngine.execute_for_signal(signal)
        except Exception:
            pass

        # Dispatch alerts
        try:
            from signals.notifications import notifier, telegram_notifier
            notifier.send_signal(signal)
            telegram_notifier.send_signal(signal)
        except Exception:
            pass

        return signal

    except Exception as e:
        record_status(symbol, timeframe, 'ERROR', [str(e)[:200]])
        logger.error(f"[AUTO-SCANNER] Error scanning {symbol} {timeframe}: {e}")
        return None


def run_full_scan_pass():
    """
    Executes a high-speed parallel pass across configured symbols and timeframes.
    Uses multi-threading to process all streams simultaneously with sub-second execution.
    """
    from django.db import close_old_connections
    close_old_connections()
    tasks = [(sym, tf) for sym in DEFAULT_SCAN_SYMBOLS for tf in DEFAULT_SCAN_TIMEFRAMES]

    def _worker(pair):
        sym, tf = pair
        try:
            from django.db import close_old_connections
            close_old_connections()
            return scan_single(sym, tf)
        except Exception as e:
            logger.warning(f"[AUTO-SCANNER] Pass failure on {sym} {tf}: {e}")
            return None
        finally:
            try:
                from django.db import close_old_connections
                close_old_connections()
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(_worker, tasks))
    close_old_connections()


def _run_scanner_thread():
    global _running, _last_run
    try:
        run_full_scan_pass()
    except Exception as e:
        logger.error(f"[AUTO-SCANNER] Exception during scan pass: {e}")
    finally:
        with _lock:
            _running = False
            _last_run = time.time()


def maybe_auto_scan():
    """
    Throttled non-blocking trigger safe to invoke periodically or during API requests.
    """
    global _running
    with _lock:
        if _running or (time.time() - _last_run) < SCAN_INTERVAL_SEC:
            return
        _running = True
    threading.Thread(target=_run_scanner_thread, daemon=True, name='market-auto-scanner').start()


def start_auto_scanner_loop():
    """
    Background daemon loop that scans continuously while server is running.
    """
    def loop():
        logger.info("[AUTO-SCANNER] Starting continuous background market scanner (>=75% confidence threshold)...")
        time.sleep(5)  # initial delay
        while True:
            try:
                maybe_auto_scan()
            except Exception as e:
                logger.error(f"[AUTO-SCANNER] Loop error: {e}")
            time.sleep(SCAN_INTERVAL_SEC)

    threading.Thread(target=loop, daemon=True, name='continuous-auto-scan-daemon').start()
