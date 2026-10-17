"""
Market Data Serializers
"""
from rest_framework import serializers
from .models import Instrument, OHLCV, MarketSession


class InstrumentSerializer(serializers.ModelSerializer):
    market_type_display = serializers.CharField(source='get_market_type_display', read_only=True)

    class Meta:
        model = Instrument
        fields = ['id', 'symbol', 'name', 'market_type', 'market_type_display',
                  'base', 'quote', 'pip_value', 'is_active']


class OHLCVSerializer(serializers.ModelSerializer):
    symbol = serializers.CharField(source='instrument.symbol', read_only=True)

    class Meta:
        model = OHLCV
        fields = ['id', 'symbol', 'timeframe', 'timestamp',
                  'open_price', 'high_price', 'low_price', 'close_price',
                  'volume', 'is_complete']


class MarketSessionSerializer(serializers.ModelSerializer):
    session_display = serializers.CharField(source='get_session_display', read_only=True)

    class Meta:
        model = MarketSession
        fields = '__all__'
