"""
Signal Serializers - DRF
"""
from rest_framework import serializers
from .models import Signal, SignalPerformance, NewsEvent


class SignalSerializer(serializers.ModelSerializer):
    instrument_symbol = serializers.CharField(source='instrument.symbol', read_only=True)
    instrument_name   = serializers.CharField(source='instrument.name', read_only=True)
    market_type       = serializers.CharField(source='instrument.get_market_type_display', read_only=True)

    class Meta:
        model = Signal
        fields = [
            'id', 'instrument_symbol', 'instrument_name', 'market_type',
            'timeframe', 'direction', 'strength', 'status',
            'entry_price', 'stop_loss', 'take_profit_1', 'take_profit_2', 'take_profit_3',
            'risk_reward', 'confidence_score', 'warnings',
            'decision_class', 'market_regime', 'independent_groups',
            'is_trade_allowed', 'recommended_lots',
            'generated_at', 'valid_until',
        ]


class SignalPerformanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignalPerformance
        fields = '__all__'


class SignalDetailSerializer(SignalSerializer):
    """Extended serializer with all engine scores"""
    performance = SignalPerformanceSerializer(read_only=True)

    class Meta(SignalSerializer.Meta):
        fields = SignalSerializer.Meta.fields + [
            'technical_score', 'smc_score', 'price_action_score',
            'macro_score', 'news_score', 'institutional_score', 'ai_ml_score',
            'analysis_summary', 'closed_at', 'performance',
        ]


class NewsEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsEvent
        fields = '__all__'
