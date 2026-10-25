import os
import sys

from django.apps import AppConfig


class SignalsConfig(AppConfig):
    name = 'signals'

    def ready(self):
        # Start background workers cleanly without blocking app initialization
        is_runserver = 'runserver' in sys.argv and (os.environ.get('RUN_MAIN') == 'true' or '--noreload' in sys.argv)
        is_cloud_wsgi = any(k in (sys.argv[0] if sys.argv else '').lower() for k in ('gunicorn', 'daphne', 'uvicorn')) or os.environ.get('RENDER') == 'true'
        if is_runserver or is_cloud_wsgi:
            import threading
            import time

            def _deferred_startup():
                # Allow Django to complete initialization and connection pool setup
                time.sleep(2)
                try:
                    from accounts.auto_trader import AutoTraderEngine
                    AutoTraderEngine.restart_recovery()
                except Exception:
                    pass
                from .auto_evaluator import start_background_loop
                start_background_loop()
                from .auto_scanner import start_auto_scanner_loop
                start_auto_scanner_loop()

            threading.Thread(target=_deferred_startup, daemon=True, name='tradesense-startup-init').start()
