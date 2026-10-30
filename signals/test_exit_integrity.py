from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

import pandas as pd
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from market_data.models import Instrument
from signals.exit_rules import evaluate_signal_exit
from signals.models import Signal, SignalPerformance


class CausalExitRulesTests(SimpleTestCase):
    def setUp(self):
        self.entry_time = datetime(2026, 10, 28, 12, 0, tzinfo=dt_timezone.utc)

    def candles(self, rows):
        return pd.DataFrame(
            [dict(zip(('open', 'high', 'low', 'close'), prices)) for _, prices in rows],
            index=pd.DatetimeIndex([self.entry_time + timedelta(minutes=minute) for minute, _ in rows]),
        )

    def evaluate(self, frame, **kwargs):
        args = dict(
            direction='BUY', entry=100.0, stop_loss=90.0, take_profit=120.0,
            generated_at=self.entry_time, now=self.entry_time + timedelta(minutes=5),
        )
        args.update(kwargs)
        return evaluate_signal_exit(frame, **args)

    def test_existing_stop_wins_ambiguous_buy_target_stop_candle(self):
        result = self.evaluate(self.candles([(1, (100, 125, 85, 105))]))
        self.assertEqual(result.outcome, 'HIT_SL')
        self.assertEqual(result.exit_price, 90.0)

    def test_existing_stop_wins_ambiguous_sell_target_stop_candle(self):
        result = self.evaluate(
            self.candles([(1, (100, 115, 75, 95))]),
            direction='SELL', stop_loss=110.0, take_profit=80.0,
        )
        self.assertEqual(result.outcome, 'HIT_SL')
        self.assertEqual(result.exit_price, 110.0)

    def test_breakeven_does_not_retroactively_use_trigger_candle_low(self):
        result = self.evaluate(
            self.candles([(1, (105, 112, 95, 108))]),
            now=self.entry_time + timedelta(minutes=2, seconds=5),
        )
        self.assertIsNone(result.outcome)
        self.assertTrue(result.state['be_active'])
        self.assertEqual(result.state['initial_risk'], 10.0)
        self.assertEqual(result.state['initial_stop'], 90.0)
        self.assertEqual(result.state['current_sl'], 100.0)

    def test_breakeven_survives_a_later_window_and_keeps_original_risk(self):
        first = self.evaluate(self.candles([(1, (105, 112, 105, 108))]))
        later = self.evaluate(
            self.candles([(300, (104, 105, 99, 101))]),
            now=self.entry_time + timedelta(minutes=301, seconds=5), prior_state=first.state,
        )
        self.assertEqual(later.outcome, 'BREAKEVEN')
        self.assertEqual(later.state['initial_risk'], 10.0)
        self.assertEqual(later.exit_price, 100.0)

    def test_unfinished_candle_extremes_do_not_close_a_signal(self):
        result = self.evaluate(
            self.candles([(1, (100, 125, 85, 105))]),
            now=self.entry_time + timedelta(minutes=1, seconds=30),
        )
        self.assertIsNone(result.outcome)
        self.assertFalse(result.state['be_active'])

    def test_protected_stop_gap_is_not_reported_as_zero_loss(self):
        first = self.evaluate(self.candles([(1, (105, 112, 105, 108))]))
        later = self.evaluate(
            self.candles([(300, (95, 98, 92, 96))]),
            now=self.entry_time + timedelta(minutes=301), prior_state=first.state,
        )
        self.assertEqual(later.outcome, 'HIT_SL')
        self.assertEqual(later.exit_price, 95.0)

    def test_pre_entry_close_cannot_be_treated_as_a_live_tick(self):
        result = self.evaluate(
            self.candles([(0, (100, 130, 95, 130))]),
            generated_at=self.entry_time + timedelta(seconds=10),
            now=self.entry_time + timedelta(minutes=1, seconds=10),
        )
        self.assertIsNone(result.outcome)

    def test_live_breakeven_does_not_replay_an_earlier_low_when_bar_completes(self):
        first = self.evaluate(
            self.candles([(1, (105, 112, 95, 111))]),
            now=self.entry_time + timedelta(minutes=1, seconds=30),
        )
        self.assertTrue(first.state['be_active'])
        later = self.evaluate(
            self.candles([(1, (105, 112, 95, 108))]),
            now=self.entry_time + timedelta(minutes=2, seconds=10), prior_state=first.state,
        )
        self.assertIsNone(later.outcome)

    def test_entry_costs_are_frozen_between_evaluations(self):
        first = self.evaluate(
            self.candles([(1, (103, 105, 100, 104))]), half_spread=0.2, slippage=0.1, commission=0.05,
        )
        later = self.evaluate(
            self.candles([(2, (104, 106, 102, 105))]), prior_state=first.state,
            half_spread=3.0, slippage=2.0, commission=1.0,
        )
        self.assertAlmostEqual(later.state['fill_entry'], 100.3)
        self.assertAlmostEqual(later.state['initial_risk'], 10.3)
        self.assertEqual(later.state['commission'], 0.05)

    def test_mt5_bid_bar_spread_is_applied_once_to_entry(self):
        result = self.evaluate(
            self.candles([(1, (103, 105, 102, 104))]), half_spread=0.5, price_basis='bid',
        )
        self.assertEqual(result.state['fill_entry'], 101.0)
        self.assertEqual(result.state['initial_risk'], 11.0)

    def test_executable_entry_is_not_charged_spread_or_entry_slippage_again(self):
        result = self.evaluate(
            self.candles([(1, (103, 105, 102, 104))]), entry=101.0,
            half_spread=0.5, slippage=0.2, price_basis='bid', entry_is_executable=True,
        )
        self.assertEqual(result.state['fill_entry'], 101.0)
        self.assertEqual(result.state['initial_risk'], 11.0)
        self.assertEqual(result.state['cost_basis'], 'PAPER_QUOTE_REFERENCE_ENTRY__EXIT_COSTS_MODELED')

    def test_bid_based_breakeven_uses_full_spread(self):
        result = self.evaluate(
            self.candles([(1, (110, 113, 108, 112))]), entry=101.0,
            take_profit=130.0, half_spread=0.5, price_basis='bid', entry_is_executable=True,
        )
        self.assertIsNone(result.outcome)
        self.assertTrue(result.state['be_active'])
        self.assertEqual(result.state['current_sl'], 102.0)

    def test_legacy_window_coverage_is_not_claimed_complete(self):
        result = self.evaluate(self.candles([(100, (103, 105, 102, 104))]))
        # Future rows cannot initialize a supposedly observed trade path.
        self.assertEqual(result.state, {})
        result = self.evaluate(
            self.candles([(100, (103, 105, 102, 104))]),
            now=self.entry_time + timedelta(minutes=101),
        )
        self.assertEqual(result.state['history_coverage'], 'PARTIAL')

    def test_post_expiry_target_is_not_awarded_as_a_win(self):
        result = self.evaluate(
            self.candles([(4, (125, 130, 124, 128))]),
            valid_until=self.entry_time + timedelta(minutes=3),
        )
        self.assertEqual(result.outcome, 'EXPIRED')
        self.assertIn('not a reconstructed', result.note)

    def test_zero_risk_does_not_get_an_invented_fallback_risk(self):
        result = self.evaluate(self.candles([(1, (100, 105, 99, 103))]), stop_loss=100.0)
        self.assertIsNone(result.outcome)
        self.assertEqual(result.state, {})


class DurableExitStateTests(TestCase):
    def setUp(self):
        self.entry_time = datetime(2026, 10, 28, 12, 0, tzinfo=dt_timezone.utc)
        self.signal = Signal.objects.create(
            instrument=Instrument.objects.get(symbol='XAUUSD'), timeframe='H1',
            direction='BUY', strength='STRONG', status='ACTIVE',
            entry_price=100, stop_loss=90, take_profit_1=125,
            risk_reward=2.5, confidence_score=80,
        )
        Signal.objects.filter(pk=self.signal.pk).update(generated_at=self.entry_time)

    def evaluate(self, frame, now):
        with (
            patch('signals.management.commands.evaluate_signals.DataFetcher.fetch', return_value=frame),
            patch('signals.management.commands.evaluate_signals.timezone.now', return_value=now),
            patch('accounts.auto_trader.AutoTraderEngine.evaluate_and_close_open_trades', return_value=[]),
            patch('accounts.auto_trader.AutoTraderEngine.close_open_trades_for_signal'),
            patch('signals.notifications.telegram_notifier.send_signal_outcome'),
            patch('engines.learning.ContinuousLearningEngine.on_trade_resolved'),
        ):
            call_command('evaluate_signals', stdout=StringIO())

    def test_breakeven_state_persists_without_overwriting_original_stop(self):
        frame = pd.DataFrame(
            [{'open': 107, 'high': 113, 'low': 105, 'close': 112}],
            index=pd.DatetimeIndex([self.entry_time + timedelta(minutes=1)]),
        )
        self.evaluate(frame, self.entry_time + timedelta(minutes=2, seconds=5))
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.status, 'ACTIVE')
        self.assertTrue(self.signal.exit_state['be_active'])
        frozen_risk = self.signal.exit_state['initial_risk']
        self.assertEqual(float(self.signal.stop_loss), 90.0)

        next_frame = pd.DataFrame(
            [{'open': 104, 'high': 105, 'low': 99, 'close': 101}],
            index=pd.DatetimeIndex([self.entry_time + timedelta(minutes=300)]),
        )
        self.evaluate(next_frame, self.entry_time + timedelta(minutes=301, seconds=5))
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.status, 'BREAKEVEN')
        self.assertEqual(self.signal.exit_state['initial_risk'], frozen_risk)
        self.assertEqual(float(self.signal.stop_loss), 90.0)
        self.assertIsNotNone(SignalPerformance.objects.get(signal=self.signal).actual_exit)

    def test_broker_quoted_setup_rejects_proxy_exit_data_and_keeps_quoted_entry(self):
        self.signal.strategy_evidence = {'evidence': {'execution_quote': {'spread': 1.0, 'ask': 100.0, 'bid': 99.0}}}
        self.signal.save(update_fields=['strategy_evidence'])
        frame = pd.DataFrame(
            [{'open': 107, 'high': 113, 'low': 105, 'close': 112}],
            index=pd.DatetimeIndex([self.entry_time + timedelta(minutes=1)]),
        )
        now = self.entry_time + timedelta(minutes=2, seconds=5)
        self.evaluate(frame, now)
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.exit_state, {})
        self.assertEqual(self.signal.status, 'ACTIVE')
        frame.attrs.update(provider='mt5', price_basis='bid')
        self.evaluate(frame, now)
        self.signal.refresh_from_db()
        self.assertEqual(self.signal.exit_state['fill_entry'], 100.0)
        self.assertEqual(self.signal.exit_state['initial_risk'], 10.0)
        self.assertEqual(self.signal.exit_state['current_sl'], 101.0)
