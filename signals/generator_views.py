"""
Signal Generator API View — Phase 2
Endpoint: POST /api/signals/generate/
Fetches live data → runs engines → saves signal → returns result
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.utils import timezone

import pandas as pd
import sys
import os

# Add project root to path for engines module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.unified import UnifiedSignalEngine
from engines.data_fetcher import DataFetcher
from market_data.models import Instrument
from .models import Signal
from .serializers import SignalDetailSerializer
from .strategy_pipeline import prepare_setup, validate_proposal, record_status, create_signal_once
from engines.institutional_setup import normalize_symbol, normalize_timeframe

ALLOWED_SYMBOLS = {'XAUUSD', 'US30', 'SPX500'}
ALLOWED_TIMEFRAMES = {'M15', 'H1', 'H4'}


def _is_in_killzone(now):
    """London [07:00, 11:00) or New York [13:00, 17:00), all in UTC."""
    return (7 <= now.hour < 11) or (13 <= now.hour < 17)


def _golden_alignment(fetcher, symbol, timeframe, direction, current_df=None):
    """Require Close > EMA50 > EMA200 (or inverse) on every approved timeframe."""
    for tf in sorted(ALLOWED_TIMEFRAMES):
        df = current_df if tf == timeframe else fetcher.fetch(symbol, tf, limit=200)
        if df is None or len(df) < 200 or 'close' not in df:
            return False, f'Insufficient {tf} data for multi-timeframe trend confirmation.'
        close_series = df['close']
        close = float(close_series.iloc[-1])
        ema50 = float(close_series.ewm(span=50, adjust=False).mean().iloc[-1])
        ema200 = float(close_series.ewm(span=200, adjust=False).mean().iloc[-1])
        aligned = (close > ema50 > ema200) if direction == 'BUY' else (close < ema50 < ema200)
        if not aligned:
            return False, (
                f'{tf} not aligned: Close {close:.2f}, EMA50 {ema50:.2f}, EMA200 {ema200:.2f}.'
            )
    return True, ''


class GenerateSignalView(APIView):
    """
    POST /api/signals/generate/
    Body: { "symbol": "XAUUSD", "timeframe": "H1" }
    Fetches live data, runs all engines, saves & returns signal.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        symbol    = normalize_symbol(request.data.get('symbol', 'XAUUSD'))
        timeframe = normalize_timeframe(request.data.get('timeframe', 'H1'))

        if symbol not in ALLOWED_SYMBOLS:
            return Response({'error': 'Only XAUUSD, US30, and SPX500 are permitted.'}, status=status.HTTP_400_BAD_REQUEST)
        if timeframe not in ALLOWED_TIMEFRAMES:
            return Response({'error': 'Only M15, H1, and H4 timeframes are permitted.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate instrument
        try:
            instrument = Instrument.objects.get(symbol=symbol)
        except Instrument.DoesNotExist:
            return Response(
                {'error': f"Unknown symbol: {symbol}. Check /api/market/instruments/ for valid symbols."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fetch market data
        fetcher = DataFetcher()
        frames, df, candidate, quote = prepare_setup(fetcher, symbol, timeframe)
        if not candidate.allowed:
            return Response({'direction': 'WAIT', 'symbol': symbol, 'timeframe': timeframe,
                             'message': '; '.join(candidate.reasons), 'setup': candidate.to_dict()})

        # Run Unified Signal Engine
        engine = UnifiedSignalEngine(df, symbol, timeframe, execution_quote=quote)
        try:
            unified = engine.generate()
        except Exception as e:
            return Response(
                {'error': f'Engine error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        decision = validate_proposal(frames, symbol, timeframe, unified, quote)
        if not decision.allowed:
            return Response({'direction': 'WAIT', 'confidence': unified.confidence,
                             'symbol': symbol, 'timeframe': timeframe,
                             'message': '; '.join(decision.reasons), 'setup': decision.to_dict()})
        setup_bar = df.index[-1].to_pydatetime()
        if Signal.objects.filter(instrument=instrument, timeframe=timeframe, setup_bar_opened_at=setup_bar).exists():
            return Response({'direction': 'WAIT', 'message': 'This completed setup candle was already processed.'})

        # Prevent duplicate active signals for the same pair/timeframe/direction
        if Signal.objects.filter(
            instrument=instrument,
            timeframe=unified.timeframe,
            direction=unified.direction,
            status='ACTIVE'
        ).exists():
            return Response({
                'direction': unified.direction,
                'confidence': unified.confidence,
                'symbol': symbol,
                'timeframe': timeframe,
                'message': 'An active signal already exists for this pair, timeframe, and direction.',
            })

        # Save signal to DB
        signal = create_signal_once(
            instrument          = instrument,
            timeframe           = unified.timeframe,
            direction           = unified.direction,
            strength            = unified.strength,
            status              = 'ACTIVE',
            entry_price         = unified.entry,
            stop_loss           = unified.stop_loss,
            take_profit_1       = unified.take_profit_1,
            take_profit_2       = None,
            take_profit_3       = None,
            risk_reward         = unified.risk_reward,
            confidence_score    = unified.confidence,
            technical_score     = unified.technical_score,
            smc_score           = unified.smc_score,
            price_action_score  = unified.price_action_score,
            macro_score         = unified.macro_score,
            news_score          = unified.news_score,
            institutional_score = unified.institutional_score,
            intermarket_score   = getattr(unified, 'intermarket_score', 50.0),
            ai_ml_score         = unified.ai_ml_score,
            engine_detail       = getattr(unified, 'engine_results', {}) or {},
            analysis_summary    = unified.analysis,
            warnings            = unified.warnings,
            decision_class      = getattr(unified, 'decision_class', 'STRONG'),
            market_regime       = getattr(unified, 'market_regime', 'TRENDING'),
            independent_groups  = getattr(unified, 'independent_groups', {}),
            is_trade_allowed    = getattr(unified, 'is_trade_allowed', True),
            recommended_lots    = getattr(unified, 'recommended_lots', 0.10),
            data_quality_score  = unified.data_quality_score,
            risk_rejection_reasons = unified.risk_rejection_reasons,
            strategy_evidence   = decision.to_dict(),
            setup_bar_opened_at = setup_bar,
            valid_until         = timezone.now() + self._get_validity(timeframe),
        )
        if signal is None:
            return Response({'direction': 'WAIT', 'message': 'Setup already persisted by another request.'})
        
        # Auto-Trader Hook: Automatically execute trade if account has auto-trading enabled
        from accounts.auto_trader import AutoTraderEngine
        auto_trades = []
        if signal.direction in ['BUY', 'SELL']:
            try:
                auto_trades = AutoTraderEngine.execute_for_signal(signal)
            except Exception:
                pass

        # Send Notification
        from signals.notifications import notifier
        if signal.direction != 'WAIT':
            try:
                notifier.send_signal(signal)
            except Exception:
                pass

        serializer = SignalDetailSerializer(signal)
        return Response({
            'status':        'Signal generated successfully',
            'signal':        serializer.data,
            'engine_detail': unified.engine_results,
            'auto_trades_opened': len(auto_trades),
        }, status=status.HTTP_201_CREATED)

    def _get_validity(self, timeframe):
        return get_signal_validity(timeframe)


def get_signal_validity(timeframe):
    """How long a signal is valid based on timeframe"""
    from datetime import timedelta
    validity_map = {
        'M1': timedelta(minutes=15),   'M5': timedelta(hours=1),
        'M15': timedelta(hours=4),     'M30': timedelta(hours=8),
        'H1': timedelta(hours=24),     'H2': timedelta(hours=48),
        'H4': timedelta(hours=96),
        'D1': timedelta(days=7),       'W1': timedelta(days=30),
    }
    return validity_map.get(str(timeframe).upper(), timedelta(hours=24))


class BulkGenerateView(APIView):
    """
    POST /api/signals/bulk-generate/
    Generates signals for multiple symbols at once.
    Body: { "symbols": ["XAUUSD", "EURUSD"], "timeframe": "H1" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        symbols   = request.data.get('symbols', ['XAUUSD', 'US30', 'SPX500'])
        timeframe = normalize_timeframe(request.data.get('timeframe', 'H1'))

        if timeframe not in ALLOWED_TIMEFRAMES:
            return Response({'error': 'Only M15, H1, and H4 timeframes are permitted.'}, status=status.HTTP_400_BAD_REQUEST)

        results = []
        fetcher = DataFetcher()

        for symbol in symbols[:10]:  # max 10 at once
            symbol = normalize_symbol(symbol)
            try:
                if symbol not in ALLOWED_SYMBOLS:
                    results.append({'symbol': symbol, 'status': 'error', 'message': 'Symbol is outside the allowed institutional universe'})
                    continue
                instrument = Instrument.objects.get(symbol=symbol)
                frames, df, candidate, quote = prepare_setup(fetcher, symbol, timeframe)
                if not candidate.allowed:
                    results.append({'symbol': symbol, 'status': 'skipped', 'reason': '; '.join(candidate.reasons)})
                    continue

                engine  = UnifiedSignalEngine(df, symbol, timeframe, execution_quote=quote)
                unified = engine.generate()
                decision = validate_proposal(frames, symbol, timeframe, unified, quote)
                if not decision.allowed:
                    results.append({'symbol': symbol, 'status': 'skipped', 'reason': '; '.join(decision.reasons)})
                    continue
                setup_bar = df.index[-1].to_pydatetime()
                if Signal.objects.filter(instrument=instrument, timeframe=timeframe, setup_bar_opened_at=setup_bar).exists():
                    results.append({'symbol': symbol, 'status': 'skipped', 'reason': 'Setup candle already processed'})
                    continue

                # Don't stack identical trades: skip if the same pair/timeframe/direction is still running
                if Signal.objects.filter(instrument=instrument, timeframe=unified.timeframe,
                                         direction=unified.direction, status='ACTIVE').exists():
                    results.append({'symbol': symbol, 'status': 'success', 'direction': unified.direction,
                                    'confidence': unified.confidence, 'duplicate': True})
                    continue

                signal = create_signal_once(
                    instrument          = instrument,
                    timeframe           = unified.timeframe,
                    direction           = unified.direction,
                    strength            = unified.strength,
                    status              = 'ACTIVE',
                    entry_price         = unified.entry,
                    stop_loss           = unified.stop_loss,
                    take_profit_1       = unified.take_profit_1,
                    take_profit_2       = None,
                    take_profit_3       = None,
                    risk_reward         = unified.risk_reward,
                    confidence_score    = unified.confidence,
                    technical_score     = unified.technical_score,
                    smc_score           = unified.smc_score,
                    price_action_score  = unified.price_action_score,
                    macro_score         = unified.macro_score,
                    news_score          = unified.news_score,
                    institutional_score = unified.institutional_score,
                    ai_ml_score         = unified.ai_ml_score,
                    analysis_summary    = unified.analysis,
                    warnings            = unified.warnings,
                    decision_class      = getattr(unified, 'decision_class', 'STRONG'),
                    market_regime       = getattr(unified, 'market_regime', 'TRENDING'),
                    independent_groups  = getattr(unified, 'independent_groups', {}),
                    is_trade_allowed    = getattr(unified, 'is_trade_allowed', True),
                    recommended_lots    = getattr(unified, 'recommended_lots', 0.10),
                    data_quality_score  = unified.data_quality_score,
                    risk_rejection_reasons = unified.risk_rejection_reasons,
                    engine_detail       = unified.engine_results,
                    strategy_evidence   = decision.to_dict(),
                    setup_bar_opened_at = setup_bar,
                    valid_until         = timezone.now() + self._get_validity(timeframe),
                )
                if signal is None:
                    results.append({'symbol': symbol, 'status': 'skipped', 'reason': 'Setup already persisted by another request'})
                    continue
                
                # Auto-Trader Hook: Automatically execute trade if account has auto-trading enabled
                from accounts.auto_trader import AutoTraderEngine
                auto_trades_cnt = 0
                if signal.direction in ['BUY', 'SELL']:
                    try:
                        executed = AutoTraderEngine.execute_for_signal(signal)
                        auto_trades_cnt = len(executed)
                    except Exception:
                        pass

                # Send Notifications (Telegram & WhatsApp)
                from signals.notifications import notifier, telegram_notifier
                if signal.direction != 'WAIT':
                    try:
                        notifier.send_signal(signal)
                        telegram_notifier.send_signal(signal)
                    except Exception:
                        pass

                results.append({
                    'symbol':             symbol,
                    'status':             'success',
                    'direction':          unified.direction,
                    'confidence':         unified.confidence,
                    'signal_id':          signal.id,
                    'auto_trades_opened': auto_trades_cnt,
                })

            except Instrument.DoesNotExist:
                results.append({'symbol': symbol, 'status': 'error', 'message': 'Unknown symbol'})
            except Exception as e:
                results.append({'symbol': symbol, 'status': 'error', 'message': str(e)[:100]})

        return Response({'results': results, 'timeframe': timeframe})

    def _get_validity(self, timeframe):
        return get_signal_validity(timeframe)


class RunBacktestView(APIView):
    """
    POST /api/signals/backtest/
    Body: { "symbol": "XAUUSD", "timeframe": "H1", "initial_capital": 10000, "spread_pips": 1.5 }
    Executes historical replay backtest and records BacktestRun.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        symbol = request.data.get('symbol', 'XAUUSD').upper()
        timeframe = request.data.get('timeframe', 'H1').upper()
        initial_capital = float(request.data.get('initial_capital', 10000.0))
        spread_pips = float(request.data.get('spread_pips', 1.5))
        slippage_pips = float(request.data.get('slippage_pips', 0.5))

        try:
            instrument = Instrument.objects.get(symbol=symbol)
        except Instrument.DoesNotExist:
            return Response({'error': f'Instrument {symbol} not found'}, status=status.HTTP_404_NOT_FOUND)

        fetcher = DataFetcher()
        df = fetcher.fetch(symbol, timeframe, limit=300)
        if df is None or len(df) < 70:
            return Response({'error': f'Insufficient historical data for {symbol}'}, status=status.HTTP_400_BAD_REQUEST)

        from engines.backtest import BacktestSimulator
        simulator = BacktestSimulator(
            instrument=instrument,
            timeframe=timeframe,
            initial_capital=initial_capital,
            spread_pips=spread_pips,
            slippage_pips=slippage_pips,
        )

        try:
            results = simulator.run(df=df, window_size=50, step=1)
            saved_run = simulator.save_run(results)
            results['run_id'] = saved_run.run_id
            return Response(results, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f'Backtest simulation error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BacktestHistoryView(APIView):
    """
    GET /api/signals/backtest/history/
    Returns list of recent Backtest runs.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from .models import BacktestRun
        runs = BacktestRun.objects.all().order_by('-created_at')[:20]
        data = []
        for r in runs:
            data.append({
                'run_id': r.run_id,
                'symbol': r.instrument.symbol,
                'timeframe': r.timeframe,
                'initial_capital': r.initial_capital,
                'final_capital': r.final_capital,
                'win_rate_pct': r.win_rate_pct,
                'profit_factor': r.profit_factor,
                'max_drawdown_pct': r.max_drawdown_pct,
                'total_trades': r.total_trades,
                'winning_trades': r.winning_trades,
                'losing_trades': r.losing_trades,
                'expectancy_r': r.expectancy_r,
                'average_r': r.average_r,
                'sharpe_ratio': r.sharpe_ratio,
                'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        return Response({'runs': data})


class WalkForwardValidationView(APIView):
    """
    POST /api/signals/walk-forward/
    Body: { "symbol": "XAUUSD", "timeframe": "H1", "splits": 3 }
    Executes walk-forward out-of-sample ML validation without look-ahead bias.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        symbol = request.data.get('symbol', 'XAUUSD').upper()
        timeframe = request.data.get('timeframe', 'H1').upper()
        splits = int(request.data.get('splits', 3))

        fetcher = DataFetcher()
        df = fetcher.fetch(symbol, timeframe, limit=300)
        if df is None or len(df) < 100:
            return Response({'error': 'Insufficient data for walk-forward validation (<100 bars)'}, status=status.HTTP_400_BAD_REQUEST)

        from engines.ai_ml import AIEngine
        res = AIEngine.walk_forward_validation(df, n_splits=splits)
        res['symbol'] = symbol
        res['timeframe'] = timeframe
        return Response(res, status=status.HTTP_200_OK)


class AlertLogsView(APIView):
    """
    GET /api/signals/alert-logs/
    Returns recent AlertDelivery logs across Telegram, Dashboard, etc.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from .models import AlertDelivery
        logs = AlertDelivery.objects.all().order_by('-sent_at')[:30]
        data = [{
            'id': l.id,
            'channel': l.channel,
            'recipient': l.recipient,
            'title': l.title,
            'status': l.status,
            'sent_at': l.sent_at.strftime('%Y-%m-%d %H:%M:%S'),
        } for l in logs]
        return Response({'logs': data})

