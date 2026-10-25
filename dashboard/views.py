"""
Dashboard View - Serves the main HTML frontend
"""
from django.views import View
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework.permissions import AllowAny


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
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'status': 'ERROR', 'message': str(e)}, status=500)

