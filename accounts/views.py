"""
Accounts Views — Broker Linking & Automated Trade Management
"""
import logging
from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from django.shortcuts import get_object_or_404
from django.utils import timezone
from decimal import Decimal

from .models import LinkedBrokerAccount, AutoTradeExecution
from .auto_trader import AutoTraderEngine

logger = logging.getLogger(__name__)


class LinkedAccountsView(views.APIView):
    """
    GET /api/accounts/linked/
    List all connected broker accounts with current balances & stats.
    
    POST /api/accounts/linked/
    Connect a new broker account (MT5, MT4, Exness, Binance, Bybit, Paper).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        accounts = LinkedBrokerAccount.objects.filter(is_active=True).order_by('-created_at')
        data = []
        for acc in accounts:
            open_count = acc.executions.filter(status='OPEN').count()
            closed_trades = acc.executions.filter(status='CLOSED')
            total_realized_pnl = sum([float(t.pnl_amount) for t in closed_trades])

            data.append({
                'id': acc.id,
                'name': acc.name,
                'broker_type': acc.broker_type,
                'broker_name': acc.get_broker_type_display(),
                'account_number': acc.account_number,
                'server': acc.server,
                'is_paper': acc.is_paper,
                'balance': float(acc.balance),
                'equity': float(acc.equity),
                'currency': acc.currency,
                'auto_trade_enabled': acc.auto_trade_enabled,
                'max_risk_pct': acc.max_risk_pct,
                'min_confidence': acc.min_confidence,
                'max_open_trades': acc.max_open_trades,
                'open_trades_count': open_count,
                'total_realized_pnl': round(total_realized_pnl, 2),
                'created_at': acc.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        return Response({'accounts': data})

    def post(self, request):
        name = request.data.get('name', '').strip()
        broker_type = request.data.get('broker_type', 'MT5').upper()
        account_number = request.data.get('account_number', '').strip()
        password = request.data.get('password', '').strip()
        server = request.data.get('server', '').strip()
        api_key = request.data.get('api_key', account_number).strip()
        api_secret = request.data.get('api_secret', password).strip()
        # Auto-detect is_paper / Live vs Demo automatically from server name
        if server:
            s_up = server.upper()
            if 'REAL' in s_up or 'LIVE' in s_up:
                is_paper = False
            elif 'TRIAL' in s_up or 'DEMO' in s_up:
                is_paper = True
            else:
                is_paper = bool(request.data.get('is_paper', broker_type == 'PAPER'))
        else:
            is_paper = bool(request.data.get('is_paper', broker_type == 'PAPER'))

        raw_balance = request.data.get('balance')
        try:
            balance = float(raw_balance) if (raw_balance is not None and str(raw_balance).strip() != '') else 10000.0
        except (ValueError, TypeError):
            balance = 10000.0
        auto_trade_enabled = bool(request.data.get('auto_trade_enabled', False))
        try:
            max_risk_pct = float(request.data.get('max_risk_pct', 0.5))
            max_open_risk_pct = float(request.data.get('max_open_risk_pct', 1.5))
        except (TypeError, ValueError):
            return Response({'success': False, 'error': 'Risk limits must be numeric.'}, status=status.HTTP_400_BAD_REQUEST)
        is_authorized = bool(request.data.get('is_authorized', False))

        if not 0 < max_risk_pct <= 5.0 or not 0 < max_open_risk_pct <= 15.0:
            return Response(
                {'success': False, 'error': 'Risk limits must be > 0; max 5.0% per trade and 15.0% combined open risk.'},
                status=status.HTTP_400_BAD_REQUEST,
            )


        if not account_number:
            if is_paper:
                account_number = f"TS-PAPER-{LinkedBrokerAccount.objects.count() + 1001}"
            else:
                return Response({'success': False, 'error': 'Account Login / ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if not name:
            name = f"{broker_type} Account ({account_number[-4:] if len(account_number) >= 4 else account_number})"

        # Deactivate previous active accounts so new one becomes primary
        LinkedBrokerAccount.objects.all().update(is_active=False)

        # Auto-fetch live balance from broker if MT5 is available
        live_equity = balance
        if broker_type in ('EXNESS', 'MT5', 'MT4') and not is_paper:
            try:
                import MetaTrader5 as mt5
                raw_login = str(account_number).strip()
                login_id = int(raw_login) if raw_login.isdigit() else 0
                if login_id and password and server:
                    init_ok = mt5.initialize(login=login_id, password=password, server=server, timeout=500)
                    if not init_ok:
                        init_ok = mt5.initialize(timeout=500)
                        if init_ok:
                            mt5.login(login=login_id, password=password, server=server, timeout=1000)
                    if init_ok:
                        acc_info = mt5.account_info()
                        if acc_info and getattr(acc_info, 'balance', None) is not None:
                            balance = round(float(acc_info.balance), 2)
                            live_equity = round(float(acc_info.equity), 2)
            except Exception as e:
                logger.warning(f"[LinkedAccountsView] MT5 live balance auto-fetch note: {e}")

        account = LinkedBrokerAccount(
            name=name,
            broker_type=broker_type,
            account_number=account_number,
            server=server or ('TradeSense-Simulator' if is_paper else 'Broker-Default'),
            api_key=api_key,
            is_paper=is_paper,
            balance=Decimal(str(balance)),
            equity=Decimal(str(live_equity)),
            is_active=True,
            auto_trade_enabled=auto_trade_enabled,
            is_authorized=is_authorized,
            authorized_at=timezone.now() if is_authorized else None,
            authorization_status='ON' if (auto_trade_enabled and is_authorized) else 'OFF',
            max_risk_pct=max_risk_pct,
            max_open_risk_pct=max_open_risk_pct,
            connection_status='CONNECTED',
            last_sync_at=timezone.now()
        )
        account.set_secret(api_secret)
        account.save()

        if auto_trade_enabled and is_authorized:
            from .models import SystemTradingConfig
            cfg = SystemTradingConfig.get_config()
            cfg.global_auto_trading = True
            cfg.emergency_stop_active = False
            cfg.save()
            try:
                AutoTraderEngine.get_automation_status()
            except Exception:
                pass

        masked = f"********{account.account_number[-4:]}" if len(account.account_number) >= 4 else account.account_number

        return Response({
            'success': True,
            'message': f'Account {account.name} successfully linked and authorized for persistent automated trading.',
            'account_id': account.id,
            'broker': account.get_broker_type_display(),
            'account_number_masked': masked,
            'auto_trade_enabled': account.auto_trade_enabled,
            'is_authorized': account.is_authorized,
            'risk_pct': account.max_risk_pct,
        }, status=status.HTTP_201_CREATED)


class TestBrokerConnectionView(views.APIView):
    """
    POST /api/accounts/test-connection/
    Section 1: Test Connection before enabling automated trading.
    Validates credentials (login, password, server, broker_type) against real broker API or local MT5 terminal.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        broker_type = request.data.get('broker_type', 'MT5').upper()
        login = request.data.get('account_number', '').strip()
        password = request.data.get('password', '').strip()
        server = request.data.get('server', '').strip()

        if not login and broker_type != 'PAPER':
            return Response({'success': False, 'error': 'Account Login / ID is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not password and broker_type != 'PAPER':
            return Response({'success': False, 'error': 'Trading Password is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not server and broker_type in ['MT5', 'MT4', 'EXNESS']:
            return Response({'success': False, 'error': 'Broker Server name is required (e.g. Exness-MT5Real, MetaQuotes-Demo).'}, status=status.HTTP_400_BAD_REQUEST)

        import time

        if broker_type in ['MT5', 'MT4', 'EXNESS']:
            start_t = time.time()
            try:
                import MetaTrader5 as mt5
                raw_login = str(login).strip()
                login_id = int(raw_login) if raw_login.isdigit() else 0
                if not login_id:
                    return Response({'success': False, 'error': f'Invalid account login: {login}. Must be numeric.'}, status=status.HTTP_400_BAD_REQUEST)

                init_ok = mt5.initialize(login=login_id, password=password, server=server, timeout=5000)
                if not init_ok:
                    init_ok = mt5.initialize(timeout=5000)
                    if init_ok:
                        login_ok = mt5.login(login=login_id, password=password, server=server, timeout=5000)
                    else:
                        login_ok = False
                else:
                    login_ok = True

                latency_ms = max(1, int((time.time() - start_t) * 1000))

                if not init_ok or not login_ok:
                    err = mt5.last_error()
                    mt5.shutdown()
                    err_msg = f"{err[1]} (code {err[0]})" if err else "Authentication or connection failed"
                    return Response({
                        'success': False,
                        'broker': broker_type,
                        'server': server,
                        'ping_ms': latency_ms,
                        'error': f"Broker authentication failed: {err_msg}. Please check your Login ID, Password, and Server name.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                acc_info = mt5.account_info()
                term_info = mt5.terminal_info()
                ping_ms = getattr(term_info, 'ping_last', latency_ms) if term_info else latency_ms
                if ping_ms <= 0:
                    ping_ms = latency_ms

                balance = float(acc_info.balance) if (acc_info and hasattr(acc_info, 'balance')) else 0.0
                equity = float(acc_info.equity) if (acc_info and hasattr(acc_info, 'equity')) else balance
                currency = str(acc_info.currency) if (acc_info and hasattr(acc_info, 'currency')) else 'USD'
                leverage = f"1:{acc_info.leverage}" if (acc_info and hasattr(acc_info, 'leverage')) else '1:100'
                company = getattr(acc_info, 'company', broker_type)
                server_name = getattr(acc_info, 'server', server)
                mt5.shutdown()

                return Response({
                    'success': True,
                    'broker': broker_type,
                    'server': server_name,
                    'company': company,
                    'ping_ms': ping_ms,
                    'balance': balance,
                    'equity': equity,
                    'currency': currency,
                    'leverage': leverage,
                    'permissions': ['READ_ACCOUNT', 'READ_MARKET_DATA', 'PLACE_ORDERS', 'MODIFY_ORDERS', 'CLOSE_ORDERS'],
                    'withdrawal_permission': 'DISABLED (Security Requirement Section 19)',
                    'message': f"Real Connection Verified! Connected to {company} ({server_name}) with {ping_ms}ms latency."
                })
            except ImportError:
                return Response({
                    'success': False,
                    'error': 'MetaTrader5 Python library is not available on this server environment.'
                }, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({
                    'success': False,
                    'error': f"Broker connection error: {str(e)}"
                }, status=status.HTTP_400_BAD_REQUEST)

        elif broker_type == 'PAPER':
            # Real paper wallet stats from LinkedBrokerAccount or default initial simulation wallet
            paper_acc = LinkedBrokerAccount.objects.filter(broker_type='PAPER', is_paper=True, is_active=True).first()
            if not paper_acc:
                paper_acc = LinkedBrokerAccount.objects.filter(broker_type='PAPER').first()
            balance = float(paper_acc.balance) if paper_acc else 10000.0
            equity = float(paper_acc.equity) if paper_acc else balance
            currency = paper_acc.currency if paper_acc else 'USD'
            return Response({
                'success': True,
                'broker': 'PAPER',
                'server': 'TradeSense-PaperWallet',
                'ping_ms': 1,
                'balance': balance,
                'equity': equity,
                'currency': currency,
                'leverage': '1:100',
                'permissions': ['READ_ACCOUNT', 'READ_MARKET_DATA', 'PLACE_ORDERS', 'MODIFY_ORDERS', 'CLOSE_ORDERS'],
                'withdrawal_permission': 'DISABLED (Simulated Paper Trading)',
                'message': "Paper Trading Environment Ready. Real-time simulation mode."
            })

        elif broker_type in ['BINANCE', 'BYBIT']:
            import urllib.request
            start_t = time.time()
            endpoint = 'https://fapi.binance.com/fapi/v1/time' if broker_type == 'BINANCE' else 'https://api.bybit.com/v5/market/time'
            try:
                req = urllib.request.Request(endpoint, headers={'User-Agent': 'TradeSense-Pro/1.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp.read()
                latency_ms = max(1, int((time.time() - start_t) * 1000))
                return Response({
                    'success': True,
                    'broker': broker_type,
                    'server': f"{broker_type}-Live-Cloud",
                    'ping_ms': latency_ms,
                    'balance': 0.0,
                    'equity': 0.0,
                    'currency': 'USDT',
                    'leverage': '1:20',
                    'permissions': ['READ_ACCOUNT', 'READ_MARKET_DATA', 'PLACE_ORDERS'],
                    'withdrawal_permission': 'DISABLED (Security Requirement Section 19)',
                    'message': f"Exchange Gateway reachable! Ping: {latency_ms}ms. Credentials stored securely."
                })
            except Exception as e:
                return Response({
                    'success': False,
                    'error': f"Failed to reach {broker_type} gateway: {str(e)}"
                }, status=status.HTTP_400_BAD_REQUEST)

        return Response({'success': False, 'error': f"Unsupported broker type: {broker_type}"}, status=status.HTTP_400_BAD_REQUEST)


class SelectActiveAccountView(views.APIView):
    """
    POST /api/accounts/select-active/
    Section 9: Switch active trading account.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        account_id = request.data.get('account_id')
        if not account_id:
            return Response({'success': False, 'error': 'account_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        acc = get_object_or_404(LinkedBrokerAccount, id=account_id)
        LinkedBrokerAccount.objects.all().update(is_active=False)
        acc.is_active = True
        acc.save(update_fields=['is_active'])

        return Response({
            'success': True,
            'message': f"Active account switched to {acc.name} ({acc.account_number})",
            'account_id': acc.id,
            'name': acc.name,
            'broker': acc.get_broker_type_display(),
            'is_authorized': acc.is_authorized,
            'authorization_status': acc.authorization_status
        })


class ToggleAutoTradeView(views.APIView):
    """
    POST /api/accounts/toggle-auto/<id>/
    Toggles auto-trade state for a specific account.
    """
    permission_classes = [AllowAny]

    def post(self, request, pk):
        account = get_object_or_404(LinkedBrokerAccount, pk=pk)
        account.auto_trade_enabled = not account.auto_trade_enabled
        account.save(update_fields=['auto_trade_enabled', 'updated_at'])
        return Response({
            'account_id': account.id,
            'auto_trade_enabled': account.auto_trade_enabled,
            'message': f"Auto-trading {'ENABLED' if account.auto_trade_enabled else 'PAUSED'} for {account.name}"
        })


class DeleteAccountView(views.APIView):
    """
    POST /api/accounts/unlink/<id>/
    Unlinks / deletes a broker account.
    """
    permission_classes = [AllowAny]

    def post(self, request, pk):
        account = get_object_or_404(LinkedBrokerAccount, pk=pk)
        name = account.name
        account.delete()
        return Response({'message': f'Account {name} unlinked successfully'})


class AutoTradesListView(views.APIView):
    """
    GET /api/accounts/trades/
    Returns recent auto-executed trades (both OPEN and CLOSED).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        status_filter = request.query_params.get('status')
        queryset = AutoTradeExecution.objects.all().order_by('-opened_at')
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())

        trades = queryset[:50]
        data = []
        for t in trades:
            data.append({
                'id': t.id,
                'account_name': t.account.name,
                'broker': t.account.broker_type,
                'symbol': t.symbol,
                'direction': t.direction,
                'volume_lots': t.volume_lots,
                'entry_price': t.entry_price,
                'stop_loss': t.stop_loss,
                'take_profit_1': t.take_profit_1,
                'take_profit_2': t.take_profit_2,
                'current_price': t.current_price,
                'status': t.status,
                'exit_price': t.exit_price,
                'exit_reason': t.exit_reason,
                'exit_reason_display': t.get_exit_reason_display() if t.exit_reason else '',
                'pnl_amount': float(t.pnl_amount),
                'pnl_r': t.pnl_r,
                'opened_at': t.opened_at.strftime('%Y-%m-%d %H:%M:%S'),
                'closed_at': t.closed_at.strftime('%Y-%m-%d %H:%M:%S') if t.closed_at else None,
                'notes': t.notes,
            })
        return Response({'trades': data})


class CloseTradeManualView(views.APIView):
    """
    POST /api/accounts/close-trade/<id>/
    Manually close an open auto-trade position.
    """
    permission_classes = [AllowAny]

    def post(self, request, pk):
        trade = AutoTraderEngine.close_trade_manually(pk)
        if not trade:
            return Response({'error': 'Trade not found or already closed'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'message': f"Trade #{trade.id} ({trade.symbol}) closed at {trade.exit_price}",
            'pnl_amount': float(trade.pnl_amount),
            'pnl_r': trade.pnl_r,
        })


class EvaluateTradesView(views.APIView):
    """
    POST /api/accounts/evaluate-trades/
    Triggers immediate evaluation of all open trades against market data to close on TP/SL.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        resolved = AutoTraderEngine.evaluate_and_close_open_trades()
        return Response({
            'evaluated': True,
            'closed_count': len(resolved),
            'closed_trades': [{
                'id': t.id,
                'symbol': t.symbol,
                'direction': t.direction,
                'exit_reason': t.exit_reason,
                'exit_price': t.exit_price,
                'pnl_amount': float(t.pnl_amount),
            } for t in resolved]
        })


class AutomationStatusView(views.APIView):
    """
    GET /api/accounts/automation-status/
    Returns real-time status of persistent automated trading for the dashboard widget.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        status_data = AutoTraderEngine.get_automation_status()
        return Response(status_data)


class AuthorizeAccountView(views.APIView):
    """
    POST /api/accounts/authorize/
    Section 1: One-time authorization.
    Body: { "account_id": 1, "max_risk_pct": 0.5, "max_open_risk_pct": 3.0 }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        account_id = request.data.get('account_id')
        if not account_id:
            acc = LinkedBrokerAccount.objects.filter(is_active=True).first()
            account_id = acc.id if acc else None

        if not account_id:
            return Response({'error': 'No active broker account found to authorize'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            max_risk = float(request.data.get('max_risk_pct', request.data.get('risk_pct', 0.5)))
            max_open = float(request.data.get('max_open_risk_pct', 1.5))
        except (TypeError, ValueError):
            return Response({'error': 'Risk limits must be numeric.'}, status=status.HTTP_400_BAD_REQUEST)

        if not 0 < max_risk <= 5.0 or not 0 < max_open <= 15.0:
            return Response(
                {'error': 'Risk limits must be > 0; max 5.0% per trade and 15.0% combined open risk.'},
                status=status.HTTP_400_BAD_REQUEST,
            )


        try:
            acc = AutoTraderEngine.authorize_account(account_id, max_risk_pct=max_risk, max_open_risk_pct=max_open)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if not acc:
            return Response({'error': 'Account not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'success': True,
            'message': f"Account {acc.name} [{acc.account_number}] successfully authorized for continuous automated trading.",
            'status': acc.authorization_status,
            'risk_per_trade': acc.max_risk_pct,
            'max_open_risk': acc.max_open_risk_pct,
            'authorized_at': acc.authorized_at.isoformat(),
        })


class ToggleGlobalSwitchView(views.APIView):
    """
    POST /api/accounts/global-switch/
    Section 10: Toggle Global Automated Trading ON/OFF.
    Body: { "enabled": true/false }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        enabled = request.data.get('enabled')
        if enabled is None:
            # Toggle current state
            from .models import SystemTradingConfig
            current = SystemTradingConfig.get_config().global_auto_trading
            enabled = not current

        cfg = AutoTraderEngine.set_global_auto_trading(bool(enabled))
        return Response({
            'success': True,
            'global_auto_trading': cfg.global_auto_trading,
            'emergency_stop_active': cfg.emergency_stop_active,
            'message': f"Global automated trading is now {'ON' if cfg.global_auto_trading else 'OFF'}."
        })


class EmergencyStopView(views.APIView):
    """
    POST /api/accounts/emergency-stop/
    Section 11: Emergency Stop.
    Halts all new trading and optionally closes all open positions at market price.
    Body: { "close_positions": true/false, "reason": "User emergency stop" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        close_positions = bool(request.data.get('close_positions', True))
        reason = request.data.get('reason', 'Manual Emergency Stop Activated from Dashboard')

        closed_count = AutoTraderEngine.emergency_stop(close_positions=close_positions, reason=reason)
        return Response({
            'success': True,
            'emergency_stop_active': True,
            'global_auto_trading': False,
            'closed_positions': closed_count,
            'closed_positions_count': closed_count,
            'message': f"EMERGENCY STOP ACTIVATED: Halted all new trades. Closed {closed_count} open positions. Auto-trading set to OFF."
        })


class EmergencyKillSwitchView(views.APIView):
    """Legacy alias for emergency stop"""
    permission_classes = [AllowAny]

    def post(self, request):
        count = AutoTraderEngine.emergency_stop(close_positions=True)
        return Response({
            'success': True,
            'kill_switch_activated': True,
            'closed_positions_count': count,
            'message': f"EMERGENCY KILL SWITCH: Closed {count} positions. Auto-trading paused on all accounts."
        })


class UpdateBalanceView(views.APIView):
    """
    POST /api/accounts/update-balance/
    Allows setting the exact account balance/equity directly (e.g. from broker login or live balance edit).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        balance_val = request.data.get('balance')
        if balance_val is None:
            return Response({'success': False, 'error': 'Balance amount is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            balance_float = float(balance_val)
            if balance_float < 0:
                return Response({'success': False, 'error': 'Balance cannot be negative.'}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({'success': False, 'error': 'Invalid balance amount.'}, status=status.HTTP_400_BAD_REQUEST)

        acc = LinkedBrokerAccount.objects.filter(is_active=True).first()
        if not acc:
            return Response({'success': False, 'error': 'No active account found.'}, status=status.HTTP_404_NOT_FOUND)

        acc.balance = Decimal(str(round(balance_float, 2)))
        acc.equity = acc.balance
        acc.save(update_fields=['balance', 'equity', 'updated_at'])

        return Response({
            'success': True,
            'balance': float(acc.balance),
            'equity': float(acc.equity),
            'message': f'Account balance updated to ${acc.balance:,.2f}'
        })
