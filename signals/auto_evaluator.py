"""
Automatic TP/SL evaluation.
Closes signals and auto-trades once their Take Profit / Stop Loss is reached,
without anyone having to run `python manage.py evaluate_signals` by hand.
"""
import threading
import time
import logging

logger = logging.getLogger(__name__)

EVAL_INTERVAL_SEC = 60
_lock = threading.Lock()
_last_run = 0.0
_running = False


def _run_once():
    global _running, _last_run
    try:
        from django.core.management import call_command
        from django.db import close_old_connections
        call_command('evaluate_signals', verbosity=0)
    except Exception as e:  # never break the server because of evaluation
        logger.warning("Auto evaluation failed: %s", e)
    finally:
        try:
            from django.db import connection
            connection.close()
        except Exception:
            pass
        with _lock:
            _running = False
            _last_run = time.time()


def maybe_evaluate():
    """Throttled, non-blocking trigger (safe to call on every API request)."""
    global _running
    with _lock:
        if _running or (time.time() - _last_run) < EVAL_INTERVAL_SEC:
            return
        _running = True
    threading.Thread(target=_run_once, daemon=True, name='tp-sl-evaluator').start()


def start_background_loop():
    """Evaluate every EVAL_INTERVAL_SEC even when no browser is open."""
    def loop():
        time.sleep(10)
        while True:
            maybe_evaluate()
            time.sleep(EVAL_INTERVAL_SEC)
    threading.Thread(target=loop, daemon=True, name='tp-sl-loop').start()
