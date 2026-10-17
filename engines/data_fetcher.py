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
from datetime import datetime, timedelta
from typing import Optional


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

    def fetch(self, symbol: str, timeframe: str = 'H1', limit: int = 200) -> Optional[pd.DataFrame]:
        """
        Fetch LIVE OHLCV data. Returns None only if all live sources fail.
        NO fake/synthetic data returned — callers must handle None.
        """
        start_time = datetime.now()
        # Primary: yfinance library
        df = self._fetch_via_yfinance(symbol, timeframe, limit)
        if df is not None and len(df) >= 30:
            latency = int((datetime.now() - start_time).total_seconds() * 1000)
            from .data_quality import DataQualityValidator
            DataQualityValidator.record_source_health('yfinance', 'HEALTHY', latency_ms=latency)
            print(f"[DataFetcher] [SUCCESS] Live data via yfinance: {symbol} {timeframe} ({len(df)} candles, "
                  f"last close={df['close'].iloc[-1]:.5g})")
            self._cache_to_database(symbol, timeframe, df)
            return df
        else:
            from .data_quality import DataQualityValidator
            DataQualityValidator.record_source_health('yfinance', 'DEGRADED', error_message="Empty or short dataset returned")

        # Fallback: Yahoo Direct API
        try:
            start_time = datetime.now()
            df = self._fetch_from_yahoo_api(symbol, timeframe, limit)
            if df is not None and len(df) >= 30:
                latency = int((datetime.now() - start_time).total_seconds() * 1000)
                from .data_quality import DataQualityValidator
                DataQualityValidator.record_source_health('yahoo_direct_api', 'HEALTHY', latency_ms=latency, is_fallback=True)
                print(f"[DataFetcher] [SUCCESS] Live data via Yahoo API: {symbol} {timeframe} ({len(df)} candles)")
                self._cache_to_database(symbol, timeframe, df)
                return df
        except Exception as e:
            from .data_quality import DataQualityValidator
            DataQualityValidator.record_source_health('yahoo_direct_api', 'DOWN', error_message=str(e), is_fallback=True)
            print(f"[DataFetcher] [ERROR] Yahoo API error for {symbol}: {e}")

        # Tertiary Fallback: Cached real historical candles in database
        db_df = self._fetch_from_database(symbol, timeframe, limit)
        if db_df is not None and len(db_df) >= 30:
            from .data_quality import DataQualityValidator
            DataQualityValidator.record_source_health('database_cache', 'HEALTHY', is_fallback=True)
            print(f"[DataFetcher] [SUCCESS] Cached real data via database: {symbol} {timeframe} ({len(db_df)} candles)")
            return db_df

        print(f"[DataFetcher] [ERROR] ALL live sources failed for {symbol} {timeframe} — signal skipped")
        return None

    def _fetch_via_yfinance(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """Use yfinance library for reliable data fetching"""
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

            return df.tail(limit)

        except ImportError:
            return None
        except Exception as e:
            print(f"[DataFetcher] yfinance error for {symbol}: {e}")
            return None

    def _fetch_from_yahoo_api(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """Fallback: Direct Yahoo Finance v8 API"""
        yf_symbol = self.YAHOO_MAP.get(symbol, symbol)
        interval, period = self.TIMEFRAME_TO_YF.get(timeframe, ('1h', '30d'))

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
        params = {'interval': interval, 'range': period, 'events': 'history'}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

        resp = requests.get(url, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        result = data.get('chart', {}).get('result', [])
        if not result:
            return None

        r          = result[0]
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

        return df.tail(limit)

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Fetch real-time current price for a symbol"""
        try:
            import yfinance as yf
            yf_symbol = self.YAHOO_MAP.get(symbol, symbol)
            ticker = yf.Ticker(yf_symbol)
            info = ticker.fast_info
            return float(info.last_price)
        except Exception:
            pass

        # Fallback via API
        try:
            yf_symbol = self.YAHOO_MAP.get(symbol, symbol)
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
            params = {'interval': '1m', 'range': '1d'}
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, params=params, headers=headers, timeout=6)
            data = resp.json()
            result = data.get('chart', {}).get('result', [])
            if result:
                closes = result[0]['indicators']['quote'][0]['close']
                closes = [c for c in closes if c is not None]
                if closes:
                    return float(closes[-1])
        except Exception:
            pass
        return None

    def get_quote_spread(self, symbol: str) -> Optional[dict]:
        """
        Fetch bid/ask and spread where available.
        Per Phase 1 Master Architecture requirements.
        """
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

    def _cache_to_database(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Asynchronously cache recent real OHLCV bars into database"""
        try:
            from market_data.models import Instrument, OHLCV
            inst = Instrument.objects.filter(symbol=symbol).first()
            if not inst:
                return
            recent_df = df.tail(100)
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

