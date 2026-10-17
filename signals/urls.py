from django.urls import path
from . import views
from .generator_views import (
    GenerateSignalView,
    BulkGenerateView,
    RunBacktestView,
    BacktestHistoryView,
    WalkForwardValidationView,
    AlertLogsView,
)

app_name = 'signals'

urlpatterns = [
    path('',                  views.SignalListView.as_view(),          name='list'),
    path('<int:pk>/',         views.SignalDetailView.as_view(),        name='detail'),
    path('<int:pk>/chart/',   views.SignalChartView.as_view(),         name='chart'),
    path('active/',           views.ActiveSignalsView.as_view(),       name='active'),
    path('stats/',            views.SignalStatsView.as_view(),         name='stats'),
    path('news-events/',      views.NewsEventListView.as_view(),       name='news-events'),

    # Signal Generation & Orchestration
    path('generate/',         GenerateSignalView.as_view(),            name='generate'),
    path('bulk-generate/',    BulkGenerateView.as_view(),              name='bulk-generate'),

    # Phase 11 Backtesting & Phase 10 Validation
    path('backtest/',         RunBacktestView.as_view(),               name='backtest'),
    path('backtest/history/', BacktestHistoryView.as_view(),           name='backtest-history'),
    path('walk-forward/',     WalkForwardValidationView.as_view(),     name='walk-forward'),
    path('alert-logs/',       AlertLogsView.as_view(),                 name='alert-logs'),
]


