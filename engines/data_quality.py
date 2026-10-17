"""
Data Quality & Reliability Layer — Phase 1
Implements requirements from TradeSense Pro Master Architecture:
- Stale-data detection
- Missing/duplicate/out-of-order candle detection
- Basic price anomaly & sanity checks
- Data source health tracking
- Critical-input failure detection (forces WAIT or reduces confidence)
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np


class DataQualityReport:
    """Contains results of data quality validation"""
    def __init__(
        self,
        is_valid: bool = True,
        quality_score: float = 100.0,
        force_wait: bool = False,
        warnings: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
        cleaned_df: Optional[pd.DataFrame] = None
    ):
        self.is_valid = is_valid
        self.quality_score = quality_score
        self.force_wait = force_wait
        self.warnings = warnings or []
        self.errors = errors or []
        self.cleaned_df = cleaned_df

    def to_dict(self) -> dict:
        return {
            'is_valid': self.is_valid,
            'quality_score': round(self.quality_score, 2),
            'force_wait': self.force_wait,
            'warnings': self.warnings,
            'errors': self.errors,
        }


class DataQualityValidator:
    """Validates market data feeds, checks freshness, and logs provider health."""

    TIMEFRAME_DELTAS = {
        'M1':  timedelta(minutes=1),
        'M5':  timedelta(minutes=5),
        'M15': timedelta(minutes=15),
        'M30': timedelta(minutes=30),
        'H1':  timedelta(hours=1),
        'H4':  timedelta(hours=4),
        'D1':  timedelta(days=1),
        'W1':  timedelta(weeks=1),
    }

    # Allowed staleness multiplier (e.g. for weekends or market close, we tolerate more)
    STALE_MULTIPLIER = 3.5

    @classmethod
    def validate_ohlcv(
        cls,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str = 'H1',
        is_crypto: bool = False
    ) -> DataQualityReport:
        """
        Comprehensive data validation of an OHLCV DataFrame.
        Returns a DataQualityReport with cleaned data and any detected anomalies.
        """
        warnings = []
        errors = []
        force_wait = False
        score = 100.0

        if df is None or df.empty:
            return DataQualityReport(
                is_valid=False,
                quality_score=0.0,
                force_wait=True,
                errors=["Empty or null dataframe received"],
            )

        # 1. Check required columns
        required_cols = {'open', 'high', 'low', 'close'}
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            return DataQualityReport(
                is_valid=False,
                quality_score=0.0,
                force_wait=True,
                errors=[f"Missing required columns: {list(missing_cols)}"],
            )

        # Work on a copy
        cleaned = df.copy()

        # 2. Duplicate timestamp check
        if cleaned.index.has_duplicates:
            duplicates_count = cleaned.index.duplicated().sum()
            warnings.append(f"Detected {duplicates_count} duplicate timestamp(s); deduplicating by keeping last.")
            cleaned = cleaned[~cleaned.index.duplicated(keep='last')]
            score -= min(15.0, duplicates_count * 5.0)

        # 3. Monotonic / Out-of-order check
        if not cleaned.index.is_monotonic_increasing:
            warnings.append("Timestamps were not in chronological order; re-sorting.")
            cleaned = cleaned.sort_index()
            score -= 10.0

        # Minimum candle requirement check
        if len(cleaned) < 30:
            errors.append(f"Insufficient candles: {len(cleaned)} (minimum 30 required for analysis).")
            force_wait = True
            score -= 40.0

        # 4. Price sanity checks (High >= Low, High >= Open/Close, Low <= Open/Close, > 0)
        invalid_prices = (
            (cleaned['open'] <= 0) |
            (cleaned['high'] <= 0) |
            (cleaned['low'] <= 0) |
            (cleaned['close'] <= 0)
        )
        if invalid_prices.any():
            errors.append("Non-positive prices found in candles.")
            force_wait = True
            score -= 50.0

        high_low_violation = cleaned['high'] < cleaned['low']
        if high_low_violation.any():
            errors.append("Invalid candle geometry: High < Low detected.")
            force_wait = True
            score -= 40.0

        high_open_close_violation = (cleaned['high'] < cleaned['open']) | (cleaned['high'] < cleaned['close'])
        if high_open_close_violation.any():
            warnings.append("High is lower than Open or Close in some candles.")
            score -= 20.0

        low_open_close_violation = (cleaned['low'] > cleaned['open']) | (cleaned['low'] > cleaned['close'])
        if low_open_close_violation.any():
            warnings.append("Low is higher than Open or Close in some candles.")
            score -= 20.0

        # 5. Missing / Gap check
        expected_delta = cls.TIMEFRAME_DELTAS.get(timeframe)
        if expected_delta and len(cleaned) > 1:
            time_diffs = cleaned.index.to_series().diff().dropna()
            # If gap > 2 * expected_delta (ignore for non-crypto weekends if daily/weekly)
            large_gaps = time_diffs[time_diffs > (expected_delta * 2.5)]
            if len(large_gaps) > 0 and (is_crypto or timeframe not in ['D1', 'W1']):
                warnings.append(f"Detected {len(large_gaps)} time gap(s) exceeding normal intervals.")
                score -= min(20.0, len(large_gaps) * 4.0)

        # 6. Stale data detection
        last_timestamp = cleaned.index[-1]
        if hasattr(last_timestamp, 'to_pydatetime'):
            last_dt = last_timestamp.to_pydatetime()
        else:
            last_dt = last_timestamp

        if last_dt.tzinfo is None:
            now = datetime.now()
        else:
            now = datetime.now(timezone.utc)

        time_since_last = now - last_dt
        if expected_delta:
            max_tolerated_age = expected_delta * cls.STALE_MULTIPLIER
            # Weekend adjustment for traditional markets
            is_weekend = now.weekday() in (5, 6)
            if not is_crypto and is_weekend:
                max_tolerated_age += timedelta(days=2)

            if time_since_last > max_tolerated_age:
                warnings.append(
                    f"Data is potentially stale. Last candle was {time_since_last} ago "
                    f"(tolerated: {max_tolerated_age})."
                )
                score -= 25.0
                if time_since_last > max_tolerated_age * 2:
                    force_wait = True
                    errors.append("Critical data staleness: Latest candle is excessively outdated.")

        # Ensure score within 0 - 100
        score = max(0.0, min(100.0, score))
        if score < 50.0:
            force_wait = True

        is_valid = len(errors) == 0 and not force_wait

        return DataQualityReport(
            is_valid=is_valid,
            quality_score=score,
            force_wait=force_wait,
            warnings=warnings,
            errors=errors,
            cleaned_df=cleaned
        )

    @classmethod
    def check_provider_conflict(
        cls,
        price_a: float,
        price_b: float,
        threshold_pct: float = 0.5
    ) -> Tuple[bool, float]:
        """
        Compares prices from two providers to detect conflict.
        Returns (has_conflict, difference_percentage).
        """
        if price_a <= 0 or price_b <= 0:
            return True, 100.0

        diff_pct = abs(price_a - price_b) / ((price_a + price_b) / 2.0) * 100.0
        has_conflict = diff_pct > threshold_pct
        return has_conflict, diff_pct

    @classmethod
    def record_source_health(
        cls,
        provider_name: str,
        status: str,
        latency_ms: Optional[int] = None,
        error_message: str = "",
        is_fallback: bool = False
    ):
        """Records data source status into DataSourceHealth model asynchronously or safely"""
        try:
            from market_data.models import DataSourceHealth
            from django.utils import timezone as dj_tz

            now = dj_tz.now()
            obj, _ = DataSourceHealth.objects.get_or_create(
                provider_name=provider_name,
                defaults={'status': status, 'is_fallback': is_fallback}
            )
            obj.status = status
            obj.is_fallback = is_fallback
            if latency_ms is not None:
                obj.latency_ms = latency_ms

            if status == 'HEALTHY':
                obj.last_success = now
            else:
                obj.last_error = now
                obj.error_message = error_message

            obj.save()
        except Exception:
            # Avoid crashing if database is not reachable or during tests
            pass
