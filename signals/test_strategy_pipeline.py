"""Isolated integration checks: no MT5 connection, orders or model training."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from rest_framework.renderers import JSONRenderer

from engines.institutional_setup import SetupDecision
from market_data.models import Instrument, MarketQuoteSpread
from signals.auto_scanner import scan_single
from signals.generator_views import GenerateSignalView
from signals.models import Signal
from signals.strategy_pipeline import _fresh_broker_quote, create_signal_once, current_status, prepare_setup, validate_proposal


class StrategyPipelineTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)
        self.instrument = Instrument.objects.get(symbol='XAUUSD')

    def test_missing_and_proxy_sources_reject_before_structural_or_unified_engine(self):
        for source in (None, 'yahoo', 'database_cache'):
            with self.subTest(source=source):
                frame = None if source is None else pd.DataFrame({'close': [100.0]})
                if frame is not None:
                    frame.attrs['provider'] = source
                fetcher = MagicMock()
                fetcher.fetch.return_value = frame
                with patch('signals.strategy_pipeline.evaluate_setup') as evaluator:
                    frames, closed, candidate, quote = prepare_setup(fetcher, 'XAUUSD', 'H1', self.now)
                self.assertFalse(candidate.allowed)
                self.assertIsNone(closed)
                self.assertIsNone(quote)
                self.assertEqual(len(frames), 3)
                self.assertIn('Actual broker candles required', candidate.reasons[0])
                evaluator.assert_not_called()

    def test_out_of_session_m15_rejects_before_data_fetch(self):
        fetcher = MagicMock()
        _, _, candidate, _ = prepare_setup(fetcher, 'XAUUSD', 'M15', self.now.replace(hour=12))
        self.assertFalse(candidate.allowed)
        self.assertIn('killzones', candidate.reasons[0])
        fetcher.fetch.assert_not_called()

    def test_fresh_quote_persists_observed_bid_ask_once(self):
        fake_mt5 = SimpleNamespace(symbol_info_tick=MagicMock(return_value=SimpleNamespace(
            time=self.now.timestamp(), bid=2000.0, ask=2000.5,
        )), order_send=MagicMock())
        with patch.dict('sys.modules', {'MetaTrader5': fake_mt5}):
            quote = _fresh_broker_quote('XAUUSD', 'XAUUSD', self.now)
            _fresh_broker_quote('XAUUSD', 'XAUUSD', self.now)
        self.assertEqual(quote['spread'], 0.5)
        self.assertEqual(quote['provider'], 'mt5_terminal')
        self.assertEqual(MarketQuoteSpread.objects.count(), 1)
        stored = MarketQuoteSpread.objects.get()
        self.assertTrue(stored.is_live)
        self.assertEqual(float(stored.bid), 2000.0)
        self.assertEqual(float(stored.ask), 2000.5)
        self.assertEqual(stored.timestamp, self.now)
        fake_mt5.order_send.assert_not_called()

    def test_stale_future_or_invalid_quotes_never_persist(self):
        for age_seconds, bid, ask in ((-121, 100, 101), (31, 100, 101), (0, 101, 100), (0, float('nan'), 101)):
            with self.subTest(age_seconds=age_seconds, bid=bid, ask=ask):
                fake_mt5 = SimpleNamespace(symbol_info_tick=MagicMock(return_value=SimpleNamespace(
                    time=(self.now + timedelta(seconds=age_seconds)).timestamp(), bid=bid, ask=ask,
                )))
                with patch.dict('sys.modules', {'MetaTrader5': fake_mt5}), self.assertRaises(ValueError):
                    _fresh_broker_quote('XAUUSD', 'XAUUSD', self.now)
        self.assertFalse(MarketQuoteSpread.objects.exists())

    def test_a_structural_candidate_still_requires_a_fresh_broker_quote(self):
        frame = pd.DataFrame({'close': [100.0]})
        frame.attrs.update(provider='mt5', broker_symbol='XAUUSD')
        fetcher = MagicMock()
        fetcher.fetch.return_value = frame
        candidate = SetupDecision(allowed=True, direction='BUY')
        with (
            patch('signals.strategy_pipeline.evaluate_setup', return_value=candidate),
            patch('signals.strategy_pipeline._fresh_broker_quote', side_effect=ValueError('stale')),
        ):
            _, closed, result, quote = prepare_setup(fetcher, 'XAUUSD', 'H1', self.now)
        self.assertFalse(result.allowed)
        self.assertEqual(result.direction, 'WAIT')
        self.assertIn('Fresh broker quote required', result.reasons[0])
        self.assertIsNone(closed)
        self.assertIsNone(quote)

    def test_manual_generator_and_scanner_share_source_rejection_without_side_effects(self):
        fake_mt5 = SimpleNamespace(order_send=MagicMock(), initialize=MagicMock())
        with (
            patch('engines.data_fetcher.DataFetcher.fetch', return_value=None),
            patch('signals.generator_views.UnifiedSignalEngine') as manual_engine,
            patch('engines.unified.UnifiedSignalEngine') as scanner_engine,
            patch('accounts.auto_trader.AutoTraderEngine.execute_for_signal') as execute,
            patch('engines.learning.ContinuousLearningEngine.retrain_all_core_symbols') as retrain,
            patch.dict('sys.modules', {'MetaTrader5': fake_mt5}),
        ):
            request = APIRequestFactory().post('/api/signals/generate/', {'symbol': 'XAUUSD', 'timeframe': 'H1'}, format='json')
            response = GenerateSignalView.as_view()(request)
            scanned = scan_single('XAUUSD', 'H1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['direction'], 'WAIT')
        self.assertIn('Actual broker candles required', response.data['message'])
        self.assertIsNone(scanned)
        self.assertFalse(Signal.objects.exists())
        manual_engine.assert_not_called()
        scanner_engine.assert_not_called()
        execute.assert_not_called()
        retrain.assert_not_called()
        fake_mt5.initialize.assert_not_called()
        fake_mt5.order_send.assert_not_called()

    def test_low_score_or_denied_risk_does_not_run_proposal_gate(self):
        for allowed, confidence in ((False, 90), (True, 74.9), (True, float('nan'))):
            with self.subTest(allowed=allowed, confidence=confidence):
                unified = SimpleNamespace(direction='BUY', is_trade_allowed=allowed, confidence=confidence,
                                          risk_rejection_reasons=['risk rejected'] if not allowed else [], warnings=[])
                with patch('signals.strategy_pipeline.evaluate_setup') as evaluate:
                    decision = validate_proposal({}, 'XAUUSD', 'H1', unified,
                                                 {'spread': 0.1, 'observed_at': self.now.isoformat()}, self.now)
                self.assertFalse(decision.allowed)
                evaluate.assert_not_called()

    def test_same_setup_bar_cannot_reopen_after_resolution_or_reverse_direction(self):
        values = dict(instrument=self.instrument, timeframe='H1', setup_bar_opened_at=self.now,
                      direction='BUY', strength='STRONG', status='HIT_SL', entry_price=100,
                      stop_loss=90, take_profit_1=120, risk_reward=2, confidence_score=80)
        Signal.objects.create(**values)
        values.update(direction='SELL', status='ACTIVE')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Signal.objects.create(**values)
        self.assertEqual(Signal.objects.count(), 1)

    def test_nonfinite_rejected_score_status_remains_json_serializable(self):
        unified = SimpleNamespace(direction='BUY', is_trade_allowed=True, confidence=float('nan'),
                                  risk_rejection_reasons=[], warnings=[])
        validate_proposal({}, 'XAUUSD', 'H1', unified,
                          {'spread': 0.1, 'observed_at': self.now.isoformat()}, self.now)
        rendered = JSONRenderer().render(current_status())
        self.assertNotIn(b'NaN', rendered)

    def test_quote_that_became_stale_during_engine_run_cannot_qualify(self):
        unified = SimpleNamespace(direction='BUY', is_trade_allowed=True, confidence=80,
                                  entry=100, stop_loss=90, take_profit_1=120,
                                  risk_rejection_reasons=[], warnings=[])
        quote = {'spread': 0.1, 'bid': 99.9, 'ask': 100.0,
                 'observed_at': (self.now - timedelta(minutes=3)).isoformat()}
        with patch('signals.strategy_pipeline.evaluate_setup', return_value=SetupDecision(allowed=True, direction='BUY')) as evaluate:
            result = validate_proposal({}, 'XAUUSD', 'H1', unified, quote, self.now)
        self.assertFalse(result.allowed)
        evaluate.assert_not_called()

    def test_legacy_null_setup_rows_are_preserved(self):
        values = dict(instrument=self.instrument, timeframe='H1', direction='BUY', strength='STRONG',
                      status='HIT_SL', entry_price=100, stop_loss=90, take_profit_1=120,
                      risk_reward=2, confidence_score=80)
        Signal.objects.create(**values)
        Signal.objects.create(**values)
        self.assertEqual(Signal.objects.count(), 2)

    def test_future_dated_broker_history_is_not_silently_accepted(self):
        frame = pd.DataFrame({'close': [100.0]}, index=pd.DatetimeIndex([self.now + timedelta(hours=2)]))
        frame.attrs.update(provider='mt5', broker_symbol='XAUUSD')
        fetcher = MagicMock()
        fetcher.fetch.return_value = frame
        with patch('signals.strategy_pipeline.evaluate_setup') as evaluate:
            _, _, result, _ = prepare_setup(fetcher, 'XAUUSD', 'H1', self.now)
        self.assertFalse(result.allowed)
        self.assertIn('Broker clock anomaly', result.reasons[0])
        evaluate.assert_not_called()

    def test_analysis_crossing_candle_close_requires_new_snapshot(self):
        frame = pd.DataFrame({'close': [100.0]})
        frame.attrs['snapshot_as_of'] = (self.now - timedelta(seconds=1)).isoformat()
        quote = {'spread': 0.1, 'bid': 99.9, 'ask': 100.0, 'observed_at': self.now.isoformat()}
        unified = SimpleNamespace(direction='BUY', is_trade_allowed=True, confidence=80,
                                  entry=100, stop_loss=90, take_profit_1=120,
                                  risk_rejection_reasons=[], warnings=[])
        with patch('signals.strategy_pipeline.evaluate_setup') as evaluate:
            result = validate_proposal({'H1': frame}, 'XAUUSD', 'H1', unified, quote, self.now)
        self.assertFalse(result.allowed)
        self.assertIn('new M15 candle', result.reasons[0])
        evaluate.assert_not_called()

    def test_duplicate_create_helper_returns_none_for_resolved_setup(self):
        values = dict(instrument=self.instrument, timeframe='H1', setup_bar_opened_at=self.now,
                      direction='BUY', strength='STRONG', status='HIT_SL', entry_price=100,
                      stop_loss=90, take_profit_1=120, risk_reward=2, confidence_score=80)
        first = create_signal_once(**values)
        self.assertIsNotNone(first)
        self.assertIsNone(create_signal_once(**values))
        self.assertEqual(Signal.objects.count(), 1)
