import sys
sys.path.insert(0, '.')
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trading_platform.settings')
django.setup()

from engines.data_fetcher import DataFetcher
from engines.unified import UnifiedSignalEngine

print('Testing DataFetcher + Unified Engine...')
fetcher = DataFetcher()
df = fetcher.fetch('XAUUSD', 'H1', limit=200)
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
for k, v in signal.engine_results.items():
    direction = v['direction']
    score = v['score']
    reason = v['reasoning'][0] if v['reasoning'] else 'N/A'
    reason_clean = reason.encode('ascii', 'replace').decode('ascii')
    print(f'  {k:20s}: {direction:7s} score={score} | {reason_clean[:60]}')

