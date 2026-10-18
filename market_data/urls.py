from django.urls import path
from . import views

app_name = 'market_data'

urlpatterns = [
    path('instruments/',        views.InstrumentListView.as_view(),  name='instruments'),
    path('instruments/<str:symbol>/', views.InstrumentDetailView.as_view(), name='instrument-detail'),
    path('ohlcv/',              views.OHLCVView.as_view(),           name='ohlcv'),
    path('sessions/',           views.MarketSessionView.as_view(),   name='sessions'),
    path('live-tick/',          views.LiveTickView.as_view(),        name='live-tick'),
    path('live-chart/',         views.LiveSymbolChartView.as_view(), name='live-chart'),
]
