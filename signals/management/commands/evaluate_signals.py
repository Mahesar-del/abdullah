"""
Management command to evaluate active signals.
Checks if they hit Take Profit or Stop Loss, and updates their status.
Phase 5: Performance Tracking
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from signals.models import Signal, SignalPerformance
from signals.exit_rules import evaluate_signal_exit
from engines.data_fetcher import DataFetcher
from datetime import timedelta
import math

class Command(BaseCommand):
    help = 'Evaluates active signals and updates win/loss status'

    def handle(self, *args, **kwargs):
        active_signals = Signal.objects.filter(status='ACTIVE', direction__in=['BUY', 'SELL']).select_related('instrument')
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
                    if (getattr(df.index, 'tz', None) is not None and
                            df.index[-1] > timezone.now() + timedelta(seconds=30)):
                        self.stdout.write(self.style.WARNING(f'Skipped {symbol}: broker candle clock is future dated.'))
                        continue

                    from quant.config import ASSETS
                    from market_data.models import MarketQuoteSpread

                    asset_cfg = ASSETS.get(symbol)
                    cost_bps = asset_cfg.cost_bps if asset_cfg else 3.0

                    live_price = float(df['close'].iloc[-1])
                    if not math.isfinite(live_price) or live_price <= 0:
                        continue

                    # Realistic fill cost components (half-spread, slippage, round-trip commission)
                    live_quote = MarketQuoteSpread.objects.filter(
                        instrument__symbol=symbol, is_live=True,
                        timestamp__gte=timezone.now() - timedelta(minutes=2),
                    ).first()
                    if live_quote and live_quote.spread:
                        half_spread = float(live_quote.spread) / 2.0
                    else:
                        half_spread = live_price * (cost_bps * 0.60) / 10000.0

                    slippage = live_price * (cost_bps * 0.30) / 10000.0
                    commission = live_price * (cost_bps * 0.10) / 10000.0

                    for sig in signals:
                        execution_quote = (sig.strategy_evidence or {}).get('evidence', {}).get('execution_quote') or {}
                        if execution_quote and df.attrs.get('provider') != 'mt5':
                            # A futures/proxy price must not settle a broker-quoted
                            # setup merely because its nominal symbol looks similar.
                            continue
                        entry_half_spread = float(execution_quote['spread']) / 2.0 if execution_quote else half_spread
                        evaluation = evaluate_signal_exit(
                            df, direction=sig.direction, entry=float(sig.entry_price),
                            stop_loss=float(sig.stop_loss), take_profit=float(sig.take_profit_1),
                            generated_at=sig.generated_at, now=timezone.now(),
                            half_spread=entry_half_spread, slippage=slippage, commission=commission,
                            prior_state=sig.exit_state, valid_until=sig.valid_until,
                            price_basis=df.attrs.get('price_basis', 'mid'),
                            entry_is_executable=bool(execution_quote),
                        )
                        outcome, exit_price = evaluation.outcome, evaluation.exit_price
                        if not outcome:
                            if evaluation.state and evaluation.state != sig.exit_state:
                                Signal.objects.filter(
                                    pk=sig.pk, status='ACTIVE', exit_state=sig.exit_state,
                                ).update(exit_state=evaluation.state)
                            continue
                        fill_entry = float(evaluation.state['fill_entry'])
                        initial_risk = float(evaluation.state['initial_risk'])

                        if outcome:
                            # Calculate true realized net PnL and R-multiple after costs
                            total_commission = 2.0 * float(evaluation.state['commission'])
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

                            # Publish the lifecycle result and its performance row
                            # together. A failed save must leave the signal active
                            # so the next evaluation can retry it.
                            with transaction.atomic():
                                updated = Signal.objects.filter(
                                    pk=sig.pk, status='ACTIVE', exit_state=sig.exit_state,
                                ).update(
                                    status=outcome, closed_at=evaluation.exit_at or timezone.now(),
                                    exit_state=evaluation.state,
                                    take_profit_2=None, take_profit_3=None,
                                )
                                if not updated:
                                    continue  # Another evaluator already resolved it.
                                SignalPerformance.objects.update_or_create(
                                    signal=sig,
                                    defaults={
                                        'outcome': perf_outcome,
                                        'actual_exit': Decimal(str(round(float(exit_price), 5))),
                                        'pnl_percent': pnl_percent,
                                        'pnl_r': realized_r,
                                        'pnl_pips': pnl_pips,
                                        'loss_category': loss_category,
                                        'notes': (
                                            f"Exit model: conservative M1 replay; history coverage: {evaluation.state.get('history_coverage')}. "
                                            f"Costs: {evaluation.state.get('cost_basis')}. {evaluation.note}"
                                        ),
                                    }
                                )
                            sig.status = outcome
                            sig.exit_state = evaluation.state

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

                            # Feedback into Continuous Learning Engine for automated model retraining
                            try:
                                from engines.learning import ContinuousLearningEngine
                                ContinuousLearningEngine.on_trade_resolved(
                                    signal=sig,
                                    outcome=perf_outcome,
                                    realized_r=realized_r,
                                    loss_category=loss_category
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
