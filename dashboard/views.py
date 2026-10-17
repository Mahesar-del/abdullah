"""
Dashboard View - Serves the main HTML frontend
"""
from django.views import View
from django.shortcuts import render
from rest_framework.permissions import AllowAny


class DashboardView(View):
    def get(self, request):
        return render(request, 'dashboard/index.html')
