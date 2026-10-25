import sys
sys.path.insert(0, '.')
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trading_platform.settings')
django.setup()

from engines.data_fetcher import DataFetcher
from engines.unified import UnifiedSignalEngine

def main():
    """Run a live engine smoke check; this is intentionally not an automated test."""
    print('Testing DataFetcher + Unified Engine...')
    fetcher = DataFetcher()
    df = fetcher.fetch('XAUUSD', 'H1', limit=200)
    if df is None:
        raise RuntimeError('No market data available for XAUUSD H1')

    last_close = df['close'].iloc[-1]
    print(f'Data fetched: {len(df)} candles, last close={last_close:.2f}')

    engine = UnifiedSignalEngine(df, 'XAUUSD', 'H1')
    signal = engine.generate()
    print()
    print('=== SIGNAL GENERATED ===')
    print(f'Symbol:     {signal.symbol}')
    print(f'Direction:  {signal.direction}')
    print(f'Strength:   {signal.strength}')
    print(f'Confidence: {signal.confidence}%')
    print(f'Entry:      {signal.entry}')
    print(f'Stop Loss:  {signal.stop_loss}')
    print(f'TP1:        {signal.take_profit_1}')
    print(f'R:R:        {signal.risk_reward}')
    print(f'Warnings:   {signal.warnings}')
    print()
    print('Engine Scores:')
    for name, result in signal.engine_results.items():
        direction = result['direction']
        score = result['score']
        reason = result['reasoning'][0] if result['reasoning'] else 'N/A'
        reason_clean = reason.encode('ascii', 'replace').decode('ascii')
        print(f'  {name:20s}: {direction:7s} score={score} | {reason_clean[:60]}')


if __name__ == '__main__':
    main()

