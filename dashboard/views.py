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
