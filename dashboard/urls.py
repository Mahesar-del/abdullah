from django.urls import path
from . import views, agent_views, copilot_views

app_name = 'dashboard'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='home'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('api/agents/status/', agent_views.agent_status, name='agent-status'),
    path('api/copilot/chat/', copilot_views.copilot_chat, name='copilot-chat'),
    path('api/historical-audit/results/', views.historical_audit_results, name='historical-audit-results'),
    path('api/ict-location-historical/results/', views.ict_location_historical_results, name='ict-location-historical-results'),
    path('api/course-price-action-backtest/results/', views.course_price_action_backtest_results, name='course-price-action-backtest-results'),
]


