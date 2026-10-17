import os
import sys

from django.apps import AppConfig


class SignalsConfig(AppConfig):
    name = 'signals'

    def ready(self):
        # Start the automatic TP/SL evaluator only in the actual runserver process
        # (not in the autoreload parent, migrations, shell, tests...).
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') == 'true':
            from .auto_evaluator import start_background_loop
            start_background_loop()
            from .auto_scanner import start_auto_scanner_loop
            start_auto_scanner_loop()
            try:
                from accounts.auto_trader import AutoTraderEngine
                AutoTraderEngine.restart_recovery()
            except Exception:
                pass
