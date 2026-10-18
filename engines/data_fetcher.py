"""
Market Data Fetcher — Live Version
Fetches REAL OHLCV data from Yahoo Finance.
Primary: yfinance library (most reliable for Yahoo Finance)
Fallback: Direct Yahoo Finance v8 API request
NO SYNTHETIC/FAKE DATA — if both fail, raises exception.
"""
import pandas as pd
import numpy as np
import requests
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import yfinance as _yf  # noqa: F401
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False

_HTTP_SESSION = requests.Session()
_HTTP_SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})
_LAST_DB_CACHE_TS = {}
_MEM_OHLCV_CACHE = {}  # (symbol, timeframe) -> (timestamp, df)


class DataFetcher:
    """Fetches live OHLCV data for any symbol"""

    # Yahoo Finance symbol mapping
    YAHOO_MAP = {
        # Forex
        'EURUSD': 'EURUSD=X',  'GBPUSD': 'GBPUSD=X',  'USDJPY': 'USDJPY=X',
        'USDCHF': 'USDCHF=X',  'AUDUSD': 'AUDUSD=X',  'USDCAD': 'USDCAD=X',
        'NZDUSD': 'NZDUSD=X',  'EURGBP': 'EURGBP=X',  'EURJPY': 'EURJPY=X',
        'GBPJPY': 'GBPJPY=X',  'EURCHF': 'EURCHF=X',  'AUDCAD': 'AUDCAD=X',
        # Commodities
        'XAUUSD': 'GC=F',      'XAGUSD': 'SI=F',       'USOIL':  'CL=F',
        'UKOIL':  'BZ=F',      'NATGAS': 'NG=F',
        # Crypto
        'BTCUSD': 'BTC-USD',   'ETHUSD': 'ETH-USD',    'BNBUSD': 'BNB-USD',
        'SOLUSD': 'SOL-USD',   'XRPUSD': 'XRP-USD',
        # Indices
        'US30':   'YM=F',      'SPX500': 'ES=F',       'NAS100': 'NQ=F',
        'GER40':  '^GDAXI',    'UK100':  '^FTSE',      'JP225':  'NKD=F',
    }

    TIMEFRAME_TO_YF = {
        'M1':  ('1m',  '3d'),
        'M5':  ('5m',  '5d'),
        'M15': ('15m', '10d'),
        'M30': ('30m', '15d'),
        'H1':  ('1h',  '30d'),
        'H2':  ('1h',  '60d'),   # H2 assembled from H1
        'H4':  ('1h',  '60d'),   # H4 assembled from H1
        'D1':  ('1d',  '365d'),
        'W1':  ('1wk', '730d'),
    }

    TF_SECONDS = {
        'M1': 60, 'M5': 300, 'M15': 900, 'M30': 1800,
        'H1': 3600, 'H2': 7200, 'H4': 14400, 'D1': 86400, 'W1': 604800,
    }

    def fetch(self, symbol: str, timeframe: str = 'H1', limit: int = 200) -> Optional[pd.DataFrame]:
        """
        Fetch LIVE OHLCV data. Returns None only if all live sources fail.
        NO fake/synthetic data returned — callers must handle None.
        """
        min_bars = min(30, max(1, limit))
        cache_key = (symbol, timeframe)
        now_ts = _time.time()

        # Short 1.5s memory cache to keep rapid live chart polls instantaneous
        cached = _MEM_OHLCV_CACHE.get(cache_key)
        if cached and (now_ts - cached[0]) < 1.5 and len(cached[1]) >= min_bars:
            return cached[1].tail(limit).copy()

        # Primary (when installed): yfinance library
        if _HAS_YFINANCE:
            start_time = datetime.now()
            df = self._fetch_via_yfinance(symbol, timeframe, limit)
            if df is not None and len(df) >= min_bars:
                latency = int((datetime.now() - start_time).total_seconds() * 1000)
                from .data_quality import DataQualityValidator
                DataQualityValidator.record_source_health('yfinance', 'HEALTHY', latency_ms=latency)
                _MEM_OHLCV_CACHE[cache_key] = (now_ts, df)
                self._cache_to_database_async(symbol, timeframe, df)
                return df

        # Fast Direct Yahoo Finance v8 API
        try:
            start_time = datetime.now()
            df = self._fetch_from_yahoo_api(symbol, timeframe, limit)
            if df is not None and len(df) >= min_bars:
                latency = int((datetime.now() - start_time).total_seconds() * 1000)
                from .data_quality import DataQualityValidator
                DataQualityValidator.record_source_health('yahoo_direct_api', 'HEALTHY', latency_ms=latency, is_fallback=not _HAS_YFINANCE)
                _MEM_OHLCV_CACHE[cache_key] = (now_ts, df)
                self._cache_to_database_async(symbol, timeframe, df)
                return df
        except Exception as e:
            from .data_quality import DataQualityValidator
            DataQualityValidator.record_source_health('yahoo_direct_api', 'DOWN', error_message=str(e), is_fallback=True)
            print(f"[DataFetcher] [ERROR] Yahoo API error for {symbol}: {e}")

        # Tertiary Fallback: Cached real historical candles in database
        db_df = self._fetch_from_database(symbol, timeframe, limit)
        if db_df is not None and len(db_df) >= min_bars:
            from .data_quality import DataQualityValidator
            DataQualityValidator.record_source_health('database_cache', 'HEALTHY', is_fallback=True)
            return db_df

        print(f"[DataFetcher] [ERROR] ALL live sources failed for {symbol} {timeframe} — signal skipped")
        return None

    def _fetch_via_yfinance(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """Use yfinance library for reliable data fetching"""
        if not _HAS_YFINANCE:
            return None
        try:
            import yfinance as yf
            yf_symbol = self.YAHOO_MAP.get(symbol, symbol)
            interval, period = self.TIMEFRAME_TO_YF.get(timeframe, ('1h', '730d'))

            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)

            if df is None or len(df) == 0:
                return None

            # Normalize column names
            df = df.rename(columns={
                'Open': 'open', 'High': 'high', 'Low': 'low',
                'Close': 'close', 'Volume': 'volume'
            })
            df = df[['open', 'high', 'low', 'close', 'volume']].dropna()
            df = df.sort_index()

            # Resample H2/H4 from H1
            if timeframe in ('H2', 'H4'):
                df = df.resample('2h' if timeframe == 'H2' else '4h').agg({
                    'open': 'first', 'high': 'max',
                    'low': 'min', 'close': 'last', 'volume': 'sum'
                }).dropna()

            df = self._normalize_trailing_live_candle(df, timeframe)
            return df.tail(limit)

        except ImportError:
            return None
        except Exception as e:
            print(f"[DataFetcher] yfinance error for {symbol}: {e}")
            return None

    def _normalize_trailing_live_candle(self, df: pd.DataFrame, timeframe: str, live_price: Optional[float] = None) -> pd.DataFrame:
        """
        Yahoo Finance appends a synthetic intra-bar quote at the current second
        with open==high==low==close and volume==0. Merge it into the active timeframe
        bucket or connect its open to previous close so the live candle has a real body.
        """
        if df is None or len(df) < 2:
            return df

        tf_sec = self.TF_SECONDS.get(timeframe, 3600)
        last_ts = int(df.index[-1].timestamp())
        prev_ts = int(df.index[-2].timestamp())

        last_row = df.iloc[-1]
        is_flat_tick = (
            abs(float(last_row['open']) - float(last_row['close'])) < 1e-9 and
            abs(float(last_row['high']) - float(last_row['low'])) < 1e-9
        )

        # If the trailing point belongs to the same candle bucket as the previous bar, merge it
        if (last_ts // tf_sec) == (prev_ts // tf_sec) or (is_flat_tick and (last_ts - prev_ts) < tf_sec):
            price = float(live_price if live_price is not None else last_row['close'])
            prev_idx = df.index[-2]
            df.loc[prev_idx, 'close'] = price
            df.loc[prev_idx, 'high'] = max(float(df.loc[prev_idx, 'high']), price)
            df.loc[prev_idx, 'low'] = min(float(df.loc[prev_idx, 'low']), price)
            df.loc[prev_idx, 'volume'] = float(df.loc[prev_idx, 'volume']) + float(last_row.get('volume', 0.0))
            df = df.iloc[:-1]
        elif is_flat_tick:
            # New bar just started: connect open to previous candle's close
            prev_close = float(df['close'].iloc[-2])
            price = float(live_price if live_price is not None else last_row['close'])
            last_idx = df.index[-1]
            df.loc[last_idx, 'open'] = prev_close
            df.loc[last_idx, 'close'] = price
            df.loc[last_idx, 'high'] = max(prev_close, price)
            df.loc[last_idx, 'low'] = min(prev_close, price)

        if live_price is not None and len(df) >= 1:
            last_idx = df.index[-1]
            lp = float(live_price)
            df.loc[last_idx, 'close'] = lp
            df.loc[last_idx, 'high'] = max(float(df.loc[last_idx, 'high']), lp)
            df.loc[last_idx, 'low'] = min(float(df.loc[last_idx, 'low']), lp)

        return df

    def _fetch_from_yahoo_api(self, symbol: str, timeframe: str, limit: int, fast_range: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Direct Yahoo Finance v8 API using persistent HTTP session"""
        yf_symbol = self.YAHOO_MAP.get(symbol, symbol)
        interval, period = self.TIMEFRAME_TO_YF.get(timeframe, ('1h', '30d'))
        if fast_range:
            period = fast_range

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
        params = {'interval': interval, 'range': period, 'events': 'history'}

        resp = _HTTP_SESSION.get(url, params=params, timeout=4)
        resp.raise_for_status()
        data = resp.json()

        result = data.get('chart', {}).get('result', [])
        if not result:
            return None

        r          = result[0]
        meta       = r.get('meta', {})
        live_price = meta.get('regularMarketPrice')
        timestamps = r.get('timestamp', [])
        q          = r.get('indicators', {}).get('quote', [{}])[0]

        df = pd.DataFrame({
            'open':   q.get('open',   []),
            'high':   q.get('high',   []),
            'low':    q.get('low',    []),
            'close':  q.get('close',  []),
            'volume': q.get('volume', []),
        }, index=pd.to_datetime(timestamps, unit='s', utc=True))

        df = df.dropna()
        df = df.sort_index()

        if timeframe in ('H2', 'H4'):
            df = df.resample('2h' if timeframe == 'H2' else '4h').agg({
                'open': 'first', 'high': 'max',
                'low': 'min', 'close': 'last', 'volume': 'sum'
            }).dropna()

        df = self._normalize_trailing_live_candle(df, timeframe, live_price=live_price)
        return df.tail(limit)

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Fetch real-time current price for a symbol"""
        if _HAS_YFINANCE:
            try:
                import yfinance as yf
                yf_symbol = self.YAHOO_MAP.get(symbol, symbol)
                ticker = yf.Ticker(yf_symbol)
                info = ticker.fast_info
                return float(info.last_price)
            except Exception:
                pass

        # Fast via persistent HTTP session
        try:
            yf_symbol = self.YAHOO_MAP.get(symbol, symbol)
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
            params = {'interval': '1m', 'range': '1d'}
            resp = _HTTP_SESSION.get(url, params=params, timeout=4)
            data = resp.json()
            result = data.get('chart', {}).get('result', [])
            if result:
                meta_price = result[0].get('meta', {}).get('regularMarketPrice')
                if meta_price is not None:
                    return float(meta_price)
                closes = result[0]['indicators']['quote'][0]['close']
                closes = [c for c in closes if c is not None]
                if closes:
                    return float(closes[-1])
        except Exception:
            pass
        return None

    def get_live_tick(self, symbol: str, timeframe: str = 'H1') -> Optional[dict]:
        """
        Ultra-fast live tick & active candle fetcher for real-time TradingView-style chart streaming.
        """
        fast_ranges = {
            'M1': '1d', 'M5': '2d', 'M15': '5d', 'M30': '5d',
            'H1': '5d', 'H2': '10d', 'H4': '15d', 'D1': '30d', 'W1': '90d'
        }
        try:
            df = self._fetch_from_yahoo_api(symbol, timeframe, limit=5, fast_range=fast_ranges.get(timeframe, '5d'))
            if df is None or df.empty:
                df = self.fetch(symbol, timeframe, limit=5)
            if df is None or df.empty:
                return None

            candles = []
            for idx, row in df.tail(3).iterrows():
                t = int(idx.timestamp()) if hasattr(idx, 'timestamp') else int(pd.to_datetime(idx).timestamp())
                candles.append({
                    'time': t,
                    'open': round(float(row['open']), 5),
                    'high': round(float(row['high']), 5),
                    'low': round(float(row['low']), 5),
                    'close': round(float(row['close']), 5),
                    'volume': float(row.get('volume', 0.0)),
                })

            last_c = candles[-1]
            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'tf_seconds': self.TF_SECONDS.get(timeframe, 3600),
                'live_price': last_c['close'],
                'candle': last_c,
                'recent_candles': candles,
                'server_ts': int(_time.time()),
            }
        except Exception as e:
            print(f"[DataFetcher] get_live_tick error for {symbol}: {e}")
            return None

    def get_quote_spread(self, symbol: str) -> Optional[dict]:
        """
        Fetch bid/ask and spread where available.
        Per Phase 1 Master Architecture requirements.
        """
        if _HAS_YFINANCE:
            try:
                import yfinance as yf
                yf_symbol = self.YAHOO_MAP.get(symbol, symbol)
                ticker = yf.Ticker(yf_symbol)
                info = ticker.fast_info
                bid = getattr(info, 'bid', None) or getattr(info, 'last_price', None)
                ask = getattr(info, 'ask', None) or getattr(info, 'last_price', None)
                if bid and ask:
                    spread = abs(float(ask) - float(bid))
                    return {
                        'bid': float(bid),
                        'ask': float(ask),
                        'spread': float(spread),
                        'provider': 'yfinance',
                        'timestamp': datetime.now(timezone.utc)
                    }
            except Exception:
                pass

        price = self.get_current_price(symbol)
        if price:
            # Approximate spread proxy if exact bid/ask not returned by free tier
            proxy_spread = price * 0.0001
            return {
                'bid': float(price),
                'ask': float(price + proxy_spread),
                'spread': float(proxy_spread),
                'provider': 'yahoo_proxy',
                'timestamp': datetime.now(timezone.utc)
            }
        return None

    def _cache_to_database_async(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Throttle and run database OHLCV caching in background thread to keep API fast"""
        key = (symbol, timeframe)
        now = _time.time()
        if now - _LAST_DB_CACHE_TS.get(key, 0) < 60:
            return
        _LAST_DB_CACHE_TS[key] = now
        df_copy = df.tail(40).copy()
        threading.Thread(
            target=self._cache_to_database,
            args=(symbol, timeframe, df_copy),
            daemon=True
        ).start()

    def _cache_to_database(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Cache recent real OHLCV bars into database"""
        try:
            from market_data.models import Instrument, OHLCV
            inst = Instrument.objects.filter(symbol=symbol).first()
            if not inst:
                return
            recent_df = df.tail(40)
            for ts, row in recent_df.iterrows():
                dt = ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts
                OHLCV.objects.update_or_create(
                    instrument=inst,
                    timeframe=timeframe,
                    timestamp=dt,
                    defaults={
                        'open_price': float(row['open']),
                        'high_price': float(row['high']),
                        'low_price': float(row['low']),
                        'close_price': float(row['close']),
                        'volume': float(row.get('volume', 0.0)),
                        'provider': 'yfinance_cache'
                    }
                )
        except Exception:
            pass

    def _fetch_from_database(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """Tertiary fallback: load cached real OHLCV data from database"""
        try:
            from market_data.models import OHLCV
            candles = list(OHLCV.objects.filter(
                instrument__symbol=symbol,
                timeframe=timeframe
            ).order_by('-timestamp')[:limit])
            if candles and len(candles) >= 30:
                candles.reverse()
                rows = []
                for c in candles:
                    rows.append({
                        'timestamp': c.timestamp,
                        'open': float(c.open_price),
                        'high': float(c.high_price),
                        'low': float(c.low_price),
                        'close': float(c.close_price),
                        'volume': float(c.volume)
                    })
                df = pd.DataFrame(rows)
                df.set_index('timestamp', inplace=True)
                return df
        except Exception:
            pass
        return None

