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

                    live_price = float(df['close'].iloc[-1])

                    for sig in signals:
                        # Check current live price right now + any M1 bars started strictly after sig.generated_at
                        post_signal_df = df[df.index > sig.generated_at]
                        if len(post_signal_df) > 0:
                            high = max(live_price, float(post_signal_df['high'].max()))
                            low = min(live_price, float(post_signal_df['low'].min()))
                        else:
                            high = live_price
                            low = live_price

                        tp1_val = float(sig.take_profit_1)
                        sl_val = float(sig.stop_loss)

                        outcome = None
                        exit_price = None

                        # Single full-position auto-close at TP1 (no waiting for TP2/TP3)
                        if sig.direction == 'BUY':
                            if high >= tp1_val or live_price >= tp1_val:
                                outcome = 'HIT_TP'
                                exit_price = tp1_val
                            elif low <= sl_val or live_price <= sl_val:
                                outcome = 'HIT_SL'
                                exit_price = sl_val
                        elif sig.direction == 'SELL':
                            if low <= tp1_val or live_price <= tp1_val:
                                outcome = 'HIT_TP'
                                exit_price = tp1_val
                            elif high >= sl_val or live_price >= sl_val:
                                outcome = 'HIT_SL'
                                exit_price = sl_val

                        # Check for expiration
                        if outcome is None and sig.valid_until is not None and timezone.now() > sig.valid_until:
                            outcome = 'EXPIRED'
                            exit_price = live_price

                        if outcome:
                            sig.status = outcome
                            sig.take_profit_2 = None
                            sig.take_profit_3 = None
                            sig.save(update_fields=['status', 'take_profit_2', 'take_profit_3'])

                            # Create or update performance record
                            pnl_percent = 0.0
                            perf_outcome = 'BREAKEVEN'
                            loss_category = None
                            if outcome == 'HIT_TP':
                                pnl_percent = float(sig.risk_reward) if sig.risk_reward else 1.50
                                perf_outcome = 'WIN'
                            elif outcome == 'HIT_SL':
                                pnl_percent = -1.0
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

                            from decimal import Decimal
                            pnl_pips = round(float(pnl_percent) * 20.0, 1)
                            SignalPerformance.objects.update_or_create(
                                signal=sig,
                                defaults={
                                    'outcome': perf_outcome,
                                    'actual_exit': Decimal(str(round(float(exit_price or sig.entry_price), 5))),
                                    'pnl_percent': pnl_percent,
                                    'pnl_r': pnl_percent,
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
