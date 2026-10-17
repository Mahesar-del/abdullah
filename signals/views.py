"""
Signal Views - REST API endpoints
"""
from rest_framework import generics, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from .models import Signal, SignalPerformance, NewsEvent
from .serializers import SignalSerializer, SignalDetailSerializer, NewsEventSerializer


class SignalListView(generics.ListAPIView):
    """GET /api/signals/ — List all signals with filters"""
    serializer_class = SignalSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = Signal.objects.select_related('instrument')
        direction  = self.request.query_params.get('direction')
        status     = self.request.query_params.get('status')
        instrument = self.request.query_params.get('instrument')

        if direction:
            qs = qs.filter(direction=direction.upper())
        if status:
            qs = qs.filter(status=status.upper())
        if instrument:
            qs = qs.filter(instrument__symbol__icontains=instrument)
        return qs


class SignalDetailView(generics.RetrieveAPIView):
    """GET /api/signals/<id>/ — Single signal detail"""
    queryset = Signal.objects.select_related('instrument').prefetch_related('performance')
    serializer_class = SignalDetailSerializer
    permission_classes = [AllowAny]


class SignalChartView(views.APIView):
    """GET /api/signals/<id>/chart/ — Candle data + Trade Entry, SL, TP levels"""
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            signal = Signal.objects.select_related('instrument').get(pk=pk)
        except Signal.DoesNotExist:
            return Response({'error': 'Signal not found'}, status=404)

        from engines.data_fetcher import DataFetcher
        import pandas as pd

        sym = signal.instrument.symbol
        tf = signal.timeframe

        fetcher = DataFetcher()
        df = fetcher.fetch(sym, tf, limit=120)

        candles = []
        if df is not None and not df.empty:
            for idx, row in df.iterrows():
                try:
                    if hasattr(idx, 'timestamp'):
                        t = int(idx.timestamp())
                    else:
                        t = int(pd.to_datetime(idx).timestamp())
                except Exception:
                    continue
                candles.append({
                    'time': t,
                    'open': round(float(row['open']), 5),
                    'high': round(float(row['high']), 5),
                    'low': round(float(row['low']), 5),
                    'close': round(float(row['close']), 5),
                    'volume': float(row.get('volume', 0)),
                })

        return Response({
            'signal_id': signal.id,
            'symbol': sym,
            'name': signal.instrument.name,
            'timeframe': tf,
            'direction': signal.direction,
            'status': signal.status,
            'entry_price': float(signal.entry_price),
            'stop_loss': float(signal.stop_loss),
            'take_profit_1': float(signal.take_profit_1),
            'take_profit_2': float(signal.take_profit_2) if signal.take_profit_2 else None,
            'take_profit_3': float(signal.take_profit_3) if signal.take_profit_3 else None,
            'risk_reward': float(signal.risk_reward),
            'confidence_score': float(signal.confidence_score),
            'strength': signal.strength,
            'generated_at': signal.generated_at.isoformat(),
            'generated_ts': int(signal.generated_at.timestamp()),
            'analysis_summary': signal.analysis_summary,
            'warnings': signal.warnings,
            'decision_class': getattr(signal, 'decision_class', 'STRONG'),
            'market_regime': getattr(signal, 'market_regime', 'TRENDING'),
            'independent_groups': getattr(signal, 'independent_groups', {}),
            'is_trade_allowed': getattr(signal, 'is_trade_allowed', True),
            'recommended_lots': getattr(signal, 'recommended_lots', 0.10),
            'technical_score': signal.technical_score,
            'smc_score': signal.smc_score,
            'price_action_score': signal.price_action_score,
            'macro_score': signal.macro_score,
            'news_score': signal.news_score,
            'institutional_score': signal.institutional_score,
            'ai_ml_score': signal.ai_ml_score,
            'candles': candles,
        })


class ActiveSignalsView(generics.ListAPIView):
    """GET /api/signals/active/ — Only high-conviction ACTIVE signals (>= 75.0% confidence)"""
    serializer_class = SignalSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        from .auto_evaluator import maybe_evaluate
        from .auto_scanner import maybe_auto_scan
        maybe_evaluate()
        maybe_auto_scan()
        return (Signal.objects.filter(status='ACTIVE', direction__in=['BUY', 'SELL'], confidence_score__gte=75.0)
                .select_related('instrument').order_by('-confidence_score'))


class SignalStatsView(views.APIView):
    """GET /api/signals/stats/ — Win rate, total signals, avg confidence, per-instrument scores, and R-multiple performance metrics"""
    permission_classes = [AllowAny]

    def get(self, request):
        from .auto_evaluator import maybe_evaluate
        maybe_evaluate()
        trades  = Signal.objects.filter(direction__in=['BUY', 'SELL'])
        total   = trades.count()
        active  = trades.filter(status='ACTIVE').count()
        hits_tp = trades.filter(status='HIT_TP').count()
        hits_sl = trades.filter(status='HIT_SL').count()
        closed  = hits_tp + hits_sl

        # Real win rate if closed trades exist; else running avg confidence as proxy score
        avg_conf_val = trades.aggregate(avg=Avg('confidence_score'))['avg'] or 0
        if closed > 0:
            win_rate = round((hits_tp / closed * 100), 2)
        else:
            win_rate = round(float(avg_conf_val), 2)

        # ── R-Multiple Performance Tracking (Phase 12) ─────────────────────────
        perfs = SignalPerformance.objects.filter(outcome__in=['WIN', 'LOSS'])
        wins = perfs.filter(outcome='WIN')
        losses = perfs.filter(outcome='LOSS')

        win_count = wins.count()
        loss_count = losses.count()

        if win_count > 0:
            avg_win_val = round(float(wins.aggregate(avg=Avg('pnl_r'))['avg'] or 0.0), 2)
        else:
            avg_win_val = 0.0

        if loss_count > 0:
            avg_loss_val = round(float(losses.aggregate(avg=Avg('pnl_r'))['avg'] or 0.0), 2)
        else:
            avg_loss_val = 0.0

        # Total Win R and Loss R
        total_win_r = float(wins.aggregate(sum=Sum('pnl_r'))['sum'] or 0.0)
        total_loss_r = abs(float(losses.aggregate(sum=Sum('pnl_r'))['sum'] or 0.0))

        if total_loss_r > 0:
            profit_factor = round(total_win_r / total_loss_r, 2)
        elif total_win_r > 0:
            profit_factor = round(total_win_r, 2)
        else:
            profit_factor = 0.0

        # Trade Expectancy in R: (Win_Rate * Avg_Win) - (Loss_Rate * |Avg_Loss|)
        if closed > 0:
            win_p = hits_tp / closed
            loss_p = hits_sl / closed
            expectancy_r = round((win_p * avg_win_val) - (loss_p * abs(avg_loss_val)), 2)
        else:
            expectancy_r = 0.0

        # Max Drawdown calculation over cumulative equity curve (in R and %)
        cum_r = 0.0
        peak_r = 0.0
        max_dd_r = 0.0
        for p in perfs.order_by('signal__generated_at'):
            val = float(p.pnl_r) if p.pnl_r is not None else (avg_win_val if p.outcome == 'WIN' else -1.0)
            cum_r += val
            if cum_r > peak_r:
                peak_r = cum_r
            dd = peak_r - cum_r
            if dd > max_dd_r:
                max_dd_r = dd

        # Assuming standard 1% risk per 1R -> Max Drawdown %
        max_drawdown_pct = round(max_dd_r * 1.0, 1) if max_dd_r > 0 else 0.0

        # ── Per-instrument running score ─────────────────────────────────────
        # Group by instrument: take the highest-confidence signal per pair
        instrument_scores = []
        seen_instruments  = set()

        for sig in Signal.objects.filter(status='ACTIVE', direction__in=['BUY', 'SELL']).select_related('instrument').order_by(
                'instrument__symbol', '-confidence_score'):
            sym = sig.instrument.symbol
            if sym in seen_instruments:
                continue
            seen_instruments.add(sym)

            pair_tp     = Signal.objects.filter(instrument=sig.instrument, status='HIT_TP').count()
            pair_sl     = Signal.objects.filter(instrument=sig.instrument, status='HIT_SL').count()
            pair_closed = pair_tp + pair_sl

            if pair_closed > 0:
                pair_score = round((pair_tp / pair_closed * 100), 2)
            else:
                pair_avg = trades.filter(instrument=sig.instrument).aggregate(
                    avg=Avg('confidence_score'))['avg'] or 0
                pair_score = round(float(pair_avg), 2)

            instrument_scores.append({
                'symbol':     sym,
                'name':       sig.instrument.name,
                'direction':  sig.direction,
                'confidence': float(sig.confidence_score),
                'score':      pair_score,
                'closed':     pair_closed,
                'tp':         pair_tp,
                'sl':         pair_sl,
            })

        # ── Loss Category Breakdown (Section 15.1) ──────────────────────────
        loss_breakdown = {}
        for loss_row in losses.values('loss_category').annotate(count=Count('id')):
            cat = loss_row['loss_category'] or 'WRONG_REGIME'
            loss_breakdown[cat] = loss_row['count']

        return Response({
            'total_signals':     total,
            'active_signals':    active,
            'take_profit_hits':  hits_tp,
            'stop_loss_hits':    hits_sl,
            'closed_signals':    closed,
            'win_rate_percent':  win_rate,
            'win_rate_source':   'actual' if closed > 0 else 'confidence_avg',
            'avg_confidence':    round(float(avg_conf_val), 2),
            'avg_win_r':         avg_win_val,
            'avg_loss_r':        avg_loss_val,
            'profit_factor':     profit_factor,
            'expectancy_r':      expectancy_r,
            'max_drawdown_pct':  max_drawdown_pct,
            'loss_breakdown':    loss_breakdown,
            'by_direction': {
                'BUY':  Signal.objects.filter(direction='BUY').count(),
                'SELL': Signal.objects.filter(direction='SELL').count(),
                'WAIT': 0,
            },
            'instrument_scores': instrument_scores,
        })


class NewsEventListView(generics.ListAPIView):
    """GET /api/signals/news-events/ — Upcoming high-impact news"""
    serializer_class = NewsEventSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return NewsEvent.objects.filter(
            event_time__gte=timezone.now()
        ).order_by('event_time')[:20]
