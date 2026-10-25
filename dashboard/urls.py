from django.urls import path
from . import views, agent_views, copilot_views

app_name = 'dashboard'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='home'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('api/agents/status/', agent_views.agent_status, name='agent-status'),
    path('api/copilot/chat/', copilot_views.copilot_chat, name='copilot-chat'),
]

