"""Download the publicly accessible historical EV Trading Labs OHLC archive.

Only explicitly public past-year URLs are requested.  Current-year M1 data is
documented by the provider as account-gated, so this script neither requests
it nor creates an account.  The data is a Dukascopy-derived market-data source,
not the connected MetaQuotes broker feed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time

import requests


BASE = 'https://evtradelabs.com/api/simulator/data/{provider_symbol}/{timeframe}/{year}.json.gz'
SOURCES = {
    'XAUUSD': ('XAUUSD', 2006),
    'US30': ('DJ', 2012),
    'SPX500': ('SP500', 2015),
}
TIMEFRAMES = ('M5', 'M15', 'H1', 'H4')


def _atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def collect(output_dir: Path, *, start_year: int | None = None, end_year: int = 2025,
            workers: int = 4, timeout: float = 30.0, symbols=None, timeframes=None):
    if not 1 <= workers <= 4:
        raise ValueError('workers must be from 1 to 4')
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    manifest.update({
        'provider': 'EV Trading Labs public historical simulator files',
        'provider_documentation': 'https://evtradelabs.com/data',
        'underlying_data_lineage': 'Provider describes its OHLCV as aggregated from Dukascopy ticks',
        'requested_at_utc': datetime.now(timezone.utc).isoformat(),
        'public_years_requested_through': end_year,
        'current_year_not_requested': datetime.now(timezone.utc).year,
        'current_year_reason': 'Provider documents M1/current-year access as account-gated; no account was created',
        'license_note': 'Provider page states free use with attribution; retain source attribution in reports',
    })
    manifest.setdefault('files', {})
    selected_symbols = tuple(symbols or SOURCES.keys())
    selected_timeframes = tuple(timeframes or TIMEFRAMES)
    unknown_symbols = set(selected_symbols) - set(SOURCES)
    unknown_timeframes = set(selected_timeframes) - set(TIMEFRAMES)
    if unknown_symbols or unknown_timeframes:
        raise ValueError(f'Unsupported symbols/timeframes: {sorted(unknown_symbols | unknown_timeframes)}')
    jobs = []
    for symbol, (provider_symbol, first_year) in SOURCES.items():
        if symbol not in selected_symbols:
            continue
        for timeframe in selected_timeframes:
            for year in range(max(first_year, start_year or first_year), end_year + 1):
                jobs.append((symbol, provider_symbol, timeframe, year))

    def one(job):
        symbol, provider_symbol, timeframe, year = job
        key = f'{symbol}/{timeframe}/{year}'
        target = output_dir / symbol / timeframe / f'{year}.json.gz'
        old = manifest['files'].get(key, {})
        if old.get('status') == 'COMPLETE' and target.exists() and sha256(target.read_bytes()).hexdigest() == old.get('sha256'):
            return key, old
        url = BASE.format(provider_symbol=provider_symbol, timeframe=timeframe, year=year)
        response = requests.get(url, timeout=timeout, headers={'User-Agent': 'TradeSense-Research/1.0 public-history-audit'})
        detail = {'url': url, 'http_status': response.status_code, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat()}
        if response.status_code != 200:
            detail['status'] = 'UNAVAILABLE'
            return key, detail
        if not response.content.startswith(b'\x1f\x8b'):
            detail.update(status='INVALID_PAYLOAD', bytes=len(response.content))
            return key, detail
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        temporary.write_bytes(response.content)
        temporary.replace(target)
        detail.update(status='COMPLETE', path=str(target.resolve()), bytes=len(response.content), sha256=sha256(response.content).hexdigest())
        return key, detail

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, job) for job in jobs]
        for future in as_completed(futures):
            key, detail = future.result()
            manifest['files'][key] = detail
            print(key, detail['status'], detail.get('bytes', ''), flush=True)
            _atomic_json(manifest_path, manifest)
            time.sleep(0.02)
    manifest['complete_files'] = sum(item.get('status') == 'COMPLETE' for item in manifest['files'].values())
    manifest['unavailable_files'] = sum(item.get('status') == 'UNAVAILABLE' for item in manifest['files'].values())
    _atomic_json(manifest_path, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--start-year', default=None, type=int)
    parser.add_argument('--end-year', default=2025, type=int)
    parser.add_argument('--workers', default=4, type=int)
    parser.add_argument('--timeout', default=30.0, type=float)
    parser.add_argument('--symbols', nargs='+', choices=tuple(SOURCES))
    parser.add_argument('--timeframes', nargs='+', choices=TIMEFRAMES)
    args = parser.parse_args()
    data = collect(args.output_dir, start_year=args.start_year, end_year=args.end_year,
                   workers=args.workers, timeout=args.timeout, symbols=args.symbols, timeframes=args.timeframes)
    print(json.dumps({'complete_files': data['complete_files'], 'unavailable_files': data['unavailable_files'],
                      'manifest': str((args.output_dir / 'manifest.json').resolve())}, indent=2))


if __name__ == '__main__':
    main()
