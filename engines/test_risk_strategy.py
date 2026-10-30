"""Risk regressions using observed bid/ask fixtures, never live orders."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from engines.risk import RiskEngine
from market_data.models import Instrument, MarketQuoteSpread
from signals.models import RiskDecision


class RiskStrategyTests(TestCase):
    def quote(self, symbol='XAUUSD', bid=99.95, ask=100.05, age=None, is_live=True):
        return MarketQuoteSpread.objects.create(
            instrument=Instrument.objects.get(symbol=symbol),
            timestamp=timezone.now() - (age or timedelta()),
            bid=Decimal(str(bid)), ask=Decimal(str(ask)),
            spread=Decimal(str(ask)) - Decimal(str(bid)),
            provider='observed-test-quote', is_live=is_live,
        )

    def evaluate(self, **overrides):
        arguments = dict(
            symbol='XAUUSD', direction='BUY', entry=100,
            stop_loss=90, take_profit=120, confidence=80,
            account_balance=10000, risk_percentage=0.5,
        )
        arguments.update(overrides)
        return RiskEngine.evaluate(**arguments)

    def test_two_r_trade_uses_observed_spread_and_preserves_existing_risk_cap(self):
        self.quote()
        risk = self.evaluate(risk_percentage=5)
        self.assertTrue(risk.is_allowed, risk.rejection_reasons)
        self.assertEqual(risk.risk_percentage, 0.5)
        self.assertEqual(risk.risk_amount_currency, 50)
        self.assertEqual(risk.current_spread_pips, 10)
        self.assertLessEqual(risk.recommended_lots * 1000, risk.risk_amount_currency)

    def test_ratio_below_two_is_rejected_even_when_it_rounds_to_two(self):
        self.quote()
        risk = self.evaluate(take_profit=119.999)
        self.assertFalse(risk.is_allowed)
        self.assertTrue(any('Risk:Reward' in reason for reason in risk.rejection_reasons))

    def test_missing_spread_rejects_and_persists_explicit_unavailable_check(self):
        risk = self.evaluate()
        self.assertFalse(risk.is_allowed)
        self.assertIsNone(risk.current_spread_pips)
        self.assertIsNone(risk.spread_cost_ratio_pct)
        record = RiskDecision.objects.latest('timestamp')
        self.assertFalse(record.is_trade_allowed)
        self.assertTrue(any('spread is unavailable' in reason for reason in record.rejection_reasons))
        self.assertEqual(record.checks, [{'name': 'fresh_live_spread', 'passed': False, 'value': None}])

    def test_stale_or_estimated_quotes_cannot_satisfy_live_spread_requirement(self):
        self.quote(age=timedelta(minutes=3))
        self.quote(is_live=False)
        risk = self.evaluate()
        self.assertFalse(risk.is_allowed)
        self.assertIsNone(risk.current_spread_pips)

    def test_spx500_uses_reviewed_paper_index_contract_not_forex_contract(self):
        lots, cash_per_lot, notional = RiskEngine.calculate_contract_sizing('SPX500', 6000, 5990, 50)
        self.assertEqual((lots, cash_per_lot, notional), (5, 10, 6000))
        self.quote(symbol='SPX500', bid=5999.9, ask=6000.1)
        risk = self.evaluate(symbol='SPX500', entry=6000, stop_loss=5990, take_profit=6020)
        self.assertTrue(risk.is_allowed, risk.rejection_reasons)
        self.assertEqual(risk.current_spread_pips, 2)  # Seeded pip unit is 0.1.
        self.assertEqual(risk.spread_cost_ratio_pct, 2)

    def test_index_spread_and_stop_distance_share_configured_pip_unit(self):
        self.quote(symbol='US30', bid=49999, ask=50001)
        risk = self.evaluate(symbol='US30', entry=50000, stop_loss=49900, take_profit=50200)
        self.assertTrue(risk.is_allowed, risk.rejection_reasons)
        self.assertEqual(risk.current_spread_pips, 2)  # Seeded US30 pip unit is 1.
        self.assertEqual(risk.spread_cost_ratio_pct, 2)

    def test_lot_step_is_floored_instead_of_rounded_up(self):
        lots, cash_per_lot, _ = RiskEngine.calculate_contract_sizing('XAUUSD', 100, 90, 16)
        self.assertEqual(lots, 0.01)
        self.assertLessEqual(lots * cash_per_lot, 16)

    def test_below_minimum_risk_size_is_rejected_instead_of_rounded_up(self):
        self.quote(bid=1999.95, ask=2000.05)
        risk = self.evaluate(entry=2000, stop_loss=1000, take_profit=4000)
        self.assertFalse(risk.is_allowed)
        self.assertEqual(risk.recommended_lots, 0)
        self.assertTrue(any('0.01 lot minimum' in reason for reason in risk.rejection_reasons))

    def test_malformed_or_nonfinite_inputs_fail_closed(self):
        for value in (None, float('nan'), float('inf')):
            with self.subTest(value=value):
                risk = self.evaluate(entry=value)
                self.assertFalse(risk.is_allowed)
                self.assertEqual(risk.recommended_lots, 0)
