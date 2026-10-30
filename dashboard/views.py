"""
Dashboard View - Serves the main HTML frontend
"""
from django.views import View
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework.permissions import AllowAny
from pathlib import Path
import json


class DashboardView(View):
    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return render(request, 'dashboard/index.html')


def historical_audit_results(request):
    """
    Dedicated endpoint returning 2021-2022 Causal Walk-Forward Audit
    Completely isolated from live trading signals.
    """
    from django.http import JsonResponse
    try:
        from engines.historical_audit import load_audit_results, run_causal_walk_forward_audit
        force = request.GET.get('recalculate', 'false').lower() == 'true'
        if force:
            data = run_causal_walk_forward_audit()
        else:
            data = load_audit_results()
        data['validation_status'] = 'SYNTHETIC_REPLAY_NOT_LIVE_VALIDATED'
        data['validation_warning'] = 'Daily OHLC was used to synthesize intraday paths; this is not real intraday validation.'
        if isinstance(data.get('summary'), dict):
            data['summary']['zero_lookahead_verified'] = False
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'status': 'ERROR', 'message': str(e)}, status=500)


def ict_location_historical_results(request):
    """Read-only dashboard projection of the causal ICT research replay.

    This intentionally never reads/writes Signal or AutoTradeExecution rows:
    historical research must not contaminate the live or paper trade ledger.
    """
    from django.conf import settings
    from django.http import JsonResponse

    report = Path(settings.BASE_DIR) / 'quant_reports' / 'walkforward_ict_location_xauusd_2006_2025.json'
    log = report.with_suffix('.log')
    if not report.exists():
        return JsonResponse({
            'status': 'PROCESSING' if log.exists() else 'UNAVAILABLE',
            'message': ('ICT causal replay is still processing. Results appear only after a complete run.'
                        if log.exists() else 'No completed ICT causal replay is available.'),
            'requested_window': '2015-01-01 to 2025-12-31',
            'source_limit': '2026 full public history is unavailable; it is not fabricated.',
        })
    try:
        raw = json.loads(report.read_text(encoding='utf-8'))
        start, end = '2015-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
        trades = [item for item in raw.get('trades', []) if start <= str(item.get('entry_at', '')) < end]
        wins = sum(float(item.get('pnl_r', 0)) > 0 for item in trades)
        losses = sum(float(item.get('pnl_r', 0)) < 0 for item in trades)
        breakeven = len(trades) - wins - losses
        net_r = sum(float(item.get('pnl_r', 0)) for item in trades)
        gains = sum(float(item.get('pnl_r', 0)) for item in trades if float(item.get('pnl_r', 0)) > 0)
        loss_r = -sum(float(item.get('pnl_r', 0)) for item in trades if float(item.get('pnl_r', 0)) < 0)
        dashboard_trades = [{
            'id': item.get('id'), 'date': item.get('entry_at'), 'symbol': item.get('symbol'),
            'direction': item.get('direction'), 'entry': float(item.get('entry_price', 0)),
            'sl': float(item.get('initial_stop', 0)), 'tp1': float(item.get('take_profit', 0)),
            'exit_price': float(item.get('exit_price', 0)), 'r_multiple': round(float(item.get('pnl_r', 0)), 4),
            'outcome': 'WIN' if float(item.get('pnl_r', 0)) > 0 else 'LOSS' if float(item.get('pnl_r', 0)) < 0 else 'BREAKEVEN',
            'exit_reason': item.get('exit_reason'), 'setup_type': item.get('setup_type'),
        } for item in trades]
        return JsonResponse({
            'status': 'SUCCESS', 'strategy': raw.get('source', {}).get('strategy', 'ict_location'),
            'requested_window': '2015-01-01 to 2025-12-31',
            'source_limit': '2026 full public history is unavailable; it is not fabricated.',
            'research_only': True, 'trades': dashboard_trades,
            'summary': {
                'total_trades': len(trades), 'winning_trades': wins, 'losing_trades': losses,
                'breakeven_trades': breakeven, 'win_rate_pct': round(100 * wins / len(trades), 2) if trades else None,
                'net_r': round(net_r, 4), 'profit_factor': round(gains / loss_r, 4) if loss_r else None,
            },
            'methodology': raw.get('metadata', {}), 'source': raw.get('source', {}),
        })
    except (OSError, ValueError, TypeError) as exc:
        return JsonResponse({'status': 'ERROR', 'message': str(exc)}, status=500)


def course_price_action_backtest_results(request):
    """Read-only dashboard status for the 4H/1H/15m/5m course research replay."""
    from django.conf import settings
    from django.http import JsonResponse
    report = Path(settings.BASE_DIR) / 'quant_reports' / 'walkforward_xauusd_course_price_action_2023_2026.json'
    run_log = Path(settings.BASE_DIR) / 'quant_reports' / 'course_price_action_2023_2026_run.log'
    if not report.exists():
        return JsonResponse({'status': 'PROCESSING' if run_log.exists() else 'UNAVAILABLE',
                             'message': '4H → 1H → 15m → 5m causal backtest is running; metrics appear only after completion.'})
    try:
        raw = json.loads(report.read_text(encoding='utf-8'))
        return JsonResponse({'status': 'SUCCESS', 'summary': raw.get('summary', {}),
                             'metadata': raw.get('metadata', {}), 'source': raw.get('source', {}),
                             'research_only': True})
    except (OSError, ValueError, TypeError) as exc:
        return JsonResponse({'status': 'ERROR', 'message': str(exc)}, status=500)

