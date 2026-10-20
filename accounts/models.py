from django.db import models
from django.utils import timezone


class LinkedBrokerAccount(models.Model):
    """
    Connected Broker Account for automated trade execution.
    Supports MT4, MT5, Exness, Binance, Bybit, and Paper Trading.
    """
    BROKER_CHOICES = [
        ('PAPER', 'TradeSense Paper Simulation'),
        ('EXNESS', 'Exness (MT5/MT4)'),
        ('MT5', 'MetaTrader 5'),
        ('MT4', 'MetaTrader 4'),
        ('BINANCE', 'Binance Futures / Spot'),
        ('BYBIT', 'Bybit Derivatives'),
    ]

    name = models.CharField(max_length=100, default='Primary Account')
    broker_type = models.CharField(max_length=20, choices=BROKER_CHOICES, default='PAPER')
    account_number = models.CharField(max_length=100, blank=True, default='DEMO-8899')
    server = models.CharField(max_length=100, blank=True, default='MetaQuotes-Demo')
    api_key = models.CharField(max_length=255, blank=True, default='')
    api_secret = models.CharField(max_length=255, blank=True, default='')
    
    is_paper = models.BooleanField(default=True, help_text="True for zero-risk demo/simulation trading")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=10000.00)
    equity = models.DecimalField(max_digits=12, decimal_places=2, default=10000.00)
    currency = models.CharField(max_length=10, default='USD')
    
    is_active = models.BooleanField(default=True)
    auto_trade_enabled = models.BooleanField(
        default=False,
        help_text="If True, automatically takes high-confidence trades without per-trade prompts"
    )
    is_authorized = models.BooleanField(
        default=False,
        help_text="Persistent user authorization for automated trading"
    )
    authorized_at = models.DateTimeField(null=True, blank=True)
    permission_type = models.CharField(max_length=50, default='PAPER_SIMULATION_TRADING')
    authorization_status = models.CharField(
        max_length=30,
        default='OFF',
        choices=[
            ('ON', 'Active (Authorized)'),
            ('OFF', 'Disabled by User'),
            ('PAUSED', 'Temporarily Paused'),
            ('KILL_SWITCH_ACTIVE', 'Kill Switch Triggered'),
            ('EMERGENCY_STOPPED', 'Emergency Stopped'),
            ('DISCONNECTED', 'Broker Disconnected'),
        ]
    )
    max_risk_pct = models.FloatField(
        default=0.5,
        help_text="Maximum account risk percentage per trade (default 0.5%)"
    )
    max_open_risk_pct = models.FloatField(
        default=3.0,
        help_text="Maximum total open risk across all concurrent positions (Section 13)"
    )
    daily_drawdown_limit_pct = models.FloatField(default=5.0)
    max_drawdown_limit_pct = models.FloatField(default=10.0)
    current_drawdown_pct = models.FloatField(default=0.0)
    disable_reason = models.CharField(max_length=255, blank=True, default='')
    connection_status = models.CharField(max_length=30, default='CONNECTED')
    last_sync_at = models.DateTimeField(null=True, blank=True)

    min_confidence = models.FloatField(
        default=75.0,
        help_text="Minimum signal confidence score required to auto-open trade"
    )
    max_open_trades = models.IntegerField(default=5, help_text="Maximum concurrent open positions")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        status = f"🟢 {self.authorization_status}" if self.auto_trade_enabled and self.authorization_status == 'ON' else f"⏸️ {self.authorization_status}"
        return f"{self.name} ({self.get_broker_type_display()}) - {status} [${self.balance:,.2f}]"


class SystemTradingConfig(models.Model):
    """
    Global Master Switch and Emergency Stop Configuration.
    Controls system-wide automated trading execution across all accounts.
    """
    global_auto_trading = models.BooleanField(default=False, help_text="Global Master Switch: ON/OFF")
    emergency_stop_active = models.BooleanField(default=False)
    emergency_stopped_at = models.DateTimeField(null=True, blank=True)
    emergency_stop_reason = models.CharField(max_length=255, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_config(cls):
        cfg, _ = cls.objects.get_or_create(id=1)
        return cfg

    def __str__(self):
        status = "🟢 ON" if self.global_auto_trading and not self.emergency_stop_active else "🔴 OFF"
        return f"SystemTradingConfig [{status}]"


class AutoTradeExecution(models.Model):
    """
    Individual automated trade record executed by TradeSense Pro.
    Tracks entry, active position, dynamic exit (TP/SL), and realized PnL.
    Includes full broker execution confirmation and audit trail fields.
    """
    STATUS_CHOICES = [
        ('OPEN', 'Open (Active)'),
        ('CLOSED', 'Closed'),
        ('CANCELLED', 'Cancelled'),
    ]

    EXIT_CHOICES = [
        ('TP_HIT', 'Take Profit Hit (Target Achieved)'),
        ('SL_HIT', 'Stop Loss Hit (Risk Protected)'),
        ('MANUAL', 'Manual Close by User'),
        ('KILL_SWITCH', 'Emergency Kill Switch Triggered'),
        ('EXPIRED', 'Signal Expired'),
    ]

    DIRECTION_CHOICES = [
        ('BUY', 'BUY (Long)'),
        ('SELL', 'SELL (Short)'),
    ]

    account = models.ForeignKey(LinkedBrokerAccount, on_delete=models.CASCADE, related_name='executions')
    signal = models.ForeignKey('signals.Signal', on_delete=models.SET_NULL, null=True, blank=True, related_name='auto_executions')
    symbol = models.CharField(max_length=20)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    
    volume_lots = models.FloatField(default=0.10)
    entry_price = models.FloatField()
    stop_loss = models.FloatField()
    take_profit_1 = models.FloatField()
    take_profit_2 = models.FloatField(null=True, blank=True)
    take_profit_3 = models.FloatField(null=True, blank=True)
    current_price = models.FloatField(null=True, blank=True)
    
    # Section 15: Broker Execution Confirmation fields
    broker_order_id = models.CharField(max_length=100, blank=True, default='')
    client_order_id = models.CharField(max_length=100, blank=True, default='')
    requested_price = models.FloatField(null=True, blank=True)
    executed_price = models.FloatField(null=True, blank=True)
    spread_pips = models.FloatField(default=0.0)
    slippage_pips = models.FloatField(default=0.0)

    # Section 18: Complete Audit Log fields
    confluence_groups = models.JSONField(default=dict, blank=True)
    market_regime = models.CharField(max_length=50, default='TRENDING')
    audit_reasoning = models.TextField(blank=True, default='')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    exit_price = models.FloatField(null=True, blank=True)
    exit_reason = models.CharField(max_length=30, choices=EXIT_CHOICES, null=True, blank=True)
    
    pnl_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    pnl_r = models.FloatField(default=0.0)
    risk_amount_currency = models.FloatField(default=0.0, help_text="Planned cash risk captured when the position opened")
    
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"[{self.status}] {self.direction} {self.symbol} {self.volume_lots} lots @ {self.entry_price} (PnL: ${self.pnl_amount:,.2f})"
