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
from django.db import close_old_connections

logger = logging.getLogger(__name__)

# Minimum confidence required to create and display a signal
MIN_CONFIDENCE_THRESHOLD = 75.0

# Supported symbols and timeframes for automatic continuous scanning:
# - M15: Intraday Scalps & Liquidity Sweeps
# - H1: Day Trading & London/NY Session Momentum
# - H4: Institutional Swing Setups
# - D1: Macro Trend & Positional Wave Trades
DEFAULT_SCAN_SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'BTCUSD', 'US30']
DEFAULT_SCAN_TIMEFRAMES = ['M15', 'H1', 'H4', 'D1']

SCAN_INTERVAL_SEC = 45  # Scan cycle interval
_lock = threading.Lock()
_last_run = 0.0
_running = False


def _get_validity(timeframe: str) -> timedelta:
    tf = timeframe.upper()
    if tf == 'M15':
        return timedelta(hours=4)
    elif tf == 'M30':
        return timedelta(hours=8)
    elif tf == 'H1':
        return timedelta(hours=24)
    elif tf == 'H4':
        return timedelta(days=2)
    elif tf == 'D1':
        return timedelta(days=7)
    return timedelta(hours=24)


def scan_single(symbol: str, timeframe: str):
    """
    Scans a single symbol + timeframe.
    Strictly enforces:
    - Multi-timeframe institutional alignment (M15, H1, H4, D1)
    - Price sanity & non-stale data verification
    - Direction must be BUY or SELL (never WAIT)
    - Confidence must be >= 75.0%
    """
    from market_data.models import Instrument
    from signals.models import Signal
    from engines.data_fetcher import DataFetcher
    from engines.unified import UnifiedSignalEngine
    from quant.data import validate_price_sanity

    try:
        instrument = Instrument.objects.filter(symbol=symbol).first()
        if not instrument:
            return None

        fetcher = DataFetcher()
        df = fetcher.fetch(symbol, timeframe, limit=120)
        if df is None or len(df) < 40:
            return None

        # Institutional Price Sanity & Anti-Stale Gate
        is_valid, sanity_reason = validate_price_sanity(df, max_bar_jump=0.10)
        if not is_valid:
            logger.warning("[AUTO-SCANNER] Rejected %s %s due to data anomaly: %s", symbol, timeframe, sanity_reason)
            return None

        engine = UnifiedSignalEngine(df, symbol, timeframe)
        unified = engine.generate()

        # Strict checks: BUY/SELL only, no WAIT, and confidence >= 75%
        if unified.direction not in ('BUY', 'SELL'):
            return None

        if not unified.is_trade_allowed:
            logger.info(
                "[AUTO-SCANNER] Rejected %s %s: deterministic risk gate denied the signal.",
                symbol, timeframe
            )
            return None

        if float(unified.confidence) < MIN_CONFIDENCE_THRESHOLD:
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
        signal = Signal.objects.create(
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
            valid_until         = timezone.now() + _get_validity(timeframe),
        )

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
        logger.error(f"[AUTO-SCANNER] Error scanning {symbol} {timeframe}: {e}")
        return None


def run_full_scan_pass():
    """
    Executes a pass across configured symbols and timeframes.
    Runs silently and safely in the background.
    """
    close_old_connections()
    for symbol in DEFAULT_SCAN_SYMBOLS:
        for tf in DEFAULT_SCAN_TIMEFRAMES:
            try:
                scan_single(symbol, tf)
                time.sleep(0.3)  # Gentle spacing to avoid rate limiting
            except Exception as e:
                logger.warning(f"[AUTO-SCANNER] Pass failure on {symbol} {tf}: {e}")
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
