"""
Management command to evaluate active signals.
Checks if they hit Take Profit or Stop Loss, and updates their status.
Phase 5: Performance Tracking
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from signals.models import Signal, SignalPerformance
from market_data.models import Instrument
from engines.data_fetcher import DataFetcher
import sys

class Command(BaseCommand):
    help = 'Evaluates active signals and updates win/loss status'

    def handle(self, *args, **kwargs):
        Signal.objects.exclude(take_profit_2=None).update(take_profit_2=None, take_profit_3=None)
        active_signals = Signal.objects.filter(status='ACTIVE').select_related('instrument')
        fetcher = DataFetcher()
        processed = 0

        if active_signals.exists():
            # Group signals by symbol to minimize API calls
            signals_by_symbol = {}
            for sig in active_signals:
                sym = sig.instrument.symbol
                if sym not in signals_by_symbol:
                    signals_by_symbol[sym] = []
                signals_by_symbol[sym].append(sig)

            for symbol, signals in signals_by_symbol.items():
                try:
                    # Fetch recent M1 data for immediate real-time TP1 / SL detection
                    df = fetcher.fetch(symbol, timeframe='M1', limit=240)
                    if df is None or len(df) == 0:
                        continue

                    from quant.config import ASSETS
                    from market_data.models import MarketQuoteSpread

                    asset_cfg = ASSETS.get(symbol)
                    cost_bps = asset_cfg.cost_bps if asset_cfg else 3.0

                    live_price = float(df['close'].iloc[-1])

                    # Realistic fill cost components (half-spread, slippage, round-trip commission)
                    live_quote = MarketQuoteSpread.objects.filter(instrument__symbol=symbol).first()
                    if live_quote and live_quote.spread:
                        half_spread = float(live_quote.spread) / 2.0
                    else:
                        half_spread = live_price * (cost_bps * 0.60) / 10000.0

                    slippage = live_price * (cost_bps * 0.30) / 10000.0
                    commission = live_price * (cost_bps * 0.10) / 10000.0

                    for sig in signals:
                        tp1_val = float(sig.take_profit_1)
                        sl_val = float(sig.stop_loss)
                        entry_val = float(sig.entry_price)

                        # Cost-adjusted entry fills at Ask for BUY, Bid for SELL
                        if sig.direction == 'BUY':
                            fill_entry = entry_val + half_spread + slippage
                        else:
                            fill_entry = entry_val - half_spread - slippage

                        initial_risk = abs(fill_entry - sl_val)
                        if initial_risk <= 0:
                            initial_risk = fill_entry * 0.005

                        outcome = None
                        exit_price = None

                        # Walk candles strictly chronologically (oldest to newest)
                        post_signal_df = df[df.index > sig.generated_at].sort_index()

                        for ts, candle in post_signal_df.iterrows():
                            c_high = float(candle['high'])
                            c_low = float(candle['low'])

                            if sig.direction == 'BUY':
                                bid_high = c_high - half_spread
                                bid_low = c_low - half_spread
                                hit_tp = (bid_high >= tp1_val)
                                hit_sl = (bid_low <= sl_val)

                                if hit_tp and hit_sl:
                                    # Conservative rule: Both touched in same bar -> SL triggers first
                                    outcome = 'HIT_SL'
                                    exit_price = sl_val - slippage
                                    break
                                elif hit_sl:
                                    outcome = 'HIT_SL'
                                    exit_price = sl_val - slippage
                                    break
                                elif hit_tp:
                                    outcome = 'HIT_TP'
                                    exit_price = tp1_val - slippage
                                    break

                            elif sig.direction == 'SELL':
                                ask_high = c_high + half_spread
                                ask_low = c_low + half_spread
                                hit_tp = (ask_low <= tp1_val)
                                hit_sl = (ask_high >= sl_val)

                                if hit_tp and hit_sl:
                                    # Conservative rule: Both touched in same bar -> SL triggers first
                                    outcome = 'HIT_SL'
                                    exit_price = sl_val + slippage
                                    break
                                elif hit_sl:
                                    outcome = 'HIT_SL'
                                    exit_price = sl_val + slippage
                                    break
                                elif hit_tp:
                                    outcome = 'HIT_TP'
                                    exit_price = tp1_val + slippage
                                    break

                        # If no historical bar resolved it, check current real-time tick
                        if outcome is None:
                            if sig.direction == 'BUY':
                                cur_bid = live_price - half_spread
                                if cur_bid <= sl_val:
                                    outcome = 'HIT_SL'
                                    exit_price = sl_val - slippage
                                elif cur_bid >= tp1_val:
                                    outcome = 'HIT_TP'
                                    exit_price = tp1_val - slippage
                            elif sig.direction == 'SELL':
                                cur_ask = live_price + half_spread
                                if cur_ask >= sl_val:
                                    outcome = 'HIT_SL'
                                    exit_price = sl_val + slippage
                                elif cur_ask <= tp1_val:
                                    outcome = 'HIT_TP'
                                    exit_price = tp1_val + slippage

                        # Check signal validity expiration
                        if outcome is None and sig.valid_until is not None and timezone.now() > sig.valid_until:
                            outcome = 'EXPIRED'
                            exit_price = (live_price - half_spread - slippage) if sig.direction == 'BUY' else (live_price + half_spread + slippage)

                        if outcome:
                            sig.status = outcome
                            sig.take_profit_2 = None
                            sig.take_profit_3 = None
                            sig.save(update_fields=['status', 'take_profit_2', 'take_profit_3'])

                            # Calculate true realized net PnL and R-multiple after costs
                            total_commission = 2.0 * commission
                            if sig.direction == 'BUY':
                                net_price_change = (exit_price - fill_entry) - total_commission
                            else:
                                net_price_change = (fill_entry - exit_price) - total_commission

                            realized_r = round(float(net_price_change / initial_risk), 3)

                            loss_category = None
                            if outcome == 'HIT_TP':
                                perf_outcome = 'WIN' if realized_r > 0 else 'LOSS'
                            elif outcome == 'HIT_SL':
                                perf_outcome = 'LOSS'
                                if any('News' in w or 'BLACKOUT' in w for w in (sig.warnings or [])):
                                    loss_category = 'NEWS_SHOCK'
                                elif getattr(sig, 'market_regime', '') == 'RANGING':
                                    loss_category = 'WRONG_REGIME'
                                elif any('spread' in str(w).lower() for w in (sig.warnings or [])):
                                    loss_category = 'SPREAD_SLIPPAGE'
                                elif sig.confidence_score < 60:
                                    loss_category = 'INSUFFICIENT_CONFLUENCE'
                                elif any('Structure' in str(w) or 'trap' in str(w).lower() for w in (sig.warnings or [])):
                                    loss_category = 'FALSE_BREAKOUT_TRAP'
                                else:
                                    loss_category = 'POOR_STRUCTURAL_INVALIDATION'
                            else:
                                perf_outcome = 'BREAKEVEN' if abs(realized_r) < 0.05 else ('WIN' if realized_r > 0 else 'LOSS')

                            from decimal import Decimal
                            pip_val = float(sig.instrument.pip_value) if sig.instrument and sig.instrument.pip_value else 0.0001
                            pnl_pips = round(float(net_price_change / pip_val), 1)
                            pnl_percent = round(realized_r * 1.0, 2)  # 1% baseline risk unit

                            SignalPerformance.objects.update_or_create(
                                signal=sig,
                                defaults={
                                    'outcome': perf_outcome,
                                    'actual_exit': Decimal(str(round(float(exit_price), 5))),
                                    'pnl_percent': pnl_percent,
                                    'pnl_r': realized_r,
                                    'pnl_pips': pnl_pips,
                                    'loss_category': loss_category,
                                }
                            )

                            # Immediately close any linked Auto-Trader positions at TP1 / SL
                            try:
                                from accounts.auto_trader import AutoTraderEngine
                                AutoTraderEngine.close_open_trades_for_signal(sig, outcome, exit_price)
                            except Exception:
                                pass

                            # Update PaperTrade simulation record if exists
                            try:
                                from signals.models import PaperTrade
                                paper = PaperTrade.objects.filter(signal=sig).first()
                                if paper and paper.state == 'OPEN':
                                    paper.state = 'CLOSED'
                                    paper.closed_at = timezone.now()
                                    paper.realized_r = pnl_percent
                                    paper.realized_pnl = round(pnl_percent * paper.risk_amount, 2)
                                    paper.exit_reason = outcome
                                    paper.save()
                            except Exception:
                                pass

                            # Dispatch resolution notification
                            try:
                                from signals.notifications import telegram_notifier
                                telegram_notifier.send_signal_outcome(
                                    signal=sig,
                                    outcome=perf_outcome,
                                    pnl_pips=pnl_pips,
                                    exit_price=exit_price or float(sig.entry_price)
                                )
                            except Exception:
                                pass

                            self.stdout.write(self.style.SUCCESS(f"Signal {sig.id} ({symbol}) resolved as {outcome} at {exit_price}"))
                            processed += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error evaluating {symbol}: {e}"))

        # Auto-Trader open position evaluation & closure on TP1/SL
        try:
            from accounts.auto_trader import AutoTraderEngine
            closed_auto = AutoTraderEngine.evaluate_and_close_open_trades()
            if closed_auto:
                self.stdout.write(self.style.SUCCESS(f"Auto-Trader evaluated and closed {len(closed_auto)} positions on TP1/SL."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Auto-Trader evaluation note: {e}"))

        if processed:
            self.stdout.write(self.style.SUCCESS(f"Evaluation complete. Resolved {processed} signals."))
