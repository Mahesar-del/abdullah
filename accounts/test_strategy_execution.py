"""New-strategy paper execution must consume the canonical signal result once."""
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
from django.test import TestCase
from django.utils import timezone

from accounts.auto_trader import AutoTraderEngine
from accounts.models import AutoTradeExecution, LinkedBrokerAccount
from engines.institutional_setup import STRATEGY_VERSION
from market_data.models import Instrument
from signals.models import Signal, SignalPerformance


class CanonicalPaperExecutionTests(TestCase):
    def setUp(self):
        self.instrument = Instrument.objects.get(symbol='XAUUSD')
        self.account = LinkedBrokerAccount.objects.create(
            name='Isolated paper test', broker_type='PAPER', is_paper=True,
            balance=10000, equity=10000, is_active=True, is_authorized=True,
            auto_trade_enabled=True, authorization_status='ON', connection_status='CONNECTED',
        )
        self.notifications = patch.object(AutoTraderEngine, '_notify_trade_closed').start()
        self.open_notifications = patch.object(AutoTraderEngine, '_notify_trade_opened').start()
        self.fetch = patch('accounts.auto_trader.DataFetcher.fetch', return_value=None).start()
        self.mt5_send = patch.object(AutoTraderEngine, '_send_mt5_order').start()
        self.mt5_close = patch.object(AutoTraderEngine, '_close_mt5_position').start()
        self.addCleanup(patch.stopall)

    def make_signal(self, status='ACTIVE', evidence=None):
        return Signal.objects.create(
            instrument=self.instrument, timeframe='H1', direction='BUY', strength='STRONG',
            status=status, entry_price=100, stop_loss=90, take_profit_1=120,
            risk_reward=2, confidence_score=85, is_trade_allowed=True,
            strategy_evidence=evidence if evidence is not None else {
                'allowed': True,
                'evidence': {
                    'strategy_version': STRATEGY_VERSION,
                    'execution_quote': {'bid': 99.5, 'ask': 100.0, 'spread': 0.5},
                },
            },
        )

    def make_trade(self, signal, moved_stop=100.5):
        return AutoTradeExecution.objects.create(
            account=self.account, signal=signal, symbol='XAUUSD', direction='BUY',
            volume_lots=0.1, entry_price=100, stop_loss=moved_stop,
            take_profit_1=120, current_price=105, risk_amount_currency=100,
            status='OPEN', broker_order_id='PAPER-TEST',
        )

    def assert_no_broker_dispatch(self):
        self.mt5_send.assert_not_called()
        self.mt5_close.assert_not_called()

    def test_tp_uses_saved_net_r_and_exit_despite_stop_moved_to_breakeven(self):
        signal = self.make_signal('HIT_TP')
        trade = self.make_trade(signal)
        SignalPerformance.objects.create(
            signal=signal, outcome='WIN', pnl_r=1.85, actual_exit=Decimal('119.75'),
        )
        closed = AutoTraderEngine.close_open_trades_for_signal(signal, 'HIT_TP', 120)
        trade.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(len(closed), 1)
        self.assertEqual(trade.status, 'CLOSED')
        self.assertEqual(trade.exit_reason, 'TP_HIT')
        self.assertAlmostEqual(trade.pnl_r, 1.85)
        self.assertEqual(trade.pnl_amount, Decimal('185.00'))
        self.assertAlmostEqual(trade.exit_price, 119.75)
        self.assertEqual(self.account.balance, Decimal('10185.00'))
        self.assertEqual(self.account.equity, self.account.balance)
        self.assertEqual(SignalPerformance.objects.get(signal=signal).pnl_r, 1.85)
        self.notifications.assert_called_once()
        self.assert_no_broker_dispatch()

    def test_breakeven_preserves_small_modeled_fee_loss(self):
        signal = self.make_signal('BREAKEVEN')
        trade = self.make_trade(signal)
        SignalPerformance.objects.create(
            signal=signal, outcome='BREAKEVEN', pnl_r=-0.03, actual_exit=Decimal('99.97'),
        )
        AutoTraderEngine.close_open_trades_for_signal(signal, 'BREAKEVEN', 100)
        trade.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(trade.status, 'CLOSED')
        self.assertEqual(trade.exit_reason, 'BREAKEVEN')
        self.assertAlmostEqual(trade.pnl_r, -0.03)
        self.assertEqual(trade.pnl_amount, Decimal('-3.00'))
        self.assertAlmostEqual(trade.exit_price, 99.97)
        self.assertEqual(self.account.balance, Decimal('9997.00'))
        self.assert_no_broker_dispatch()

    def test_expiry_closes_paper_position_using_saved_result(self):
        signal = self.make_signal('EXPIRED')
        trade = self.make_trade(signal)
        SignalPerformance.objects.create(
            signal=signal, outcome='WIN', pnl_r=0.4, actual_exit=Decimal('104.00'),
        )
        AutoTraderEngine.close_open_trades_for_signal(signal, 'EXPIRED', 100)
        trade.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(trade.status, 'CLOSED')
        self.assertEqual(trade.exit_reason, 'EXPIRED')
        self.assertAlmostEqual(trade.pnl_r, 0.4)
        self.assertEqual(trade.pnl_amount, Decimal('40.00'))
        self.assertEqual(trade.exit_price, 104.0)
        self.assertEqual(self.account.balance, Decimal('10040.00'))
        self.assert_no_broker_dispatch()

    def test_active_strategy_execution_bypasses_competing_ohlc_exit_path(self):
        signal = self.make_signal()
        signal.exit_state = {'be_active': True, 'current_sl': 100.75}
        signal.save(update_fields=['exit_state'])
        trade = self.make_trade(signal, moved_stop=90)
        self.fetch.return_value = pd.DataFrame(
            [{'open': 100, 'high': 1000, 'low': 1, 'close': 1000}],
            index=pd.DatetimeIndex([timezone.now()]),
        )
        result = AutoTraderEngine.evaluate_and_close_open_trades()
        trade.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(result, [])
        self.assertEqual(trade.status, 'OPEN')
        self.assertEqual(trade.stop_loss, 100.75)
        self.assertEqual(trade.pnl_amount, Decimal('0.00'))
        self.assertEqual(self.account.balance, Decimal('10000.00'))
        self.assertFalse(SignalPerformance.objects.filter(signal=signal).exists())
        self.notifications.assert_not_called()
        self.assert_no_broker_dispatch()

    def test_missing_approved_evidence_cannot_reach_order_dispatch(self):
        signal = self.make_signal(evidence={})
        with patch('accounts.auto_trader.SystemTradingConfig.get_config') as config:
            result = AutoTraderEngine.execute_for_signal(signal)
        self.assertEqual(result, [])
        config.assert_not_called()
        self.assertFalse(AutoTradeExecution.objects.exists())
        self.open_notifications.assert_not_called()
        self.assert_no_broker_dispatch()

    def test_stale_strategy_version_cannot_reach_order_dispatch(self):
        signal = self.make_signal(evidence={'allowed': True, 'evidence': {'strategy_version': 'unreviewed-old-version'}})
        with patch('accounts.auto_trader.SystemTradingConfig.get_config') as config:
            result = AutoTraderEngine.execute_for_signal(signal)
        self.assertEqual(result, [])
        config.assert_not_called()
        self.assertFalse(AutoTradeExecution.objects.exists())
        self.assert_no_broker_dispatch()

    def test_repeated_canonical_close_does_not_credit_balance_twice(self):
        signal = self.make_signal('HIT_TP')
        trade = self.make_trade(signal)
        SignalPerformance.objects.create(signal=signal, outcome='WIN', pnl_r=1.8, actual_exit=118)
        AutoTraderEngine.close_open_trades_for_signal(signal, 'HIT_TP', 120)
        second = AutoTraderEngine.close_open_trades_for_signal(signal, 'HIT_TP', 120)
        self.account.refresh_from_db()
        trade.refresh_from_db()
        self.assertEqual(second, [])
        self.assertEqual(self.account.balance, Decimal('10180.00'))
        self.assertEqual(trade.status, 'CLOSED')
        self.notifications.assert_called_once()
        self.assert_no_broker_dispatch()
