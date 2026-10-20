"""
Backtesting & Validation Engine — Phase 11
Implements requirements from TradeSense Pro Master Architecture Section 26 & 27:
- Historical bar-by-bar replay simulation
- Spread, slippage, and transaction cost accounting
- High-impact news event blackout awareness
- Dynamic ATR and structural SL / TP target validation
- Equity curve tracking & drawdown calculation
- Performance metrics: Win Rate, Profit Factor, Max Drawdown %, Expectancy (R)
- Performance by regime (Trend, Range, Volatile)
- Replay only; walk-forward validation is provided by the separate quant runner
- Persistence to BacktestRun database model
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd

from django.utils import timezone as dj_tz
from market_data.models import Instrument, OHLCV
from signals.models import BacktestRun, EconomicEvent
from engines.unified import UnifiedSignalEngine

logger = logging.getLogger(__name__)


class BacktestSimulator:
    """
    Simulates historical trading execution for TradeSense Pro signals.
    """

    def __init__(
        self,
        instrument: Instrument,
        timeframe: str = 'H1',
        initial_capital: float = 10000.0,
        risk_per_trade_pct: float = 1.0,
        spread_pips: float = 1.5,
        slippage_pips: float = 0.5,
        respect_news_blackout: bool = True,
        custom_weights: Optional[Dict[str, float]] = None,
    ):
        self.instrument = instrument
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.capital = initial_capital
        if not np.isfinite(float(risk_per_trade_pct)) or float(risk_per_trade_pct) <= 0:
            raise ValueError("risk_per_trade_pct must be a finite positive number")
        if not np.isfinite(float(spread_pips)) or float(spread_pips) < 0:
            raise ValueError("spread_pips must be a finite non-negative number")
        if not np.isfinite(float(slippage_pips)) or float(slippage_pips) < 0:
            raise ValueError("slippage_pips must be a finite non-negative number")
        self.risk_per_trade_pct = min(float(risk_per_trade_pct), 0.5)
        self.spread_pips = float(spread_pips)
        self.slippage_pips = float(slippage_pips)
        self.pip_value = float(instrument.pip_value) if instrument.pip_value else 0.0001
        self.respect_news_blackout = respect_news_blackout
        self.custom_weights = custom_weights

    def run(
        self,
        df: pd.DataFrame,
        window_size: int = 60,
        step: int = 1,
        walk_forward_split: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Executes a historical replay backtest over the provided OHLCV DataFrame.
        """
        if walk_forward_split is not None:
            raise ValueError("walk_forward_split is not implemented by this replay engine; use the quant walk-forward runner")
        if step < 1:
            raise ValueError("step must be a positive integer")
        if window_size < 10:
            raise ValueError("window_size must be at least 10 bars")
        if len(df) < window_size + 10:
            raise ValueError(f"Insufficient historical data: {len(df)} candles provided, need at least {window_size + 10}")

        # Ensure datetime and sorted
        df = df.copy()
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp').reset_index(drop=True)
        elif not isinstance(df.index, pd.DatetimeIndex):
            df = df.sort_index().reset_index(drop=True)

        total_bars = len(df)
        trade_logs: List[Dict[str, Any]] = []
        equity_curve: List[Dict[str, Any]] = []
        active_trade: Optional[Dict[str, Any]] = None

        peak_capital = self.initial_capital
        max_drawdown_amount = 0.0
        max_drawdown_pct = 0.0

        # Preload high-impact news if applicable
        blackout_events = []
        if self.respect_news_blackout:
            currency = self.instrument.quote or 'USD'
            base_curr = self.instrument.base or ''
            try:
                blackout_events = list(EconomicEvent.objects.filter(
                    impact='HIGH',
                    currency__in=[currency, base_curr]
                ).values_list('event_time', 'blackout_mins_before', 'blackout_mins_after'))
            except Exception:
                blackout_events = []

        # Historical bar-by-bar replay loop
        for i in range(window_size, total_bars):
            trade_closed_this_bar = False
            current_bar = df.iloc[i]
            bar_timestamp = current_bar.get('timestamp', None)
            high_price = float(current_bar['high'])
            low_price = float(current_bar['low'])
            close_price = float(current_bar['close'])
            open_price = float(current_bar['open'])

            # 1. Evaluate Active Trade if one is open
            if active_trade is not None:
                outcome = None
                exit_price = None
                pnl_pips = 0.0
                r_multiple = 0.0

                direction = active_trade['direction']
                entry_price = active_trade['entry_price']
                sl_price = active_trade['stop_loss']
                tp_price = active_trade['take_profit_1']
                initial_risk_pips = active_trade['risk_pips']
                exit_cost_pips = (self.spread_pips / 2.0) + self.slippage_pips

                if direction == 'BUY':
                    # Check if SL hit first (worst-case: low hit SL before high hit TP)
                    if low_price <= sl_price:
                        outcome = 'LOSS'
                        exit_price = sl_price - (exit_cost_pips * self.pip_value)
                        pnl_pips = (exit_price - entry_price) / self.pip_value
                        r_multiple = pnl_pips / max(initial_risk_pips, 1e-9)
                    elif high_price >= tp_price:
                        outcome = 'WIN'
                        exit_price = tp_price - (exit_cost_pips * self.pip_value)
                        pnl_pips = (exit_price - entry_price) / self.pip_value
                        r_multiple = pnl_pips / max(initial_risk_pips, 1e-9)
                elif direction == 'SELL':
                    if high_price >= sl_price:
                        outcome = 'LOSS'
                        exit_price = sl_price + (exit_cost_pips * self.pip_value)
                        pnl_pips = (entry_price - exit_price) / self.pip_value
                        r_multiple = pnl_pips / max(initial_risk_pips, 1e-9)
                    elif low_price <= tp_price:
                        outcome = 'WIN'
                        exit_price = tp_price + (exit_cost_pips * self.pip_value)
                        pnl_pips = (entry_price - exit_price) / self.pip_value
                        r_multiple = pnl_pips / max(initial_risk_pips, 1e-9)

                # Time expiration check (e.g., maximum 30 bars hold)
                bars_held = i - active_trade['entry_bar']
                if outcome is None and bars_held >= 30:
                    outcome = 'EXPIRED'
                    exit_price = close_price
                    if direction == 'BUY':
                        exit_price -= exit_cost_pips * self.pip_value
                        pnl_pips = (exit_price - entry_price) / self.pip_value
                    else:
                        exit_price += exit_cost_pips * self.pip_value
                        pnl_pips = (entry_price - exit_price) / self.pip_value
                    r_multiple = pnl_pips / max(initial_risk_pips, 1e-9)

                if outcome is not None:
                    # Finalize trade
                    # Account risk amount
                    risk_amount = active_trade['risk_amount']
                    profit_loss = r_multiple * risk_amount

                    self.capital += profit_loss
                    active_trade['exit_bar'] = i
                    active_trade['exit_timestamp'] = str(bar_timestamp)
                    active_trade['exit_price'] = round(exit_price, 5)
                    active_trade['outcome'] = outcome
                    active_trade['pnl_pips'] = round(pnl_pips, 1)
                    active_trade['pnl_amount'] = round(profit_loss, 2)
                    active_trade['r_multiple'] = round(r_multiple, 2)
                    active_trade['bars_held'] = bars_held

                    trade_logs.append(active_trade)
                    active_trade = None
                    trade_closed_this_bar = True

                    # Drawdown tracking
                    if self.capital > peak_capital:
                        peak_capital = self.capital
                    dd_amount = peak_capital - self.capital
                    dd_pct = (dd_amount / peak_capital) * 100.0 if peak_capital > 0 else 0.0
                    if dd_pct > max_drawdown_pct:
                        max_drawdown_pct = dd_pct
                        max_drawdown_amount = dd_amount


            # 2. Check News Blackout if enabled
            in_blackout = False
            if self.respect_news_blackout and bar_timestamp is not None and blackout_events:
                for evt_time, b_before, b_after in blackout_events:
                    if hasattr(evt_time, 'timestamp') and hasattr(bar_timestamp, 'timestamp'):
                        t_diff = abs((bar_timestamp - evt_time).total_seconds()) / 60.0
                        if t_diff <= max(b_before, b_after):
                            in_blackout = True
                            break
            # 3. If no active trade, generate signal on historical slice
            if active_trade is None and not trade_closed_this_bar and not in_blackout and (i % step == 0):
                history_slice = df.iloc[max(0, i - window_size):i].copy()
                
                try:
                    engine = UnifiedSignalEngine(
                        df=history_slice,
                        symbol=self.instrument.symbol,
                        timeframe=self.timeframe
                    )
                    # Apply custom engine weights if provided
                    if self.custom_weights:
                        engine.weights.update(self.custom_weights)

                    signal = engine.generate_signal()

                    # Only execute high-confidence tradeable signals
                    if signal.direction in ['BUY', 'SELL'] and signal.confidence >= 55.0 and signal.is_trade_allowed:
                        # Trade at this bar's open; the signal only used bars that
                        # had closed before it. Do not backfill at the prior close.
                        cost_pips = (self.spread_pips / 2.0) + self.slippage_pips
                        raw_entry = open_price
                        stop_price = float(signal.stop_loss)
                        target_price = float(signal.take_profit_1)
                        if signal.direction == 'BUY' and not (stop_price < raw_entry < target_price):
                            equity_curve.append({'bar': i, 'timestamp': str(bar_timestamp), 'equity': round(self.capital, 2), 'drawdown_pct': round(max_drawdown_pct, 2)})
                            continue
                        if signal.direction == 'SELL' and not (target_price < raw_entry < stop_price):
                            equity_curve.append({'bar': i, 'timestamp': str(bar_timestamp), 'equity': round(self.capital, 2), 'drawdown_pct': round(max_drawdown_pct, 2)})
                            continue
                        if signal.direction == 'BUY':
                            adjusted_entry = raw_entry + (cost_pips * self.pip_value)
                        else:
                            adjusted_entry = raw_entry - (cost_pips * self.pip_value)

                        initial_risk_pips = (abs(adjusted_entry - stop_price) / self.pip_value) + cost_pips
                        risk_amount = self.capital * (self.risk_per_trade_pct / 100.0)

                        active_trade = {
                            'trade_id': len(trade_logs) + 1,
                            'entry_bar': i,
                            'entry_timestamp': str(bar_timestamp),
                            'symbol': self.instrument.symbol,
                            'direction': signal.direction,
                            'confidence': signal.confidence,
                            'entry_price': round(adjusted_entry, 5),
                            'signal_reference_entry': round(float(signal.entry), 5),
                            'stop_loss': round(stop_price, 5),
                            'take_profit_1': round(target_price, 5),
                            'risk_reward': round(float(signal.risk_reward), 2),
                            'risk_pips': initial_risk_pips,
                            'risk_amount': risk_amount,
                            'engine_scores': signal.to_dict().get('engine_scores', {}),
                        }
                except Exception as e:
                    logger.debug(f"Backtest step {i} analysis error: {e}")
                    equity_curve.append({'bar': i, 'timestamp': str(bar_timestamp), 'equity': round(self.capital, 2), 'drawdown_pct': round(max_drawdown_pct, 2)})
                    continue

            # Mark open risk to market every bar, including adverse movement
            # before the stop closes. This feeds drawdown and the equity series.
            mark_equity = self.capital
            if active_trade is not None:
                exit_cost_pips = (self.spread_pips / 2.0) + self.slippage_pips
                if active_trade['direction'] == 'BUY':
                    mark_exit = close_price - exit_cost_pips * self.pip_value
                    mark_pips = (mark_exit - active_trade['entry_price']) / self.pip_value
                else:
                    mark_exit = close_price + exit_cost_pips * self.pip_value
                    mark_pips = (active_trade['entry_price'] - mark_exit) / self.pip_value
                mark_r = mark_pips / max(active_trade['risk_pips'], 1e-9)
                mark_equity += mark_r * active_trade['risk_amount']
            peak_capital = max(peak_capital, mark_equity)
            dd_amount = peak_capital - mark_equity
            dd_pct = (dd_amount / peak_capital) * 100.0 if peak_capital > 0 else 0.0
            max_drawdown_amount = max(max_drawdown_amount, dd_amount)
            max_drawdown_pct = max(max_drawdown_pct, dd_pct)
            equity_curve.append({
                'bar': i,
                'timestamp': str(bar_timestamp) if bar_timestamp is not None else str(df.index[i]),
                'equity': round(mark_equity, 2),
                'drawdown_pct': round(dd_pct, 2),
            })

        # Liquidate any still-open position at the final available close so the
        # reported sample cannot silently omit adverse or unfinished trades.
        if active_trade is not None:
            last_bar = df.iloc[-1]
            final_close = float(last_bar['close'])
            exit_cost_pips = (self.spread_pips / 2.0) + self.slippage_pips
            if active_trade['direction'] == 'BUY':
                exit_price = final_close - exit_cost_pips * self.pip_value
                pnl_pips = (exit_price - active_trade['entry_price']) / self.pip_value
            else:
                exit_price = final_close + exit_cost_pips * self.pip_value
                pnl_pips = (active_trade['entry_price'] - exit_price) / self.pip_value
            r_multiple = pnl_pips / max(active_trade['risk_pips'], 1e-9)
            risk_amount = active_trade['risk_amount']
            profit_loss = r_multiple * risk_amount
            self.capital += profit_loss
            active_trade.update({
                'exit_bar': total_bars - 1,
                'exit_timestamp': str(last_bar['timestamp']) if 'timestamp' in df.columns else str(df.index[-1]),
                'exit_price': round(exit_price, 5),
                'outcome': 'EXPIRED',
                'pnl_pips': round(pnl_pips, 1),
                'pnl_amount': round(profit_loss, 2),
                'r_multiple': round(r_multiple, 2),
                'bars_held': total_bars - 1 - active_trade['entry_bar'],
            })
            trade_logs.append(active_trade)
            peak_capital = max(peak_capital, self.capital)
            dd_pct = ((peak_capital - self.capital) / peak_capital) * 100.0 if peak_capital > 0 else 0.0
            max_drawdown_pct = max(max_drawdown_pct, dd_pct)
            max_drawdown_amount = max(max_drawdown_amount, peak_capital - self.capital)
            equity_curve.append({
                'bar': total_bars - 1,
                'timestamp': str(last_bar['timestamp']) if 'timestamp' in df.columns else str(df.index[-1]),
                'equity': round(self.capital, 2),
                'drawdown_pct': round(dd_pct, 2),
            })

        # Compile final backtest metrics
        total_trades = len(trade_logs)
        winning_trades = sum(1 for t in trade_logs if t['outcome'] == 'WIN')
        losing_trades = sum(1 for t in trade_logs if t['outcome'] == 'LOSS')
        expired_trades = sum(1 for t in trade_logs if t['outcome'] == 'EXPIRED')

        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profit = sum(t['pnl_amount'] for t in trade_logs if t['pnl_amount'] > 0)
        gross_loss = abs(sum(t['pnl_amount'] for t in trade_logs if t['pnl_amount'] < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        r_multiples = [t['r_multiple'] for t in trade_logs]
        average_r = float(np.mean(r_multiples)) if r_multiples else 0.0
        expectancy_r = float(np.mean(r_multiples)) if r_multiples else 0.0

        # Trade-level observations have irregular durations, so they do not
        # support a valid annualized Sharpe ratio. Keep this metric unavailable.
        if 'timestamp' in df.columns:
            start_timestamp, end_timestamp = df.iloc[window_size]['timestamp'], df.iloc[-1]['timestamp']
        elif isinstance(df.index, pd.DatetimeIndex):
            start_timestamp, end_timestamp = df.index[window_size], df.index[-1]
        else:
            start_timestamp, end_timestamp = None, None

        results = {
            'instrument': self.instrument.symbol,
            'timeframe': self.timeframe,
            'start_date': str(start_timestamp) if start_timestamp is not None else None,
            'end_date': str(end_timestamp) if end_timestamp is not None else None,
            'initial_capital': self.initial_capital,
            'final_capital': round(self.capital, 2),
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'expired_trades': expired_trades,
            'win_rate_pct': round(win_rate, 2),
            'profit_factor': round(profit_factor, 2),
            'max_drawdown_pct': round(max_drawdown_pct, 2),
            'average_r': round(average_r, 2),
            'expectancy_r': round(expectancy_r, 2),
            'sharpe_ratio': None,
            'spread_slippage_pips': round(self.spread_pips + (2.0 * self.slippage_pips), 2),
            'limitations': [
                'REPLAY only; not walk-forward/out-of-sample',
                'Sharpe omitted because observations are irregular trade-level samples',
            ],
            'trade_logs': trade_logs,
            'equity_curve': equity_curve,
        }

        return results

    def save_run(self, results: Dict[str, Any]) -> BacktestRun:
        """
        Persists backtest results to the BacktestRun database model.
        """
        run_id = f"BT-{self.instrument.symbol}-{self.timeframe}-{uuid.uuid4().hex[:8].upper()}"

        if not results.get('start_date') or not results.get('end_date'):
            raise ValueError("Backtest results lack source timestamps; refusing to persist fabricated dates")
        start_dt = pd.Timestamp(results['start_date']).to_pydatetime()
        end_dt = pd.Timestamp(results['end_date']).to_pydatetime()
        if start_dt.tzinfo is None:
            start_dt = dj_tz.make_aware(start_dt, timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = dj_tz.make_aware(end_dt, timezone.utc)

        run = BacktestRun.objects.create(
            run_id=run_id,
            instrument=self.instrument,
            timeframe=self.timeframe,
            start_date=start_dt,
            end_date=end_dt,
            initial_capital=results['initial_capital'],
            final_capital=results['final_capital'],
            total_trades=results['total_trades'],
            winning_trades=results['winning_trades'],
            losing_trades=results['losing_trades'],
            win_rate_pct=results['win_rate_pct'],
            profit_factor=results['profit_factor'],
            max_drawdown_pct=results['max_drawdown_pct'],
            expectancy_r=results['expectancy_r'],
            average_r=results['average_r'],
            sharpe_ratio=results.get('sharpe_ratio'),
            limitations=results.get('limitations', []),
            spread_slippage_pips=results['spread_slippage_pips'],
            engine_weights=self.custom_weights or {},
            equity_curve=results['equity_curve'],
            trade_logs=results['trade_logs'][:100], # Keep last 100 in DB
        )
        return run
