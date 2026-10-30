"""Deterministic math fixtures only: these are not historical/backtest evidence."""
from unittest import TestCase

import numpy as np
import pandas as pd

from engines.institutional_setup import (
    TIMEFRAMES, TF_MINUTES, closed_candles, evaluate_setup, in_killzone,
)


class InstitutionalSetupTests(TestCase):
    AS_OF = pd.Timestamp('2026-10-28T08:00:00Z')

    def frames(self, direction='BUY', trigger='sweep', as_of=None):
        """Synthetic unit-test geometry, never a profitability simulation."""
        stamp = pd.Timestamp(as_of if as_of is not None else self.AS_OF)
        frames = {}
        for tf in TIMEFRAMES:
            delta = pd.Timedelta(minutes=TF_MINUTES[tf])
            last_open = stamp.floor(delta) - delta
            close = 100 + np.arange(220, dtype=float) * 0.5
            frame = pd.DataFrame({
                'open': close - 0.1, 'high': close + 0.3,
                'low': close - 0.3, 'close': close, 'volume': 100,
            }, index=pd.date_range(end=last_open, periods=220, freq=delta))
            if tf == 'M15' and trigger != 'none':
                ema20 = float(frame.close.ewm(span=20, adjust=False).mean().iloc[-2])
                if trigger == 'sweep':
                    last_low = float(frame.low.iloc[-6:-1].min()) - 0.5
                elif trigger == 'pullback':
                    frame.iloc[-4, frame.columns.get_loc('low')] = ema20 - 3
                    last_low = ema20 - 0.2
                else:
                    raise ValueError(trigger)
                frame.iloc[-1, frame.columns.get_loc('open')] = 209.0
                frame.iloc[-1, frame.columns.get_loc('close')] = 210.0
                frame.iloc[-1, frame.columns.get_loc('high')] = 210.3
                frame.iloc[-1, frame.columns.get_loc('low')] = last_low
            if direction == 'SELL':
                original = frame.copy()
                frame['open'], frame['close'] = 400 - original.open, 400 - original.close
                frame['high'], frame['low'] = 400 - original.low, 400 - original.high
            frames[tf] = frame
        return frames

    def evaluate(self, frames=None, **kwargs):
        return evaluate_setup(
            self.frames() if frames is None else frames,
            kwargs.pop('symbol', 'XAUUSD'), kwargs.pop('timeframe', 'M15'),
            as_of=kwargs.pop('as_of', self.AS_OF), **kwargs,
        )

    def test_bullish_and_bearish_completed_sweep_produce_structural_candidates(self):
        for direction in ('BUY', 'SELL'):
            with self.subTest(direction=direction):
                result = self.evaluate(self.frames(direction))
                self.assertTrue(result.allowed, result.reasons)
                self.assertEqual(result.direction, direction)
                self.assertEqual(result.setup_type, 'LIQUIDITY_SWEEP_RECLAIM')
                self.assertAlmostEqual(result.risk_reward, 2)
                invalidation = result.evidence['structural_invalidation']
                if direction == 'BUY':
                    self.assertLess(result.stop_loss, invalidation)
                    self.assertLess(result.stop_loss, result.entry)
                    self.assertGreater(result.take_profit, result.entry)
                else:
                    self.assertGreater(result.stop_loss, invalidation)
                    self.assertGreater(result.stop_loss, result.entry)
                    self.assertLess(result.take_profit, result.entry)

    def test_bullish_and_bearish_ema20_reclaim_without_sweep(self):
        for direction in ('BUY', 'SELL'):
            with self.subTest(direction=direction):
                result = self.evaluate(self.frames(direction, trigger='pullback'))
                self.assertTrue(result.allowed, result.reasons)
                self.assertEqual(result.direction, direction)
                self.assertEqual(result.setup_type, 'TREND_PULLBACK_RECLAIM')

    def test_trend_alignment_without_entry_trigger_stays_wait(self):
        for direction in ('BUY', 'SELL'):
            with self.subTest(direction=direction):
                result = self.evaluate(self.frames(direction, trigger='none'))
                self.assertFalse(result.allowed)
                self.assertEqual(result.direction, 'WAIT')
                self.assertTrue(any('No completed' in reason for reason in result.reasons))

    def test_exact_killzone_boundaries_are_utc_and_timezone_independent(self):
        for clock, expected in (
            ('06:59:59', False), ('07:00:00', True), ('10:59:59', True),
            ('11:00:00', False), ('12:59:59', False), ('13:00:00', True),
            ('16:59:59', True), ('17:00:00', False),
        ):
            with self.subTest(clock=clock):
                stamp = pd.Timestamp(f'2026-10-28T{clock}Z')
                self.assertEqual(in_killzone(stamp), expected)
                self.assertEqual(in_killzone(stamp.tz_convert('Asia/Karachi')), expected)
                result = self.evaluate(self.frames(as_of=stamp), as_of=stamp)
                if expected:
                    self.assertTrue(result.allowed, result.reasons)
                else:
                    self.assertTrue(any('Outside M15 killzones' in reason for reason in result.reasons))

    def test_forming_and_future_bars_do_not_influence_any_timeframe(self):
        frames = self.frames()
        for tf in TIMEFRAMES:
            # Deliberately invalid prices must be ignored because these bars
            # cannot have been observed as completed at the evaluation time.
            delta = pd.Timedelta(minutes=TF_MINUTES[tf])
            extras = pd.DataFrame(
                {'open': [np.nan, -1], 'high': [np.nan, -1],
                 'low': [np.nan, -1], 'close': [np.nan, -1], 'volume': [0, 0]},
                index=pd.DatetimeIndex([self.AS_OF, self.AS_OF + delta]),
            )
            frames[tf] = pd.concat([frames[tf], extras])
            completed = closed_candles(frames[tf], tf, self.AS_OF)
            self.assertEqual(len(completed), 220)
            self.assertTrue((completed.index + delta <= self.AS_OF).all())
        result = self.evaluate(frames)
        self.assertTrue(result.allowed, result.reasons)
        self.assertEqual(result.entry, 210)

    def test_candle_is_included_at_exact_close_and_excluded_one_second_before(self):
        frame = self.frames()['M15']
        at_close = closed_candles(frame, 'M15', self.AS_OF)
        before_close = closed_candles(frame, 'M15', self.AS_OF - pd.Timedelta(seconds=1))
        self.assertEqual(len(at_close), 220)
        self.assertEqual(len(before_close), 219)

    def test_price_above_both_emas_does_not_replace_full_ema_chain(self):
        frames = self.frames()
        values = np.append(np.linspace(300, 180, 219), 310)
        frame = frames['H4']
        frame['close'], frame['open'] = values, values - 0.1
        frame['high'], frame['low'] = values + 0.3, values - 0.3
        result = self.evaluate(frames)
        self.assertFalse(result.allowed)
        h4 = result.evidence['trends']['H4']
        self.assertGreater(h4['close'], h4['ema50'])
        self.assertGreater(h4['close'], h4['ema200'])
        self.assertLess(h4['ema50'], h4['ema200'])
        self.assertEqual(h4['direction'], 'WAIT')

    def test_one_opposing_timeframe_or_proposed_direction_vetoes_candidate(self):
        frames = self.frames()
        frames['H4'] = self.frames('SELL')['H4']
        self.assertFalse(self.evaluate(frames).allowed)
        result = self.evaluate(direction='SELL')
        self.assertFalse(result.allowed)
        self.assertTrue(any('conflicts with BUY' in reason for reason in result.reasons))

    def test_provided_stop_inside_structure_is_rejected(self):
        for direction in ('BUY', 'SELL'):
            with self.subTest(direction=direction):
                frames = self.frames(direction)
                candidate = self.evaluate(frames)
                stop = candidate.entry - 0.1 if direction == 'BUY' else candidate.entry + 0.1
                target = candidate.entry + 1 if direction == 'BUY' else candidate.entry - 1
                result = self.evaluate(frames, direction=direction, stop_loss=stop, take_profit=target)
                self.assertFalse(result.allowed)
                self.assertTrue(any('beyond structural invalidation' in reason for reason in result.reasons))

    def test_provided_under_two_r_target_is_rejected_without_extending_it(self):
        for direction in ('BUY', 'SELL'):
            with self.subTest(direction=direction):
                frames = self.frames(direction)
                candidate = self.evaluate(frames)
                distance = abs(candidate.entry - candidate.stop_loss)
                target = candidate.entry + 1.5 * distance if direction == 'BUY' else candidate.entry - 1.5 * distance
                result = self.evaluate(frames, stop_loss=candidate.stop_loss, take_profit=target)
                self.assertFalse(result.allowed)
                self.assertEqual(result.direction, 'WAIT')
                self.assertTrue(any('1.500R' in reason for reason in result.reasons))

    def test_missing_history_naive_timestamps_nan_and_geometry_fail_closed(self):
        mutations = {
            'missing': lambda frames: frames.pop('H4'),
            'short': lambda frames: frames.update(H1=frames['H1'].tail(199)),
            'naive': lambda frames: setattr(frames['H1'], 'index', frames['H1'].index.tz_localize(None)),
            'nan': lambda frames: frames.update(H1=frames['H1'].assign(close=np.nan)),
            'geometry': lambda frames: frames.update(H1=frames['H1'].assign(high=frames['H1'].low - 1)),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                frames = self.frames()
                mutate(frames)
                result = self.evaluate(frames)
                self.assertFalse(result.allowed)
                self.assertEqual(result.direction, 'WAIT')
                self.assertTrue(result.reasons)

    def test_naive_asof_and_unapproved_scope_are_rejected(self):
        for kwargs in (
            {'as_of': self.AS_OF.tz_localize(None)},
            {'symbol': 'EURUSD'}, {'timeframe': 'D1'},
        ):
            with self.subTest(kwargs=kwargs):
                result = self.evaluate(**kwargs)
                self.assertFalse(result.allowed)
                self.assertEqual(result.direction, 'WAIT')

    def test_duplicate_or_unsorted_history_is_rejected(self):
        for duplicate in (True, False):
            frames = self.frames()
            frame = frames['H1']
            frames['H1'] = pd.concat([frame, frame.tail(1)]) if duplicate else frame.iloc[::-1]
            result = self.evaluate(frames)
            self.assertFalse(result.allowed)
            self.assertTrue(any('duplicate or out-of-order' in reason for reason in result.reasons))

    def test_stale_completed_history_is_not_treated_as_a_current_setup(self):
        frames = self.frames()
        frames['H4'].index = frames['H4'].index - pd.Timedelta(hours=8)
        result = self.evaluate(frames)
        self.assertFalse(result.allowed)
        self.assertTrue(any('H4: history is stale' in reason for reason in result.reasons))

    def test_spread_must_be_finite_nonnegative_and_within_stop_budget(self):
        for spread in (float('nan'), -1, 100):
            with self.subTest(spread=spread):
                result = self.evaluate(spread=spread)
                self.assertFalse(result.allowed)
                self.assertEqual(result.direction, 'WAIT')
