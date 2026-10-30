from django.test import TestCase
from unittest.mock import patch
from datetime import timedelta
from io import StringIO

import pandas as pd
from django.core.management import call_command
from django.utils import timezone

from rest_framework.test import APIRequestFactory

from market_data.models import Instrument
from .models import Signal, SignalPerformance
from .views import SignalStatsView


class SignalStatsConsistencyTests(TestCase):
    def test_totals_include_missing_r_and_legacy_status_with_separate_r_sample(self):
        instrument = Instrument.objects.get(symbol='XAUUSD')

        def make_signal(status):
            return Signal.objects.create(
                instrument=instrument, timeframe='H1', direction='BUY', strength='STRONG',
                status=status, entry_price=100, stop_loss=99, take_profit_1=102,
                risk_reward=2, confidence_score=80,
            )

        win = make_signal('HIT_TP')
        loss = make_signal('HIT_SL')
        make_signal('HIT_SL')  # Older closed signal without a recorded R result.
        missing_r = make_signal('HIT_TP')
        legacy_loss = make_signal('STOP_LOSS_HIT')
        make_signal('ACTIVE')
        make_signal('EXPIRED')
        make_signal('BREAKEVEN')
        SignalPerformance.objects.create(signal=win, outcome='WIN', pnl_r=2)
        SignalPerformance.objects.create(signal=loss, outcome='LOSS', pnl_r=-1, loss_category='NEWS_SHOCK')
        SignalPerformance.objects.create(signal=missing_r, outcome='WIN', pnl_r=None)
        SignalPerformance.objects.create(signal=legacy_loss, outcome='LOSS', pnl_r=-1)

        with patch('signals.auto_evaluator.maybe_evaluate'):
            response = SignalStatsView.as_view()(APIRequestFactory().get('/api/signals/stats/'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['sample_size_trades'], 3)
        self.assertEqual(response.data['performance_wins'], 1)
        self.assertEqual(response.data['performance_losses'], 2)
        self.assertEqual(response.data['win_rate_percent'], 40.0)
        self.assertEqual(response.data['performance_win_rate_percent'], 33.3)
        self.assertEqual(response.data['take_profit_hits'], 2)
        self.assertEqual(response.data['stop_loss_hits'], 3)
        self.assertEqual(response.data['breakeven_signals'], 1)
        self.assertEqual(response.data['expired_signals'], 1)
        self.assertEqual(response.data['active_signals'], 1)
        self.assertEqual(response.data['missing_performance_signals'], 4)
        self.assertEqual(response.data['total_signals'], 8)
        self.assertEqual(response.data['loss_breakdown'], {'NEWS_SHOCK': 1, 'UNKNOWN': 1})

    def test_confidence_is_not_shown_as_a_win_rate_when_no_results_exist(self):
        with patch('signals.auto_evaluator.maybe_evaluate'):
            response = SignalStatsView.as_view()(APIRequestFactory().get('/api/signals/stats/'))
        self.assertIsNone(response.data['win_rate_percent'])
        self.assertEqual(response.data['win_rate_source'], 'no_closed_signals')


class SignalResolutionPersistenceTests(TestCase):
    def setUp(self):
        self.signal = Signal.objects.create(
            instrument=Instrument.objects.get(symbol='XAUUSD'), timeframe='H1',
            direction='BUY', strength='STRONG', status='ACTIVE',
            entry_price=100, stop_loss=90, take_profit_1=120,
            risk_reward=2, confidence_score=80,
        )
        Signal.objects.filter(pk=self.signal.pk).update(generated_at=timezone.now() - timedelta(minutes=5))
        self.candles = pd.DataFrame(
            [{'open': 115, 'high': 122, 'low': 115, 'close': 121, 'volume': 1}],
            index=pd.DatetimeIndex([timezone.now() - timedelta(minutes=1)]),
        )

    def evaluate(self):
        with (
            patch('signals.management.commands.evaluate_signals.DataFetcher.fetch', return_value=self.candles),
            patch('accounts.auto_trader.AutoTraderEngine.evaluate_and_close_open_trades', return_value=[]),
            patch('accounts.auto_trader.AutoTraderEngine.close_open_trades_for_signal'),
            patch('signals.notifications.telegram_notifier.send_signal_outcome'),
            patch('engines.learning.ContinuousLearningEngine.on_trade_resolved'),
        ):
            call_command('evaluate_signals', stdout=StringIO())

    def test_resolution_saves_status_exit_timestamp_and_r_once(self):
        self.evaluate()
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.status, 'HIT_TP')
        self.assertIsNotNone(self.signal.closed_at)
        performance = SignalPerformance.objects.get(signal=self.signal)
        self.assertEqual(performance.outcome, 'WIN')
        self.assertGreater(performance.pnl_r, 0)
        self.assertIsNotNone(performance.actual_exit)
        self.evaluate()
        self.assertEqual(SignalPerformance.objects.filter(signal=self.signal).count(), 1)

    def test_failed_performance_save_keeps_signal_active_for_retry(self):
        with patch('signals.management.commands.evaluate_signals.SignalPerformance.objects.update_or_create', side_effect=RuntimeError('write failed')):
            self.evaluate()
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.status, 'ACTIVE')
        self.assertIsNone(self.signal.closed_at)
        self.assertFalse(SignalPerformance.objects.filter(signal=self.signal).exists())
