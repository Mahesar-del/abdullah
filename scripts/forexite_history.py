"""Public Forexite minute-history collector, with explicit source limitations.

This downloads offered archive links only. It never creates synthetic bars,
forward-fills missing periods, logs into an account, or enables paid services.
MetaStock source labels are treated conservatively as minute OPEN timestamps;
their OHLC becomes available one minute later. This is an assumption, not a
claim that Forexite and the configured MT5 broker have identical candles.
"""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urljoin, urlparse
from zipfile import ZipFile

import numpy as np
import pandas as pd
import requests


SOURCE_BASE = 'https://www.forexite.com/free_forex_quotes/'
SOURCE_DESCRIPTION = SOURCE_BASE + 'forex_history.html'
SYMBOLS = {'XAUUSD': 'XAUUSD', 'DJIUSD': 'US30', 'SPXUSD': 'SPX500'}
SOURCE_TIMEZONE = 'Europe/Berlin'
LABEL_ASSUMPTION = 'Provider label treated as minute open; OHLC available at label+1 minute (conservative, unconfirmed label convention)'
PRICE_BASIS = 'Forexite MetaStock OHLC; exact bid/ask basis not separately established'
_ZIP_PATTERN = re.compile(r'/free_forex_quotes/(\d{4})/(\d{2})/(\d{6})\.zip$', re.I)


class AccessBlocked(RuntimeError):
    """An explicit access/rate denial ends this run without bypass attempts."""


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            self.hrefs.extend(value for key, value in attrs if key.lower() == 'href' and value)


def catalog_pages(start: date, end: date):
    """Known published catalogs: individual 2001–2014 years; current 2022+ page.

    There is no verified published 2015–2021 daily catalog in these sources.
    Those years remain an explicit coverage gap, not guessed URL requests.
    """
    urls = [SOURCE_BASE + f'forex_history_arhiv_{year}.html'
            for year in range(start.year, min(end.year, 2014) + 1)]
    if end.year >= 2015:
        urls.append(SOURCE_BASE + 'forex_history_arhiv.html')
    return urls


def parse_archive_catalog(html: str, page_url: str):
    parser = _Links()
    parser.feed(html)
    found = {}
    for href in parser.hrefs:
        url = urljoin(page_url, href)
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.netloc != 'www.forexite.com':
            continue
        match = _ZIP_PATTERN.fullmatch(parsed.path)
        if not match or parsed.query or parsed.fragment:
            continue
        year, month, compact = match.groups()
        try:
            stamp = datetime.strptime(compact, '%d%m%y').date()
        except ValueError:
            continue
        if stamp.year == int(year) and stamp.month == int(month):
            found[stamp] = url
    return dict(sorted(found.items()))


def parse_forexite_zip(payload: bytes):
    """Return real quoted OHLC only, normalized to UTC, without filling gaps."""
    with ZipFile(BytesIO(payload)) as archive:
        members = [info for info in archive.infolist() if info.filename.lower().endswith('.txt')]
        if not members or sum(info.file_size for info in members) > 64 * 1024 * 1024:
            raise ValueError('Missing or unexpectedly large text archive')
        pieces = []
        for info in members:
            frame = pd.read_csv(BytesIO(archive.read(info)), dtype=str)
            frame.columns = [str(name).strip('<> ').upper() for name in frame.columns]
            required = ['TICKER', 'DTYYYYMMDD', 'TIME', 'OPEN', 'HIGH', 'LOW', 'CLOSE']
            if any(name not in frame for name in required):
                raise ValueError('Unrecognized Forexite MetaStock schema')
            frame = frame[frame.TICKER.isin(SYMBOLS)].copy()
            if frame.empty:
                continue
            labels = pd.to_datetime(
                frame.DTYYYYMMDD + frame.TIME.str.zfill(6), format='%Y%m%d%H%M%S', errors='raise',
            )
            # Forexite explicitly means CET/CEST, not a fixed UTC+1 offset.
            # Ambiguous/nonexistent DST labels cannot be silently guessed.
            stamps = labels.dt.tz_localize(SOURCE_TIMEZONE, ambiguous='raise', nonexistent='raise').dt.tz_convert('UTC')
            normalized = pd.DataFrame({
                'timestamp': stamps,
                'available_at': stamps + pd.Timedelta(minutes=1),
                'symbol': frame.TICKER.map(SYMBOLS),
            })
            for name in ('OPEN', 'HIGH', 'LOW', 'CLOSE'):
                normalized[name.lower()] = pd.to_numeric(frame[name], errors='raise')
            pieces.append(normalized)
    if not pieces:
        raise ValueError('Archive has no approved asset rows')
    result = pd.concat(pieces, ignore_index=True).sort_values(['timestamp', 'symbol']).reset_index(drop=True)
    prices = result[['open', 'high', 'low', 'close']]
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        raise ValueError('Archive contains non-finite/non-positive prices')
    if ((result.high < result[['open', 'close', 'low']].max(axis=1)) |
            (result.low > result[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError('Archive contains invalid OHLC geometry')
    if result.duplicated(['timestamp', 'symbol']).any():
        raise ValueError('Archive contains duplicate instrument/timestamp rows')
    return result


def day_cache_path(output_dir, day: date):
    return Path(output_dir) / 'days' / str(day.year) / f'{day.isoformat()}.csv.gz'


def load_cached_day(path):
    frame = pd.read_csv(path)
    frame['timestamp'] = pd.to_datetime(frame.timestamp, utc=True)
    frame['available_at'] = pd.to_datetime(frame.available_at, utc=True)
    return frame.sort_values(['timestamp', 'symbol']).reset_index(drop=True)


def iter_csv_chunks(output_dir, start=None, end=None):
    """Yield cached daily DataFrames in provider-date / UTC chronological order.

    A row's OHLC may only be used when available_at <= simulated decision time.
    Consumers must preserve this cutoff when resampling M15/H1/H4 history.
    """
    for path in sorted((Path(output_dir) / 'days').glob('*/*.csv.gz')):
        day = date.fromisoformat(path.name[:10])
        if (start is not None and day < start) or (end is not None and day > end):
            continue
        yield load_cached_day(path)


class PublicFetcher:
    def __init__(self, timeout=20.0, attempts=3):
        self.timeout = timeout
        self.attempts = attempts
        self.blocked = threading.Event()
        self.local = threading.local()

    def get(self, url):
        if not url.startswith(SOURCE_BASE):
            raise ValueError('Only published Forexite source URLs are permitted')
        if not hasattr(self.local, 'session'):
            self.local.session = requests.Session()
            self.local.session.headers['User-Agent'] = 'TradeSense-Research/1.0 public-history-audit'
        for attempt in range(self.attempts):
            if self.blocked.is_set():
                raise AccessBlocked('Source blocked this run; no further requests submitted')
            try:
                response = self.local.session.get(url, timeout=self.timeout)
                if response.status_code in (401, 403, 429):
                    self.blocked.set()
                    raise AccessBlocked(f'Source access/rate denial HTTP {response.status_code}: {url}')
                if response.status_code >= 500 and attempt + 1 < self.attempts:
                    time.sleep(2 ** attempt)
                    continue
                return response
            except (requests.Timeout, requests.ConnectionError):
                if attempt + 1 == self.attempts:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError('Unreachable retry state')


def _write_manifest(path, manifest):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def collect(start: date, end: date, output_dir, max_days=None, workers=3, timeout=20.0):
    if end < start:
        raise ValueError('end must not precede start')
    if not 1 <= workers <= 4:
        raise ValueError('workers must be between 1 and 4')
    root = Path(output_dir)
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    manifest.update({
        'provider': 'Forexite public MetaStock archive', 'source_documentation': SOURCE_DESCRIPTION,
        'source_timezone': SOURCE_TIMEZONE, 'bar_label_assumption': LABEL_ASSUMPTION,
        'price_basis': PRICE_BASIS, 'costs': 'Historical spread/commission/swap/volume unavailable in this archive; any execution-cost model is an assumption',
        'license_status': 'Publicly offered download for quote-history use; no separate redistribution license verified',
        'requested_start': start.isoformat(), 'requested_end': end.isoformat(),
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'catalogs': [],
    })
    manifest.setdefault('days', {})
    fetcher = PublicFetcher(timeout=timeout)
    discovered = {}
    for page in catalog_pages(start, end):
        response = fetcher.get(page)
        catalog_entry = {'url': page, 'http_status': response.status_code,
                         'sha256': sha256(response.content).hexdigest()}
        if response.status_code == 200:
            links = parse_archive_catalog(response.text, page)
            discovered.update(links)
            catalog_entry['published_zip_count'] = len(links)
        manifest['catalogs'].append(catalog_entry)
    available = [(day, url) for day, url in sorted(discovered.items()) if start <= day <= end]
    manifest['catalog_day_count_in_window'] = len(available)
    published_years = {day.year for day, _ in available}
    manifest['requested_years_without_published_daily_links'] = [
        year for year in range(start.year, end.year + 1) if year not in published_years
    ]
    if max_days is not None:
        if max_days < 1:
            raise ValueError('max_days must be positive')
        available = available[:max_days]
    manifest['selected_day_count'] = len(available)
    _write_manifest(manifest_path, manifest)

    def one_day(pair):
        day, url = pair
        cache = day_cache_path(root, day)
        previous = manifest['days'].get(day.isoformat(), {})
        if previous.get('status') == 'COMPLETE' and cache.exists() and sha256(cache.read_bytes()).hexdigest() == previous.get('cache_sha256'):
            return day.isoformat(), previous
        response = fetcher.get(url)
        details = {'url': url, 'http_status': response.status_code,
                   'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                   'source_bytes': len(response.content), 'source_sha256': sha256(response.content).hexdigest()}
        if response.status_code != 200:
            details['status'] = 'SOURCE_UNAVAILABLE'
            return day.isoformat(), details
        frame = parse_forexite_zip(response.content)
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_name(cache.name + '.tmp')
        frame.to_csv(temporary, index=False, compression={'method': 'gzip', 'mtime': 0})
        temporary.replace(cache)
        details.update(
            status='COMPLETE', cache=str(cache.resolve()), rows=len(frame),
            cache_sha256=sha256(cache.read_bytes()).hexdigest(),
            first_timestamp_utc=frame.timestamp.min().isoformat(),
            last_timestamp_utc=frame.timestamp.max().isoformat(),
            last_available_at_utc=frame.available_at.max().isoformat(),
            by_symbol={symbol: int(count) for symbol, count in frame.groupby('symbol').size().items()},
        )
        return day.isoformat(), details

    iterator = iter(available)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}
        for _ in range(workers):
            pair = next(iterator, None)
            if pair is not None:
                pending[pool.submit(one_day, pair)] = pair
        while pending:
            ready, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in ready:
                pair = pending.pop(future)
                try:
                    day, details = future.result()
                except Exception as exc:
                    day, details = pair[0].isoformat(), {'url': pair[1], 'status': 'ERROR', 'error': str(exc)}
                manifest['days'][day] = details
                print(day, details['status'], details.get('rows', ''), flush=True)
                _write_manifest(manifest_path, manifest)
                if not fetcher.blocked.is_set():
                    next_pair = next(iterator, None)
                    if next_pair is not None:
                        pending[pool.submit(one_day, next_pair)] = next_pair
    manifest['stopped_for_access_denial'] = fetcher.blocked.is_set()
    manifest['complete_day_count'] = sum(
        info.get('status') == 'COMPLETE' for info in manifest['days'].values()
    )
    _write_manifest(manifest_path, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, default=date(2006, 1, 1))
    parser.add_argument('--end', type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--max-days', type=int)
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=3)
    parser.add_argument('--timeout', type=float, default=20.0)
    args = parser.parse_args()
    manifest = collect(args.start, args.end, args.output_dir, args.max_days, args.workers, args.timeout)
    print(json.dumps({
        'manifest': str((args.output_dir / 'manifest.json').resolve()),
        'selected_days': manifest['selected_day_count'],
        'complete_days_in_cache': manifest['complete_day_count'],
        'years_without_catalog': manifest['requested_years_without_published_daily_links'],
        'access_denied': manifest['stopped_for_access_denial'],
    }, indent=2))


if __name__ == '__main__':
    main()
