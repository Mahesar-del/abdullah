import os
import sys

from django.apps import AppConfig


class SignalsConfig(AppConfig):
    name = 'signals'

    def ready(self):
        # Start the automatic TP/SL evaluator & scanner in the active server process
        # (supports both local runserver and 24/7 cloud servers like Gunicorn/Render).
        is_runserver = 'runserver' in sys.argv and (os.environ.get('RUN_MAIN') == 'true' or '--noreload' in sys.argv)
        is_cloud_wsgi = any(k in (sys.argv[0] if sys.argv else '').lower() for k in ('gunicorn', 'daphne', 'uvicorn')) or os.environ.get('RENDER') == 'true'
        if is_runserver or is_cloud_wsgi:
            from .auto_evaluator import start_background_loop
            start_background_loop()
            from .auto_scanner import start_auto_scanner_loop
            start_auto_scanner_loop()
            try:
                from accounts.auto_trader import AutoTraderEngine
                AutoTraderEngine.restart_recovery()
            except Exception:
                pass
