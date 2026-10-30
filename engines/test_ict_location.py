from datetime import timedelta

import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from engines.ict_location import evaluate_ict_location


def frame(start, periods, minutes, seed):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.25, periods))
    opened = np.r_[close[0], close[:-1]]
    high = np.maximum(opened, close) + rng.uniform(0.01, 0.15, periods)
    low = np.minimum(opened, close) - rng.uniform(0.01, 0.15, periods)
    return pd.DataFrame(
        {'open': opened, 'high': high, 'low': low, 'close': close},
        index=pd.date_range(start, periods=periods, freq=f'{minutes}min', tz='UTC'),
    )


class ICTLocationTests(SimpleTestCase):
    def setUp(self):
        start = pd.Timestamp('2024-01-01T00:00:00Z')
        self.frames = {
            'M15': frame(start, 1000, 15, 1),
            'H1': frame(start, 300, 60, 2),
            'H4': frame(start, 100, 240, 3),
        }

    def test_rejects_outside_killzone(self):
        result = evaluate_ict_location(self.frames, 'XAUUSD', as_of=pd.Timestamp('2024-01-05T05:00:00Z'))
        self.assertFalse(result.allowed)
        self.assertIn('Outside M15 London/NY killzones', result.reasons)

    def test_future_candles_cannot_change_prior_decision(self):
        as_of = pd.Timestamp('2024-01-10T09:00:00Z')
        baseline = evaluate_ict_location(self.frames, 'XAUUSD', as_of=as_of).to_dict()
        future = {key: value.copy() for key, value in self.frames.items()}
        for key, value in future.items():
            step = {'M15': 15, 'H1': 60, 'H4': 240}[key]
            last = value.index[-1]
            extra_index = pd.date_range(last + pd.Timedelta(minutes=step), periods=20, freq=f'{step}min', tz='UTC')
            future_values = pd.DataFrame({'open': 9999., 'high': 10000., 'low': 9998., 'close': 9999.}, index=extra_index)
            future[key] = pd.concat([value, future_values])
        self.assertEqual(baseline, evaluate_ict_location(future, 'XAUUSD', as_of=as_of).to_dict())

    def test_requires_supported_asset(self):
        result = evaluate_ict_location(self.frames, 'BTCUSD', as_of=pd.Timestamp('2024-01-10T09:00:00Z'))
        self.assertFalse(result.allowed)
        self.assertIn('Outside approved assets', result.reasons)
