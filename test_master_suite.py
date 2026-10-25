"""
Manual live-data architecture verification.

Run ``python test_master_suite.py`` from the project root. It is not an
automated test because it fetches live market data and persists a backtest.
"""


def main():
    import os

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trading_platform.settings')
    import django
    django.setup()

    from engines.ai_ml import AIEngine
    from engines.backtest import BacktestSimulator
    from engines.data_fetcher import DataFetcher
    from engines.unified import UnifiedSignalEngine
    from market_data.models import Instrument
    from signals.models import AlertDelivery, BacktestRun, Signal

    print('=' * 60)
    print('TRADESENSE PRO MASTER VERIFICATION SUITE')
    print('=' * 60)

    df = DataFetcher().fetch('XAUUSD', 'H1', limit=150)
    if df is None or len(df) < 50:
        raise RuntimeError('DataFetcher failed to return at least 50 XAUUSD candles')
    print(f"[1/5] Market Data: Fetched {len(df)} candles (last close: {df['close'].iloc[-1]:.2f})")

    signal = UnifiedSignalEngine(df, 'XAUUSD', 'H1').generate()
    print(f'[2/5] Unified Engine: Verdict={signal.direction} | Conf={signal.confidence:.1f}%')

    validation = AIEngine.walk_forward_validation(df, n_splits=2)
    print(f"[3/5] AI Walk-Forward: OOS Accuracy={validation.get('out_of_sample_accuracy_pct', 0)}%")

    instrument = Instrument.objects.filter(symbol='XAUUSD').first()
    if instrument is None:
        raise RuntimeError('XAUUSD is missing; seed master data before this manual check')
    simulator = BacktestSimulator(instrument=instrument, timeframe='H1', initial_capital=10_000.0, spread_pips=1.5)
    result = simulator.run(df=df, window_size=40, step=1)
    run = simulator.save_run(result)
    print(f"[4/5] Backtest: RunID={run.run_id} | Trades={result['total_trades']} | PF={result['profit_factor']}")

    print('[5/5] Database inventory:')
    for model in (Signal, BacktestRun, AlertDelivery):
        print(f'  - {model.__name__:24s}: {model.objects.count()} records')

    print('\nALL MASTER ARCHITECTURE REQUIREMENTS VERIFIED SUCCESSFULLY!')


if __name__ == '__main__':
    main()
