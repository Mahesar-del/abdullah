"""
Market Data Models - Phase 1
Stores price data for all instruments (Forex, Crypto, Commodities, Indices)
"""
from django.db import models
from django.utils import timezone


class Instrument(models.Model):
    """
    Trading instrument (e.g., XAUUSD, EURUSD, BTC/USD)
    """
    MARKET_CHOICES = [
        ('forex',       'Forex'),
        ('crypto',      'Crypto'),
        ('commodity',   'Commodity'),
        ('index',       'Index'),
        ('stock',       'Stock'),
    ]

    symbol      = models.CharField(max_length=20, unique=True, db_index=True)
    name        = models.CharField(max_length=100)
    market_type = models.CharField(max_length=20, choices=MARKET_CHOICES)
    base        = models.CharField(max_length=10, help_text="Base currency e.g. XAU")
    quote       = models.CharField(max_length=10, help_text="Quote currency e.g. USD")
    base_country = models.CharField(max_length=50, blank=True, help_text="e.g. United States")
    quote_country = models.CharField(max_length=50, blank=True, help_text="e.g. United States")
    base_region = models.CharField(max_length=50, blank=True, help_text="e.g. North America")
    quote_region = models.CharField(max_length=50, blank=True, help_text="e.g. North America")
    pip_value   = models.DecimalField(max_digits=10, decimal_places=5, default=0.0001)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.symbol} ({self.get_market_type_display()})"

    class Meta:
        ordering = ['market_type', 'symbol']


class OHLCV(models.Model):
    """
    Open-High-Low-Close-Volume data for each instrument and timeframe.
    This is the core price data table.
    """
    TIMEFRAME_CHOICES = [
        ('M1',  '1 Minute'),
        ('M5',  '5 Minutes'),
        ('M15', '15 Minutes'),
        ('M30', '30 Minutes'),
        ('H1',  '1 Hour'),
        ('H4',  '4 Hours'),
        ('D1',  'Daily'),
        ('W1',  'Weekly'),
        ('MN',  'Monthly'),
    ]

    instrument  = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name='ohlcv_data')
    timeframe   = models.CharField(max_length=5, choices=TIMEFRAME_CHOICES, db_index=True)
    timestamp   = models.DateTimeField(db_index=True)
    open_price  = models.DecimalField(max_digits=20, decimal_places=8)
    high_price  = models.DecimalField(max_digits=20, decimal_places=8)
    low_price   = models.DecimalField(max_digits=20, decimal_places=8)
    close_price = models.DecimalField(max_digits=20, decimal_places=8)
    volume      = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    real_volume = models.BooleanField(default=False, help_text="True if real exchange volume, False if proxy/tick volume")
    provider    = models.CharField(max_length=50, default='unknown', help_text="Data provider e.g. OANDA, Binance")
    is_complete = models.BooleanField(default=True, help_text="False if candle still forming")

    def __str__(self):
        return f"{self.instrument.symbol} {self.timeframe} @ {self.timestamp}"

    class Meta:
        unique_together = ['instrument', 'timeframe', 'timestamp']
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['instrument', 'timeframe', '-timestamp']),
        ]


class MarketSession(models.Model):
    """
    Track which market session is active (Sydney, Tokyo, London, New York)
    Important for signal filtering per SRS
    """
    SESSION_CHOICES = [
        ('sydney',   'Sydney'),
        ('tokyo',    'Tokyo'),
        ('london',   'London'),
        ('new_york', 'New York'),
        ('overlap',  'London-NY Overlap'),
    ]

    session     = models.CharField(max_length=20, choices=SESSION_CHOICES)
    open_time   = models.TimeField(help_text="UTC time")
    close_time  = models.TimeField(help_text="UTC time")
    is_active   = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.get_session_display()} ({self.open_time} - {self.close_time} UTC)"

    class Meta:
        ordering = ['open_time']


class MarketQuoteSpread(models.Model):
    """
    Real-time Bid/Ask and Spread data for instruments
    """
    instrument  = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name='quotes')
    timestamp   = models.DateTimeField(db_index=True)
    bid         = models.DecimalField(max_digits=20, decimal_places=8)
    ask         = models.DecimalField(max_digits=20, decimal_places=8)
    spread      = models.DecimalField(max_digits=10, decimal_places=5)
    provider    = models.CharField(max_length=50)
    is_live     = models.BooleanField(default=True, help_text="True for real bid/ask from a quote feed; False for derived estimates")

    @property
    def spread_pips(self) -> float:
        """Spread expressed in the instrument's pip units."""
        pip = float(self.instrument.pip_value) if self.instrument.pip_value else 0.0001
        return float(self.spread) / pip if pip else float(self.spread)

    def __str__(self):
        return f"{self.instrument.symbol} @ {self.timestamp}: Spread {self.spread}"

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['instrument', '-timestamp']),
        ]


class DataSourceHealth(models.Model):
    """
    Tracks the health and reliability of external data providers
    """
    STATUS_CHOICES = [
        ('HEALTHY', 'Healthy'),
        ('DEGRADED', 'Degraded'),
        ('DOWN', 'Down'),
    ]

    provider_name = models.CharField(max_length=50, unique=True, db_index=True)
    endpoint      = models.CharField(max_length=200, blank=True)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='HEALTHY')
    last_success  = models.DateTimeField(null=True, blank=True)
    last_error    = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    latency_ms    = models.IntegerField(null=True, blank=True)
    is_fallback   = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.provider_name} - {self.get_status_display()}"
