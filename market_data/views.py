"""
Market Data Views
"""
import time
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


def check_market_status(symbol: str) -> dict:
    """
    Returns real exchange market status:
    - Crypto (BTC, ETH, SOL, etc.): OPEN 24/7/365.
    - Forex, Indices (US30, NAS100, SPX500), Commodities (XAUUSD, USOIL):
      Closed from Friday 21:00 UTC (5 PM EST) to Sunday 21:00 UTC (5 PM EST).
    """
    sym = (symbol or '').upper().replace('/', '')
    is_crypto = any(k in sym for k in ('BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA'))
    if is_crypto:
        return {'is_open': True, 'status': 'OPEN_24_7', 'label': 'Market Open 24/7', 'reopens': None}

    from django.utils import timezone as dj_tz
    now_utc = dj_tz.now()
    weekday = now_utc.weekday()  # 4 = Fri, 5 = Sat, 6 = Sun
    hour = now_utc.hour

    if (weekday == 4 and hour >= 21) or (weekday == 5) or (weekday == 6 and hour < 21):
        return {
            'is_open': False,
            'status': 'WEEKEND_CLOSED',
            'label': 'Market Closed (Weekend)',
            'reopens': 'Sunday 5:00 PM EST (21:00 UTC)'
        }

    return {'is_open': True, 'status': 'OPEN', 'label': 'Market Open', 'reopens': None}


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

        mkt = check_market_status(symbol)

        fetcher = DataFetcher()
        tick = fetcher.get_live_tick(symbol, tf)
        if not tick:
            return Response({'error': 'Live tick unavailable'}, status=503)

        tick['is_market_open'] = mkt['is_open']
        tick['market_status'] = mkt['status']
        tick['market_label'] = mkt['label']
        tick['market_reopens'] = mkt['reopens']

        # Trigger background TP1/SL evaluator ONLY when market is actually open (or crypto)
        if mkt['is_open']:
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
        try:
            limit = min(max(int(request.query_params.get('limit', 800)), 100), 1500)
        except Exception:
            limit = 800
        fast_mode = request.query_params.get('fast') == '1'

        fetcher = DataFetcher()
        df = fetcher.fetch(symbol, tf, limit=limit)

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
        engine_details = {} if fast_mode else build_signal_engine_details(sig, df.tail(150) if df is not None else None, symbol, tf)
        auto_trade = None if fast_mode else get_signal_auto_trade_details(sig)

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


_INST_CACHE = {"at": 0.0, "data": None}


class InstitutionalOverviewView(generics.GenericAPIView):
    """
    GET /api/market/institutional-positions/
    Returns real CFTC Commitments of Traders positions, real Binance derivatives funding rates,
    and empirical intermarket snapshot data (cached for 300s for instantaneous page refreshes).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from rest_framework.response import Response

        now = time.monotonic()
        if _INST_CACHE["data"] is not None and (now - _INST_CACHE["at"]) < 300:
            return Response(_INST_CACHE["data"])

        from signals.models import InstitutionalPosition
        from engines.institutional import InstitutionalEngine
        from engines.intermarket import IntermarketEngine

        target_symbols = ['XAUUSD', 'EURUSD', 'BTCUSD', 'USOIL', 'GBPUSD', 'SPX500']
        positions_data = []

        for sym in target_symbols:
            pos = InstitutionalPosition.objects.filter(symbol=sym).order_by('-report_date').first()
            if not pos:
                try:
                    InstitutionalEngine.sync_live_cot_data([sym])
                    pos = InstitutionalPosition.objects.filter(symbol=sym).order_by('-report_date').first()
                except Exception:
                    pass

            funding_rate = None
            if 'BTC' in sym or 'ETH' in sym:
                funding_rate = InstitutionalEngine.fetch_crypto_funding_rate(sym)

            if pos:
                bias = 'Bullish Bias' if pos.percentile_52w >= 60.0 else ('Bearish Bias' if pos.percentile_52w <= 40.0 else 'Neutral / Range')
                if pos.extreme_bullish:
                    bias = 'Overcrowded Bullish'
                elif pos.extreme_bearish:
                    bias = 'Extreme Bearish Squeeze'

                positions_data.append({
                    'symbol': sym,
                    'report_date': pos.report_date.strftime('%Y-%m-%d'),
                    'non_commercial_net': pos.non_commercial_net,
                    'commercial_net': pos.commercial_net,
                    'open_interest': pos.open_interest,
                    'percentile_52w': round(pos.percentile_52w, 1),
                    'z_score_52w': round(pos.z_score_52w, 2),
                    'bias': bias,
                    'is_confirmed': not pos.is_proxy,
                    'source': pos.source,
                    'funding_rate': funding_rate,
                })

        macro = IntermarketEngine.get_real_intermarket_metrics('XAUUSD')

        payload = {
            'success': True,
            'source': 'CFTC Official Socrata Feed & Binance Derivatives',
            'positions': positions_data,
            'macro': {
                'yield_curve_slope': macro.get('yield_curve_slope', 0.96),
                'dxy_gold_corr': macro.get('dxy', -0.25),
                'spx_gold_corr': macro.get('spx', 0.43),
                'oil_gold_corr': macro.get('oil', -0.07),
            }
        }
        _INST_CACHE.update(at=now, data=payload)
        return Response(payload)


class InstitutionalLiquidityView(generics.GenericAPIView):
    """GET /api/market/institutional-liquidity/?symbol=BTCUSD — Live Level 2 Depth, Open Interest & Fed Net Liquidity"""
    permission_classes = [AllowAny]

    def get(self, request):
        from rest_framework.response import Response
        from engines.institutional_liquidity import InstitutionalLiquidityEngine
        from engines.data_fetcher import DataFetcher

        symbol = request.query_params.get('symbol', 'BTCUSD').upper()
        fetcher = DataFetcher()
        cur_p = fetcher.get_current_price(symbol) or 0.0

        depth = InstitutionalLiquidityEngine.get_order_book_depth(symbol, cur_price=cur_p)
        macro_net = InstitutionalLiquidityEngine.get_macro_net_liquidity()

        return Response({
            'success': True,
            'symbol': symbol,
            'current_price': cur_p,
            'depth': depth,
            'macro_liquidity': macro_net
        })

