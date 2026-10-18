"""
Market Data Views
"""
from rest_framework import generics
from rest_framework.permissions import AllowAny
from .models import Instrument, OHLCV, MarketSession
from .serializers import InstrumentSerializer, OHLCVSerializer, MarketSessionSerializer


class InstrumentListView(generics.ListAPIView):
    """GET /api/market/instruments/ — All trading instruments"""
    serializer_class = InstrumentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = Instrument.objects.filter(is_active=True)
        market_type = self.request.query_params.get('type')
        if market_type:
            qs = qs.filter(market_type=market_type.lower())
        return qs


class InstrumentDetailView(generics.RetrieveAPIView):
    """GET /api/market/instruments/<symbol>/ — Single instrument"""
    serializer_class = InstrumentSerializer
    permission_classes = [AllowAny]
    lookup_field = 'symbol'
    queryset = Instrument.objects.all()


class OHLCVView(generics.ListAPIView):
    """GET /api/market/ohlcv/?symbol=XAUUSD&timeframe=H1 — Price data"""
    serializer_class = OHLCVSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        symbol    = self.request.query_params.get('symbol', 'XAUUSD')
        timeframe = self.request.query_params.get('timeframe', 'H1')
        limit     = int(self.request.query_params.get('limit', 100))

        return OHLCV.objects.filter(
            instrument__symbol=symbol,
            timeframe=timeframe
        ).order_by('-timestamp')[:limit]


class MarketSessionView(generics.ListAPIView):
    """GET /api/market/sessions/ — Market session times"""
    serializer_class = MarketSessionSerializer
    permission_classes = [AllowAny]
    queryset = MarketSession.objects.filter(is_active=True)


class LiveTickView(generics.GenericAPIView):
    """GET /api/market/live-tick/?symbol=BTCUSD&tf=H2&signal_id=12 — Real-time active candle & price tick + TP1 auto-close check"""
    permission_classes = [AllowAny]

    def get(self, request):
        from rest_framework.response import Response
        from engines.data_fetcher import DataFetcher
        from signals.auto_evaluator import maybe_evaluate
        from signals.models import Signal

        symbol = request.query_params.get('symbol', 'BTCUSD').upper()
        tf = request.query_params.get('tf', 'H1').upper()
        signal_id = request.query_params.get('signal_id')

        fetcher = DataFetcher()
        tick = fetcher.get_live_tick(symbol, tf)
        if not tick:
            return Response({'error': 'Live tick unavailable'}, status=503)

        # Trigger background TP1/SL evaluator
        maybe_evaluate()

        # If a specific signal_id is being watched, return its current live status (and auto-close if live price hit TP1/SL)
        if signal_id and str(signal_id).isdigit():
            try:
                sig = Signal.objects.filter(pk=int(signal_id)).first()
                if sig:
                    live_p = float(tick.get('price', 0))
                    if sig.status == 'ACTIVE' and live_p > 0:
                        tp1_val = float(sig.take_profit_1)
                        sl_val = float(sig.stop_loss)
                        hit_outcome = None
                        exit_p = None
                        if sig.direction == 'BUY':
                            if live_p >= tp1_val:
                                hit_outcome, exit_p = 'HIT_TP', tp1_val
                            elif live_p <= sl_val:
                                hit_outcome, exit_p = 'HIT_SL', sl_val
                        elif sig.direction == 'SELL':
                            if live_p <= tp1_val:
                                hit_outcome, exit_p = 'HIT_TP', tp1_val
                            elif live_p >= sl_val:
                                hit_outcome, exit_p = 'HIT_SL', sl_val

                        if hit_outcome:
                            from django.core.management import call_command
                            call_command('evaluate_signals', verbosity=0)
                            sig.refresh_from_db()

                    tick['signal_status'] = sig.status
            except Exception:
                pass

        return Response(tick)


class LiveSymbolChartView(generics.GenericAPIView):
    """GET /api/market/live-chart/?symbol=XAUUSD&tf=H1 — Full live candles + active signal if any"""
    permission_classes = [AllowAny]

    def get(self, request):
        from rest_framework.response import Response
        from engines.data_fetcher import DataFetcher
        from signals.models import Signal
        import pandas as pd

        symbol = request.query_params.get('symbol', 'XAUUSD').upper()
        tf = request.query_params.get('tf', 'H1').upper()
        fetcher = DataFetcher()
        df = fetcher.fetch(symbol, tf, limit=150)

        candles = []
        if df is not None and not df.empty:
            for idx, row in df.iterrows():
                try:
                    t = int(idx.timestamp()) if hasattr(idx, 'timestamp') else int(pd.to_datetime(idx).timestamp())
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

        inst = Instrument.objects.filter(symbol=symbol).first()
        sig = (Signal.objects.filter(instrument__symbol=symbol, status='ACTIVE', direction__in=['BUY', 'SELL'])
               .order_by('-confidence_score', '-generated_at').first())
        if not sig:
            sig = (Signal.objects.filter(instrument__symbol=symbol, direction__in=['BUY', 'SELL'])
                   .order_by('-generated_at').first())

        live_price = candles[-1]['close'] if candles else (float(sig.entry_price) if sig else 0.0)

        from signals.views import build_signal_engine_details, get_signal_auto_trade_details
        engine_details = build_signal_engine_details(sig, df, symbol, tf)
        auto_trade = get_signal_auto_trade_details(sig)

        return Response({
            'signal_id': sig.id if sig else None,
            'symbol': symbol,
            'name': inst.name if inst else symbol,
            'timeframe': tf,
            'signal_timeframe': sig.timeframe if sig else tf,
            'tf_seconds': DataFetcher.TF_SECONDS.get(tf, 3600),
            'live_price': live_price,
            'direction': sig.direction if sig else 'WAIT',
            'status': sig.status if sig else 'LIVE',
            'entry_price': float(sig.entry_price) if sig else live_price,
            'stop_loss': float(sig.stop_loss) if sig else None,
            'take_profit_1': float(sig.take_profit_1) if sig else None,
            'take_profit_2': None,
            'take_profit_3': None,
            'risk_reward': float(sig.risk_reward) if sig else 1.5,
            'confidence_score': float(sig.confidence_score) if sig else 0.0,
            'technical_score': float(sig.technical_score) if sig else engine_details.get('technical', {}).get('score', 0),
            'smc_score': float(sig.smc_score) if sig else engine_details.get('smc_ict', {}).get('score', 0),
            'price_action_score': float(sig.price_action_score) if sig else engine_details.get('price_action', {}).get('score', 0),
            'macro_score': float(sig.macro_score) if sig else engine_details.get('macro', {}).get('score', 50),
            'news_score': float(sig.news_score) if sig else engine_details.get('news', {}).get('score', 50),
            'institutional_score': float(sig.institutional_score) if sig else engine_details.get('institutional', {}).get('score', 0),
            'intermarket_score': float(getattr(sig, 'intermarket_score', 0) or engine_details.get('intermarket', {}).get('score', 0)),
            'ai_ml_score': float(sig.ai_ml_score) if sig else engine_details.get('ai_ml', {}).get('score', 0),
            'engine_details': engine_details,
            'auto_trade': auto_trade,
            'generated_ts': int(sig.generated_at.timestamp()) if sig else (candles[-1]['time'] if candles else 0),
            'candles': candles,
        })

