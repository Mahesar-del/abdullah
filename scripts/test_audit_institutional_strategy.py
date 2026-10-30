"""Offline execution invariants; these fixtures are not performance evidence."""
import unittest
from unittest.mock import patch
import json
from pathlib import Path
import tempfile

import pandas as pd

from scripts.audit_institutional_strategy import main, prepare_frames, simulate_position


class CandidateReplayExecutionTests(unittest.TestCase):
    def bars(self, records):
        return pd.DataFrame(records, index=pd.date_range('2026-01-01T07:00:00Z', periods=len(records), freq='15min'))

    def test_same_bar_target_and_stop_is_a_loss(self):
        bars = self.bars([{'open': 100, 'high': 125, 'low': 85, 'close': 110, 'spread': 0}])
        trade = simulate_position(bars, 0, 'BUY', 100, 90, 120, 1, 0, 0)
        self.assertEqual(trade['reason'], 'STOP_LOSS')
        self.assertEqual(trade['realized_r'], -1)

    def test_new_be_does_not_use_same_bar_earlier_low(self):
        bars = self.bars([
            {'open': 100, 'high': 112, 'low': 95, 'close': 111, 'spread': 1},
            {'open': 111, 'high': 114, 'low': 105, 'close': 110, 'spread': 1},
        ])
        trade = simulate_position(bars, 0, 'BUY', 100, 90, 120, 1, 0, 0, 2)
        self.assertEqual(trade['reason'], 'TIME_EXIT')
        self.assertEqual(trade['realized_r'], 1)

    def test_gap_through_stop_does_not_fill_at_ideal_stop(self):
        bars = self.bars([{'open': 80, 'high': 88, 'low': 75, 'close': 85, 'spread': 0}])
        trade = simulate_position(bars, 0, 'BUY', 100, 90, 120, 1, 0, 0)
        self.assertEqual(trade['realized_r'], -2)

    def test_short_uses_ask_and_commission(self):
        bars = self.bars([{'open': 100, 'high': 108, 'low': 96, 'close': 100, 'spread': 3}])
        trade = simulate_position(bars, 0, 'SELL', 100, 110, 80, 1, 1, 1)
        self.assertEqual(trade['reason'], 'STOP_LOSS')
        self.assertGreater(trade['exit'], 110)
        self.assertLess(trade['realized_r'], -1)

    def test_coverage_excludes_unfinished_bar_without_filling_gaps(self):
        raw = {'frames': {'M15': {'rates': [
            {'time': 1767250800, 'open': 100, 'high': 101, 'low': 99, 'close': 100},
            {'time': 1767252600, 'open': 100, 'high': 101, 'low': 99, 'close': 100},
        ]}}}
        end = pd.Timestamp(1767252600, unit='s', tz='UTC') + pd.Timedelta(minutes=10)
        frames, coverage = prepare_frames(raw, end)
        self.assertEqual(len(frames['M15']), 1)
        self.assertEqual(coverage['M15']['returned_bars'], 2)
        self.assertEqual(coverage['M15']['completed_bars'], 1)

    def test_future_bar_open_is_a_clock_anomaly_without_timezone_shifting(self):
        as_of = pd.Timestamp('2026-10-27T19:34:38Z')
        raw = {'frames': {'M15': {'rates': [
            {'time': int(pd.Timestamp('2026-10-27T19:00:00Z').timestamp()), 'open': 100, 'high': 101, 'low': 99, 'close': 100},
            {'time': int(pd.Timestamp('2026-10-27T21:30:00Z').timestamp()), 'open': 100, 'high': 101, 'low': 99, 'close': 100},
        ]}}}
        frames, coverage = prepare_frames(raw, as_of)
        self.assertEqual(coverage['M15']['status'], 'CLOCK_ANOMALY')
        self.assertEqual(coverage['M15']['future_bars'], 1)
        self.assertEqual(coverage['M15']['largest_future_ahead_seconds'], 6922)
        self.assertEqual(coverage['M15']['source_last_bar_open_utc'], '2026-10-27T21:30:00+00:00')
        self.assertEqual(frames['M15'].index[0], pd.Timestamp('2026-10-27T19:00:00Z'))

    def test_current_unfinished_bar_is_not_a_future_open(self):
        raw = {'frames': {'M15': {'rates': [
            {'time': int(pd.Timestamp('2026-10-27T19:30:00Z').timestamp()), 'open': 100, 'high': 101, 'low': 99, 'close': 100},
        ]}}}
        _, coverage = prepare_frames(raw, pd.Timestamp('2026-10-27T19:34:38Z'))
        self.assertEqual(coverage['M15']['status'], 'OK')
        self.assertEqual(coverage['M15']['future_bars'], 0)
        self.assertEqual(coverage['M15']['completed_bars'], 0)

    def test_clock_anomaly_prevents_any_benchmark_call(self):
        future_open = pd.Timestamp.now(tz='UTC') + pd.Timedelta(hours=2)
        raw = {'status': 'OK', 'specifications': {}, 'frames': {'M15': {'rates': [
            {'time': int(future_open.timestamp()), 'open': 100, 'high': 101, 'low': 99, 'close': 100},
        ]}}}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'audit.json'
            with (
                patch('scripts.audit_institutional_strategy.read_broker_history', return_value=raw),
                patch('scripts.audit_institutional_strategy.benchmark') as replay,
                patch('scripts.audit_institutional_strategy.ROOT', Path(directory)),
            ):
                main(['--symbols', 'XAUUSD', '--bars', '400', '--output', str(output)])
            report = json.loads(output.read_text(encoding='utf-8'))
        replay.assert_not_called()
        self.assertEqual(report['status'], 'CLOCK_ANOMALY')
        self.assertEqual(report['assets']['XAUUSD']['benchmark']['status'], 'NOT_RUN')


if __name__ == '__main__':
    unittest.main()
