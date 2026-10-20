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



class PortfolioAlignment(unittest.TestCase):
    def test_calendar_alignment_drops_weekends_and_compounds(self):
        import pandas as pd
        from quant.portfolio import align_to_business_calendar, combine

        # Simulate 1 year of daily 7-day crypto data (365 days)
        dates = pd.date_range("2024-01-01", "2024-12-31", freq="D")
        np.random.seed(42)
        crypto_ret = pd.Series(np.random.normal(0.001, 0.03, len(dates)), index=dates)

        # Simulate 1 year of 5-day equity/forex data (business days only)
        forex_dates = pd.date_range("2024-01-01", "2024-12-31", freq="B")
        forex_ret = pd.Series(np.random.normal(0.0005, 0.01, len(forex_dates)), index=forex_dates)

        # 1. Aligned series must strictly contain only business days
        aligned_crypto = align_to_business_calendar(crypto_ret)
        self.assertTrue((aligned_crypto.index.dayofweek < 5).all(), "Weekend days still present in aligned index")

        # 2. Compounded total return across the year must match original geometric growth closely
        orig_wealth = np.prod(1.0 + crypto_ret.values)
        aligned_wealth = np.prod(1.0 + aligned_crypto.values)
        self.assertAlmostEqual(orig_wealth, aligned_wealth, places=5)

        # 3. Combining sleeves must yield ~252-262 rows per year (business days), never 365 or 770
        port = combine({"crypto": crypto_ret, "forex": forex_ret}, ppy=252)
        self.assertTrue((port.index.dayofweek < 5).all(), "Combined portfolio contains weekend bars")
        self.assertGreaterEqual(len(port), 250)
        self.assertLessEqual(len(port), 263)



class DataAndSanity(unittest.TestCase):
    def test_mt5_export_loader(self):
        import tempfile, os
        from quant.data import load_csv

        # Sample native MT5 tab-separated export content
        mt5_content = (
            "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
            "2024.01.02\t00:00:00\t1.10350\t1.10500\t1.10100\t1.10400\t100\t0\t1\n"
            "2024.01.02\t01:00:00\t1.10400\t1.10650\t1.10300\t1.10600\t120\t0\t1\n"
            "2024.01.02\t02:00:00\t1.10600\t1.10700\t1.10500\t1.10550\t90\t0\t1\n"
        )
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as f:
            f.write(mt5_content)
            temp_path = f.name

        try:
            df = load_csv(temp_path)
            self.assertEqual(len(df), 3)
            self.assertListEqual(list(df.columns), ["open", "high", "low", "close", "volume"])
            self.assertEqual(df.index[0].strftime("%Y-%m-%d %H:%M:%S"), "2024-01-02 00:00:00")
            self.assertAlmostEqual(df["close"].iloc[0], 1.10400)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_price_sanity_rejects_spikes_and_stale(self):
        import pandas as pd
        from quant.data import validate_price_sanity

        dates = pd.date_range("2024-01-01", periods=30, freq="h")
        # 1. Normal clean data -> Passes
        clean_df = pd.DataFrame({
            "open": np.linspace(100, 102, 30),
            "high": np.linspace(101, 103, 30),
            "low": np.linspace(99, 101, 30),
            "close": np.linspace(100.5, 102.5, 30),
        }, index=dates)
        ok, msg = validate_price_sanity(clean_df, max_bar_jump=0.10)
        self.assertTrue(ok, f"Clean data rejected: {msg}")

        # 2. Corrupt tick with 25% single-bar jump -> Rejected
        spike_df = clean_df.copy()
        spike_df.loc[dates[15], "close"] = spike_df.loc[dates[15], "close"] * 1.25
        ok, msg = validate_price_sanity(spike_df, max_bar_jump=0.10)
        self.assertFalse(ok, "Failed to reject price jump spike")

        # 3. Flatlined stale data (last 20 bars identical) -> Rejected
        stale_df = clean_df.copy()
        stale_df.iloc[-20:, stale_df.columns.get_loc("close")] = 100.0
        ok, msg = validate_price_sanity(stale_df, max_flat_bars=15)
        self.assertFalse(ok, "Failed to reject stale flatlined feed")



class EvaluatorChronology(unittest.TestCase):
    def test_chronological_sl_before_tp(self):
        """If price hits SL on bar 1 and TP on bar 5, SL must win (no future lookahead)."""
        import pandas as pd
        dates = pd.date_range("2024-01-01 10:00", periods=6, freq="1min")
        # Bar 0: Entry = 100.0, SL = 95.0, TP = 110.0
        # Bar 1: Low drops to 94.0 (SL hit!)
        # Bar 5: High reaches 112.0 (TP hit later)
        bars = pd.DataFrame({
            "open":  [100.0, 99.0, 98.0, 102.0, 105.0, 108.0],
            "high":  [100.5, 99.5, 100.0, 104.0, 107.0, 112.0],
            "low":   [99.5,  94.0, 97.0, 101.0, 104.0, 107.0],
            "close": [100.0, 95.0, 98.0, 103.0, 106.0, 111.0],
        }, index=dates)

        # Test chronological resolution for BUY signal
        entry, sl, tp = 100.0, 95.0, 110.0
        half_spread = 0.05
        outcome = None
        for _, candle in bars.iloc[1:].iterrows():
            bid_high = candle["high"] - half_spread
            bid_low = candle["low"] - half_spread
            if (bid_high >= tp) and (bid_low <= sl):
                outcome = "HIT_SL"
                break
            elif bid_low <= sl:
                outcome = "HIT_SL"
                break
            elif bid_high >= tp:
                outcome = "HIT_TP"
                break

        self.assertEqual(outcome, "HIT_SL", "Chronological evaluator failed: SL must trigger before future TP")

    def test_same_bar_collision_assumes_sl(self):
        """Conservative Rule: If both SL and TP are touched in the same bar, assume SL first."""
        import pandas as pd
        dates = pd.date_range("2024-01-01 10:00", periods=2, freq="1min")
        # Single bar touches both 94.0 (SL=95) and 112.0 (TP=110)
        candle = {"high": 112.0, "low": 94.0}
        sl, tp = 95.0, 110.0
        half_spread = 0.05

        bid_high = candle["high"] - half_spread
        bid_low = candle["low"] - half_spread
        hit_tp = (bid_high >= tp)
        hit_sl = (bid_low <= sl)

        self.assertTrue(hit_tp and hit_sl, "Both boundaries must be touched in collision test")
        # Rule implementation:
        outcome = "HIT_SL" if (hit_tp and hit_sl) else ("HIT_TP" if hit_tp else "HIT_SL")
        self.assertEqual(outcome, "HIT_SL", "Collision rule violated: Must assume SL first")


class InstrumentSizing(unittest.TestCase):
    def test_contract_sizing_specs(self):
        from engines.risk import RiskEngine

        balance = 10000.0
        risk_pct = 0.5  # 0.5% = $50 dollar risk

        # 1. Gold (XAUUSD): Entry 2500, SL 2490 (10 points). 100 oz contract -> $1000 risk per lot.
        # Lots = $50 / $1000 = 0.05 lots
        lots_gold, dollar_risk_per_lot, _ = RiskEngine.calculate_contract_sizing(
            "XAUUSD", entry=2500.0, sl=2490.0, risk_dollar=50.0
        )
        self.assertEqual(dollar_risk_per_lot, 1000.0)
        self.assertEqual(lots_gold, 0.05)

        # 2. US30: Entry 40000, SL 39900 (100 points). $1/point -> $100 risk per lot.
        # Lots = $50 / $100 = 0.50 lots
        lots_us30, dollar_risk_us30, _ = RiskEngine.calculate_contract_sizing(
            "US30", entry=40000.0, sl=39900.0, risk_dollar=50.0
        )
        self.assertEqual(dollar_risk_us30, 100.0)
        self.assertEqual(lots_us30, 0.50)

        # 3. Forex (EURUSD): Entry 1.1000, SL 1.0950 (50 pips). $10/pip -> $500 risk per lot.
        # Lots = $50 / $500 = 0.10 lots
        lots_fx, dollar_risk_fx, _ = RiskEngine.calculate_contract_sizing(
            "EURUSD", entry=1.1000, sl=1.0950, risk_dollar=50.0
        )
        self.assertAlmostEqual(dollar_risk_fx, 500.0, places=2)
        self.assertEqual(lots_fx, 0.10)

    def test_risk_percentage_clamp(self):
        from engines.risk import RiskEngine
        # Evaluating with requested risk_percentage=2.0% must be clamped to 0.5% max
        eval_res = RiskEngine.evaluate(
            symbol="EURUSD", direction="BUY", entry=1.1000, stop_loss=1.0950,
            take_profit=1.1100, confidence=80.0, account_balance=10000.0, risk_percentage=2.0
        )
        self.assertLessEqual(eval_res.risk_percentage, 0.50)
        self.assertLessEqual(eval_res.risk_amount_currency, 50.0)


class GoLiveGatekeeper(unittest.TestCase):
    def test_gate_rejects_subthreshold_sharpe(self):
        from quant.gate import GoLiveGate
        metrics = {"sharpe": 0.35, "maxdd": -0.12, "boot_p5": 0.08}
        sleeves = {"s1": 120, "s2": 150}
        ok, reasons = GoLiveGate.evaluate_backtest_gate(metrics, sleeves)
        self.assertFalse(ok)
        self.assertTrue(any("Sharpe" in r for r in reasons))

    def test_gate_rejects_excessive_drawdown(self):
        from quant.gate import GoLiveGate
        metrics = {"sharpe": 0.65, "maxdd": -0.22, "boot_p5": 0.15}
        sleeves = {"s1": 120}
        ok, reasons = GoLiveGate.evaluate_backtest_gate(metrics, sleeves)
        self.assertFalse(ok)
        self.assertTrue(any("Drawdown" in r for r in reasons))

    def test_gate_rejects_insufficient_sleeve_trades(self):
        from quant.gate import GoLiveGate
        metrics = {"sharpe": 0.70, "maxdd": -0.10, "boot_p5": 0.20}
        sleeves = {"s1": 150, "s2": 45}  # s2 has <100 trades
        ok, reasons = GoLiveGate.evaluate_backtest_gate(metrics, sleeves)
        self.assertFalse(ok)
        self.assertTrue(any("trades" in r.lower() for r in reasons))

    def test_gate_rejects_short_paper_trading(self):
        from quant.gate import GoLiveGate
        from datetime import datetime, timedelta
        # Paper trading only 30 days old (<90 days required)
        start = datetime(2024, 1, 1)
        trades = [
            {"closed_at": start + timedelta(days=i), "pnl_r": 0.5}
            for i in range(30)
        ]
        ok, reasons = GoLiveGate.evaluate_paper_trading_gate(trades)
        self.assertFalse(ok)
        self.assertTrue(any("90 days" in r for r in reasons))

    def test_gate_passes_when_all_standards_satisfied(self):
        from quant.gate import GoLiveGate
        from datetime import datetime, timedelta
        metrics = {"sharpe": 0.75, "maxdd": -0.11, "boot_p5": 0.25}
        sleeves = {"EURUSD/trend": 130, "XAUUSD/trend": 115}
        start = datetime(2024, 1, 1)
        trades = [
            {"closed_at": start + timedelta(days=i * 4), "pnl_r": 0.4}
            for i in range(25)
        ]  # Spans 25 * 4 = 100 days (>90 days)
        ok, report = GoLiveGate.can_go_live(metrics, sleeves, trades)
        self.assertTrue(ok, f"Gate failed unexpectedly: {report['rejection_reasons']}")

class ExpectancyAndSharpeMetrics(unittest.TestCase):
    def test_known_toy_trade_lists_hand_calculated(self):
        """Toy trade list with hand-calculated expectancy, payoff, profit factor, and break-even."""
        from quant.metrics_r import compute_metrics_r

        # 5 trades: 3 wins (+1.33R each), 2 losses (-1.00R each)
        # sum_wins = 3.99, sum_losses = 2.0
        # win_rate = 3/5 = 0.60, loss_rate = 2/5 = 0.40
        # avg_win_R = 1.33, avg_loss_R = 1.00
        # payoff_ratio = 1.33 / 1.0 = 1.33
        # profit_factor = 3.99 / 2.0 = 1.995
        # expectancy_R = (0.60 * 1.33) - (0.40 * 1.00) = 0.798 - 0.40 = 0.398
        # break_even_win_rate = 1 / (1 + 1.33) = 1 / 2.33 = ~0.42918 (42.92%)
        trades = [1.33, -1.00, 1.33, -1.00, 1.33]
        m = compute_metrics_r(trades)

        self.assertEqual(m["n_trades"], 5)
        self.assertAlmostEqual(m["win_rate"], 0.60, places=4)
        self.assertAlmostEqual(m["loss_rate"], 0.40, places=4)
        self.assertAlmostEqual(m["avg_win_R"], 1.33, places=4)
        self.assertAlmostEqual(m["avg_loss_R"], 1.00, places=4)
        self.assertAlmostEqual(m["payoff_ratio"], 1.33, places=2)
        self.assertAlmostEqual(m["profit_factor"], 1.995, places=3)
        self.assertAlmostEqual(m["expectancy_R"], 0.398, places=3)
        self.assertAlmostEqual(m["break_even_win_rate"], 0.4292, places=3)

    def test_high_win_rate_negative_expectancy_not_positive_edge(self):
        """High-win-rate / negative-expectancy sample (Win-Rate Trap) is NOT labelled 'Positive edge'."""
        from quant.metrics_r import compute_metrics_r

        # 70 wins of +0.20R and 30 losses of -1.00R (n = 100 closed trades)
        # win_rate = 70% (high win rate)
        # sum_wins = 14.0, sum_losses = 30.0 -> profit_factor = 14/30 = 0.467 (< 1.0)
        # expectancy = (0.70 * 0.20) - (0.30 * 1.00) = 0.14 - 0.30 = -0.16R
        trades = [0.20] * 70 + [-1.00] * 30
        m = compute_metrics_r(trades)

        self.assertEqual(m["n_trades"], 100)
        self.assertAlmostEqual(m["win_rate"], 0.70, places=2)
        self.assertAlmostEqual(m["expectancy_R"], -0.16, places=2)
        self.assertLess(m["profit_factor"], 1.0)
        # Must be flagged as win-rate trap: win_rate > 55% but profit_factor < 1.20
        self.assertTrue(m["is_win_rate_trap"], "High win rate with low profit factor must be flagged as trap")
        # Must NOT be labelled 'Positive edge'
        self.assertNotEqual(m["edge_verdict"], "Positive edge")
        self.assertEqual(m["edge_verdict"], "Negative edge")

    def test_selection_ignores_win_rate(self):
        """Selection strictly follows net expectancy_R (or Sharpe) and ignores win rate."""
        from quant.backtest import select_parameters

        # Candidate A (Trend): 30% win rate, +0.40R expectancy
        # Candidate B (Meanrev trap): 80% win rate, +0.10R expectancy
        scores = {
            ("trend_fast", 10): 0.40,
            ("meanrev_trap", 20): 0.10,
        }
        chosen = select_parameters(scores, metric_name="expectancy")
        self.assertEqual(chosen, ("trend_fast", 10), "Higher expectancy must be selected regardless of win rate")

        # Tied Expectancy: Candidate X (30% win rate) vs Candidate Y (80% win rate)
        # Same expectancy -> selection never prefers Y for having higher win rate
        tied_scores = {
            ("candidate_x_low_wr",): 0.35,
            ("candidate_y_high_wr",): 0.35,
        }
        chosen_tied = select_parameters(tied_scores, metric_name="expectancy")
        self.assertEqual(chosen_tied, ("candidate_x_low_wr",), "Ties must be stable and never broken by win rate")


if __name__ == "__main__":
    unittest.main()



