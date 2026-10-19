"""Sanity tests for the machinery. Run from project root:  python -m unittest quant.tests.test_quant -v"""
import unittest
import numpy as np

from quant import synthetic as S
from quant.strategies import REGISTRY
from quant.backtest import sleeve_returns, walk_forward, metrics

PPY = 252


class Causality(unittest.TestCase):
    def test_signals_ignore_the_future(self):
        df = S.regime_trend(1200, seed=3)
        k = 800
        for name, (fn, grid) in REGISTRY.items():
            params = {key: vals[0] for key, vals in grid.items()}
            full = fn(df, **params).iloc[:k]
            part = fn(df.iloc[:k], **params)
            np.testing.assert_array_equal(full.to_numpy(), part.to_numpy(), err_msg=name)

    def test_positions_ignore_the_future(self):
        df = S.regime_trend(1200, seed=4)
        fn, grid = REGISTRY["trend"]
        p = {k: v[0] for k, v in grid.items()}
        k = 900
        a = sleeve_returns(df, fn(df, **p), 2.0, PPY)["pos"].iloc[:k]
        b = sleeve_returns(df.iloc[:k], fn(df.iloc[:k], **p), 2.0, PPY)["pos"]
        np.testing.assert_allclose(a.to_numpy(), b.to_numpy())


class NullAndSignal(unittest.TestCase):
    def _mean_oos_sharpe(self, maker, seeds, strats=None, **kw):
        vals = []
        for s in seeds:
            df = maker(3000, seed=s, **kw)
            for st in (strats or REGISTRY):
                oos, _, _ = walk_forward(df, st, 2.0, PPY, 3 * PPY, PPY)
                vals.append(metrics(oos["ret"], PPY)["sharpe"])
        return float(np.mean(vals))

    def test_random_walk_has_no_edge(self):
        m = self._mean_oos_sharpe(S.null_walk, range(8))
        print(f"\n  null random-walk mean OOS Sharpe = {m:+.2f}  (must be ~0 or negative)")
        self.assertLess(m, 0.25)       # a leaky backtester would show a large positive number here

    def test_trending_market_is_detected(self):
        trend = self._mean_oos_sharpe(S.regime_trend, range(5), ["trend", "donchian"], drift=0.0012)
        mrev = self._mean_oos_sharpe(S.regime_trend, range(5), ["meanrev"], drift=0.0012)
        print(f"\n  trending market: trend-following Sharpe = {trend:+.2f}, mean-reversion = {mrev:+.2f}")
        self.assertGreater(trend, 0.4)   # trend-followers must find the planted edge
        self.assertLess(mrev, trend)     # and mean-reversion must NOT (wrong tool for this market)


if __name__ == "__main__":
    unittest.main()
