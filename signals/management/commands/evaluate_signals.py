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
        active_signals = Signal.objects.filter(status='ACTIVE')
        if not active_signals.exists():
            self.stdout.write(self.style.SUCCESS("No active signals to evaluate."))
            return

        self.stdout.write(f"Found {active_signals.count()} active signals. Evaluating...")
        
        fetcher = DataFetcher()
        processed = 0

        # Group signals by symbol to minimize API calls
        signals_by_symbol = {}
        for sig in active_signals:
            sym = sig.instrument.symbol
            if sym not in signals_by_symbol:
                signals_by_symbol[sym] = []
            signals_by_symbol[sym].append(sig)

        for symbol, signals in signals_by_symbol.items():
            try:
                # Fetch recent M5 data to get accurate high/lows since signal generation
                # In production, we'd fetch tick data, but M5 works for this simulation
                df = fetcher.fetch(symbol, timeframe='M5', limit=1500)
                if df is None or len(df) == 0:
                    self.stdout.write(self.style.WARNING(f"Could not fetch data for {symbol}"))
                    continue

                for sig in signals:
                    # Filter data to only look at candles AFTER the signal was created
                    # Note: Using naive comparison for simplicity if timezones don't match, 
                    # but pandas tz-aware is better.
                    post_signal_df = df[df.index > sig.generated_at]
                    
                    if len(post_signal_df) == 0:
                        # Price hasn't updated enough since signal creation
                        continue

                    high = post_signal_df['high'].max()
                    low = post_signal_df['low'].min()
                    
                    outcome = None
                    exit_price = None

                    if sig.direction == 'BUY':
                        if low <= sig.stop_loss:
                            outcome = 'HIT_SL'
                            exit_price = sig.stop_loss
                        elif high >= sig.take_profit_1:
                            outcome = 'HIT_TP'
                            exit_price = sig.take_profit_1
                    elif sig.direction == 'SELL':
                        if high >= sig.stop_loss:
                            outcome = 'HIT_SL'
                            exit_price = sig.stop_loss
                        elif low <= sig.take_profit_1:
                            outcome = 'HIT_TP'
                            exit_price = sig.take_profit_1

                    # Check for expiration
                    if outcome is None and sig.valid_until is not None and timezone.now() > sig.valid_until:
                        outcome = 'EXPIRED' # Expired
                        exit_price = float(df['close'].iloc[-1])

                    if outcome:
                        sig.status = outcome
                        sig.save()
                        
                        # Create performance record
                        pnl_percent = 0.0
                        perf_outcome = 'BREAKEVEN'
                        loss_category = None
                        if outcome == 'HIT_TP':
                            pnl_percent = float(sig.risk_reward) if sig.risk_reward else 1.50 # e.g. >= +1.5R
                            perf_outcome = 'WIN'
                        elif outcome == 'HIT_SL':
                            pnl_percent = -1.0 # -1R
                            perf_outcome = 'LOSS'
                            # Section 15.1: Required Loss Classification
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

                        SignalPerformance.objects.create(
                            signal=sig,
                            outcome=perf_outcome,
                            pnl_percent=pnl_percent,
                            pnl_r=pnl_percent,
                            loss_category=loss_category
                        )

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
                        from signals.notifications import telegram_notifier
                        pnl_pips = float(pnl_percent) * 20.0 # Standard R-unit to pips approx
                        telegram_notifier.send_signal_outcome(
                            signal=sig,
                            outcome=perf_outcome,
                            pnl_pips=pnl_pips,
                            exit_price=exit_price or float(sig.entry_price)
                        )

                        self.stdout.write(self.style.SUCCESS(f"Signal {sig.id} ({symbol}) resolved as {outcome}"))
                        processed += 1


            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error evaluating {symbol}: {e}"))

        # Auto-Trader open position evaluation & closure on TP/SL
        try:
            from accounts.auto_trader import AutoTraderEngine
            closed_auto = AutoTraderEngine.evaluate_and_close_open_trades()
            if closed_auto:
                self.stdout.write(self.style.SUCCESS(f"Auto-Trader evaluated and closed {len(closed_auto)} positions on TP/SL."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Auto-Trader evaluation note: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Evaluation complete. Resolved {processed} signals."))
