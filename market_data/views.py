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
