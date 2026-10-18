"""
Accounts App URL Configuration
"""
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Linked Broker Accounts & Automation Authorization
    path('linked/', views.LinkedAccountsView.as_view(), name='linked-accounts'),
    path('test-connection/', views.TestBrokerConnectionView.as_view(), name='test-connection'),
    path('select-active/', views.SelectActiveAccountView.as_view(), name='select-active'),
    path('toggle-auto/<int:pk>/', views.ToggleAutoTradeView.as_view(), name='toggle-auto'),
    path('unlink/<int:pk>/', views.DeleteAccountView.as_view(), name='unlink-account'),
    path('automation-status/', views.AutomationStatusView.as_view(), name='automation-status'),
    path('authorize/', views.AuthorizeAccountView.as_view(), name='authorize-account'),
    path('global-switch/', views.ToggleGlobalSwitchView.as_view(), name='global-switch'),
    path('emergency-stop/', views.EmergencyStopView.as_view(), name='emergency-stop'),

    # Auto-Executed Trades
    path('trades/', views.AutoTradesListView.as_view(), name='auto-trades'),
    path('close-trade/<int:pk>/', views.CloseTradeManualView.as_view(), name='close-trade'),
    path('evaluate-trades/', views.EvaluateTradesView.as_view(), name='evaluate-trades'),
    path('kill-switch/', views.EmergencyKillSwitchView.as_view(), name='kill-switch'),
    path('update-balance/', views.UpdateBalanceView.as_view(), name='update-balance'),
]
