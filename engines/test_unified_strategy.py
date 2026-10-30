"""Deterministic strategy regressions; sub-engines and risk persistence are isolated."""
from unittest.mock import patch

import pandas as pd
from django.test import SimpleTestCase

from engines.base import EngineResult
from engines.data_quality import DataQualityReport
from engines.risk import RiskEvaluation
from engines.unified import UnifiedSignalEngine


class UnifiedStrategyTests(SimpleTestCase):
    def setUp(self):
        close = pd.Series(range(100, 350), dtype=float)
        self.frame = pd.DataFrame({
            'open': close - 0.2, 'high': close + 1, 'low': close - 1,
            'close': close, 'volume': 100,
        })
        self.engine = UnifiedSignalEngine(self.frame, 'XAUUSD', 'M15')

    def result(self, name, direction='BUY', score=90, sl=None, tp=None, reasoning=None):
        return EngineResult(
            engine_name=name, score=score, direction=direction, confidence=score,
            reasoning=reasoning or ['Deterministic fixture'], weight=0,
            sl_zone=sl, tp_zone=tp,
        )

    def generate(self, overrides=None):
        overrides = overrides or {}
        risk = RiskEvaluation(
            is_allowed=True, direction='BUY', recommended_lots=0.1,
            risk_amount_currency=100, risk_percentage=1, risk_reward_ratio=2,
            current_spread_pips=1, spread_cost_ratio_pct=1,
        )
        quality = DataQualityReport(cleaned_df=self.frame)

        def run_engine(cls, name):
            if name in overrides:
                return overrides[name]
            return self.result(name, direction='NEUTRAL' if name == 'news' else 'BUY')

        with (
            patch('engines.data_quality.DataQualityValidator.validate_ohlcv', return_value=quality),
            patch.object(self.engine, '_run_engine', side_effect=run_engine),
            patch('engines.unified.RiskEngine.evaluate', return_value=risk),
        ):
            return self.engine.generate()

    def test_default_buy_and_sell_levels_have_two_r_target(self):
        for direction in ('BUY', 'SELL'):
            entry, sl, tp, _, _, rr = self.engine._calculate_levels(direction, 100, 2, {})
            self.assertEqual(rr, 2.0)
            self.assertEqual(abs(tp - entry) / abs(sl - entry), 2.0)

    def test_low_reward_structural_target_is_vetoed_without_fabricating_target(self):
        smc = self.result('smc_ict', sl=339, tp=364)  # Entry 349: 1.5R.
        signal = self.generate({'smc_ict': smc})
        self.assertEqual(signal.direction, 'WAIT')
        self.assertFalse(signal.is_trade_allowed)
        self.assertEqual(signal.recommended_lots, 0)
        self.assertEqual(signal.take_profit_1, 364)
        self.assertEqual(signal.risk_reward, 1.5)
        self.assertTrue(any('below required 2.00R' in reason for reason in signal.risk_rejection_reasons))

    def test_maximum_rr_changes_actual_target_as_well_as_displayed_ratio(self):
        smc = self.result('smc_ict', sl=99, tp=120)
        entry, sl, tp, _, _, rr = self.engine._calculate_levels('BUY', 100, 2, {'smc_ict': smc})
        self.assertEqual(rr, 5)
        self.assertEqual(tp, 105)
        self.assertEqual(abs(tp - entry) / abs(sl - entry), rr)

    def test_opposing_weighted_score_cannot_boost_majority_direction(self):
        overrides = {
            'smc_ict': self.result('smc_ict', score=1),
            'technical': self.result('technical', score=1),
            'godzilla': self.result('godzilla', score=1),
            'master_traders': self.result('master_traders', direction='SELL', score=100),
            'macro': self.result('macro', direction='SELL', score=100),
        }
        signal = self.generate(overrides)
        self.assertEqual(signal.direction, 'WAIT')
        self.assertEqual(signal.decision_class, 'CONFLICT')
        self.assertFalse(signal.is_trade_allowed)

    def test_missing_required_evidence_fails_closed(self):
        signal = self.generate({'macro': None})
        self.assertEqual(signal.direction, 'WAIT')
        self.assertEqual(signal.decision_class, 'DATA_ERROR')
        self.assertFalse(signal.is_trade_allowed)

    def test_news_reasoning_blackout_is_enforced(self):
        signal = self.generate({'news': self.result('news', direction='NEUTRAL', reasoning=['BLACKOUT: event window'])})
        self.assertEqual(signal.direction, 'WAIT')
        self.assertEqual(signal.decision_class, 'BLACKOUT')

    def test_score_is_not_raised_to_pass_scanner_threshold(self):
        overrides = {name: self.result(name, score=60) for name in self.engine.weights if self.engine.weights[name] > 0}
        signal = self.generate(overrides)
        self.assertEqual(signal.confidence, 76.0)  # 60*0.6 + 100*0.4, no floor.
        overrides = {name: self.result(name, score=50) for name in self.engine.weights if self.engine.weights[name] > 0}
        signal = self.generate(overrides)
        self.assertEqual(signal.confidence, 70.0)

    def test_invalid_data_does_not_run_engines(self):
        quality = DataQualityReport(force_wait=True, quality_score=0, errors=['Empty input'])
        with (
            patch('engines.data_quality.DataQualityValidator.validate_ohlcv', return_value=quality),
            patch.object(self.engine, '_run_engine') as run_engine,
            patch('engines.unified.RiskEngine.evaluate') as risk,
        ):
            signal = self.engine.generate()
        run_engine.assert_not_called()
        risk.assert_not_called()
        self.assertEqual(signal.direction, 'WAIT')
        self.assertFalse(signal.is_trade_allowed)

    def test_requested_timeframe_reaches_aware_sub_engine(self):
        fixture = self.result('test')
        observed = []

        class AwareEngine:
            def __init__(self, df, symbol, timeframe='H1'):
                observed.append(timeframe)

            def analyze(self):
                return fixture

        self.engine._run_engine(AwareEngine, 'test')
        self.assertEqual(observed, ['M15'])

    def test_nonfinite_engine_score_is_unavailable(self):
        fixture = self.result('test', score=float('nan'))

        class InvalidEngine:
            def __init__(self, df, symbol):
                pass

            def analyze(self):
                return fixture

        self.assertIsNone(self.engine._run_engine(InvalidEngine, 'test'))
