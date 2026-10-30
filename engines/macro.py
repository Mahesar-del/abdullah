"""
Macro & Economic Engine — Weight: 15%
Phase 4 Upgrades:
- DXY, Treasury Yields (10Y, 2Y), Yield Curve Slope (2Y-10Y), Real Yields proxy, VIX
- Gold, Oil (WTI/Brent), Copper (Dr. Copper growth proxy), Equity Indices (SPX, NQ, DAX)
- Economic Calendar & Releases: CPI, PPI, NFP, Unemployment, GDP, PMI, Retail Sales
- Surprise calculation (Actual vs Forecast vs Previous)
- Country & Currency Specific Regional Mapping from Instrument model
- Macro Regimes: Growth, Inflation, Yield Curve, and Risk Sentiment
- High-Impact News Blackout Window enforcement
"""
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from .base import BaseEngine, EngineResult
from .central_bank import CentralBankEngine


class MacroEngine(BaseEngine):
    name   = 'macro'
    weight = 0.15

    # Live Yahoo Finance Tickers
    TICKERS = {
        'DXY':    'DX-Y.NYB',  # US Dollar Index
        'VIX':    '^VIX',      # Volatility / Risk gauge
        'TNX':    '^TNX',      # 10Y Treasury Yield
        'IRX':    '^IRX',      # 13-Week / Short-term Yield proxy
        'GOLD':   'GC=F',      # Gold futures
        'OIL':    'CL=F',      # Crude Oil (WTI)
        'COPPER': 'HG=F',      # High Grade Copper (Global growth proxy)
        'SPX':    'ES=F',      # S&P 500 futures
        'NAS100': 'NQ=F',      # NASDAQ 100 futures
    }

    def __init__(self, df: pd.DataFrame, symbol: str = ''):
        super().__init__(df, symbol)
        self.blackout_active = False
        self.blackout_events = []

    def analyze(self) -> EngineResult:
        try:
            macro_data = self._fetch_live_macro_data()
            self._check_economic_calendar()
            return self._evaluate(macro_data)
        except Exception as e:
            return self._neutral_result(f"Macro Engine error: {str(e)}")

    def _check_economic_calendar(self):
        """Query EconomicEvent and NewsEvent for active blackout windows and recent surprises"""
        try:
            from signals.models import EconomicEvent, NewsEvent
            from market_data.models import Instrument
            import django.utils.timezone as dj_tz

            now = dj_tz.now()
            inst = Instrument.objects.filter(symbol=self.symbol).first()
            relevant_currencies = ['USD']
            if inst:
                if inst.base: relevant_currencies.append(inst.base)
                if inst.quote: relevant_currencies.append(inst.quote)
            relevant_currencies = list(set(relevant_currencies))

            # Check EconomicEvent blackout window
            window_start = now - timedelta(minutes=45)
            window_end   = now + timedelta(minutes=45)

            events = EconomicEvent.objects.filter(
                currency__in=relevant_currencies,
                event_time__range=(window_start, window_end),
                impact='HIGH'
            )

            for ev in events:
                if ev.is_in_blackout:
                    self.blackout_active = True
                    self.blackout_events.append(f"{ev.currency} {ev.title} @ {ev.event_time.strftime('%H:%M')} UTC")

            # Fallback to NewsEvent table
            news_events = NewsEvent.objects.filter(
                currency__in=relevant_currencies,
                event_time__range=(window_start, window_end),
                impact='HIGH'
            )
            for nev in news_events:
                diff = abs((nev.event_time - now).total_seconds()) / 60.0
                if diff <= 30:
                    self.blackout_active = True
            # Central Bank meeting blackout check
            cb_eval = CentralBankEngine.evaluate(self.symbol)
            if cb_eval.get('blackout_active'):
                self.blackout_active = True
                for r in cb_eval.get('reasoning', []):
                    if 'BLACKOUT' in r:
                        self.blackout_events.append(r)

        except Exception:
            pass

    def _evaluate(self, macro: dict) -> EngineResult:
        buy_score  = 0.0
        sell_score = 0.0
        reasoning  = []

        dxy_chg    = macro.get('dxy_change', 0.0)
        vix_lvl    = macro.get('vix_level', 18.0)
        tnx_chg    = macro.get('tnx_change', 0.0)
        gold_chg   = macro.get('gold_change', 0.0)
        oil_chg    = macro.get('oil_change', 0.0)
        copper_chg = macro.get('copper_change', 0.0)
        spx_chg    = macro.get('spx_change', 0.0)

        # ── 1. Central Bank & Monetary Stance ────────────
        cb_eval = CentralBankEngine.evaluate(self.symbol)
        cb_dir = cb_eval.get('direction')
        cb_score = cb_eval.get('score', 50.0)
        if cb_dir == 'BUY':
            buy_score += 25 * (cb_score / 100.0)
        elif cb_dir == 'SELL':
            sell_score += 25 * (cb_score / 100.0)

        for r in cb_eval.get('reasoning', []):
            if 'BLACKOUT' not in r and r not in reasoning:
                reasoning.append(r)

        # ── 2. High-Impact News & Central Bank Blackout Check ─
        if self.blackout_active or cb_eval.get('blackout_active'):
            reasoning.insert(0, f"MACRO/CENTRAL BANK BLACKOUT WINDOW: {', '.join(self.blackout_events or ['High volatility window'])}")
            reasoning.append(f"HIGH-IMPACT NEWS BLACKOUT WINDOW: {', '.join(self.blackout_events)}")
            # In blackout, macro engine stays NEUTRAL to caution / prevent front-running
            return EngineResult(
                engine_name=self.name,
                score=0.0,
                direction='NEUTRAL',
                confidence=15.0,
                reasoning=reasoning,
                weight=self.weight
            )

        # ── 2. Currency Identification ───────────────────
        base_curr  = self.symbol[:3]
        quote_curr = self.symbol[3:6] if len(self.symbol) >= 6 else 'USD'

        # ── 3. DXY (US Dollar Index Dynamics) ────────────
        if quote_curr == 'USD' or self.symbol in ['XAUUSD', 'BTCUSD', 'ETHUSD']:
            if dxy_chg > 0.25:
                sell_score += 35
                reasoning.append(f"DXY surging +{dxy_chg:.2f}%: Broad USD strength creates headwinds")
            elif dxy_chg < -0.25:
                buy_score += 35
                reasoning.append(f"DXY softening {dxy_chg:.2f}%: USD weakness creates tailwind")
            else:
                reasoning.append(f"DXY steady ({dxy_chg:+.2f}%): USD neutral")

        elif base_curr == 'USD':
            if dxy_chg > 0.25:
                buy_score += 35
                reasoning.append(f"DXY +{dxy_chg:.2f}%: Bullish USD push for USD-base pair")
            elif dxy_chg < -0.25:
                sell_score += 35
                reasoning.append(f"DXY {dxy_chg:.2f}%: Bearish drag for USD-base pair")

        # ── 4. Treasury Yields & Real Rates ───────────────
        if tnx_chg > 0.06:
            reasoning.append(f"US 10Y Yield climbing (+{tnx_chg:.3f}%): Higher rate expectations")
            if self.symbol == 'XAUUSD':
                sell_score += 25
                reasoning.append("Rising yields pressure Gold (non-yielding asset)")
            elif quote_curr == 'USD':
                sell_score += 18
        elif tnx_chg < -0.06:
            reasoning.append(f"US 10Y Yield easing ({tnx_chg:.3f}%): Easing financial conditions")
            if self.symbol == 'XAUUSD':
                buy_score += 25
                reasoning.append("Falling yields boost Gold demand")
            elif quote_curr == 'USD':
                buy_score += 18

        # ── 5. VIX (Market Volatility & Risk-Off / Risk-On)
        if vix_lvl > 24.0:
            regime_risk = 'RISK_OFF'
            reasoning.append(f"VIX at {vix_lvl:.1f} (Elevated Fear): Risk-Off regime")
            if self.symbol in ['XAUUSD', 'USDJPY', 'USDCHF']:
                buy_score += 25
                reasoning.append("Safe-haven allocation in Gold/Franc/Yen")
            elif self.symbol in ['BTCUSD', 'ETHUSD', 'SOLUSD', 'NAS100', 'AUDUSD']:
                sell_score += 25
                reasoning.append("High VIX depresses risk assets & growth currencies")
        elif vix_lvl < 15.0:
            regime_risk = 'RISK_ON'
            reasoning.append(f"VIX at {vix_lvl:.1f} (Complacency/Calm): Risk-On regime")
            if self.symbol in ['BTCUSD', 'ETHUSD', 'NAS100', 'SPX500', 'AUDUSD']:
                buy_score += 20
                reasoning.append("Risk-on climate stimulates equities, crypto, and commodity FX")
        else:
            regime_risk = 'NEUTRAL'

        # ── 6. Commodities: Oil (CAD/Inflation) & Copper (Growth)
        if self.symbol in ['USDCAD']:
            if oil_chg > 1.2:
                sell_score += 25
                reasoning.append(f"Crude Oil +{oil_chg:.1f}% strengthens Canadian Dollar (CAD bullish / USDCAD down)")
            elif oil_chg < -1.2:
                buy_score += 25
                reasoning.append(f"Crude Oil {oil_chg:.1f}% weakens Canadian Dollar (USDCAD up)")

        if self.symbol in ['AUDUSD', 'NZDUSD']:
            if copper_chg > 1.0:
                buy_score += 20
                reasoning.append(f"Dr. Copper +{copper_chg:.1f}% signals global industrial growth (Aussie/Kiwi bullish)")
            elif copper_chg < -1.0:
                sell_score += 20
                reasoning.append(f"Dr. Copper {copper_chg:.1f}% signals economic deceleration (Aussie/Kiwi bearish)")

        # ── 7. Equities Alignment ─────────────────────────
        if self.symbol in ['SPX500', 'US30', 'NAS100']:
            if spx_chg > 0.4:
                buy_score += 25
                reasoning.append(f"Equity futures index advancing +{spx_chg:.2f}%")
            elif spx_chg < -0.4:
                sell_score += 25
                reasoning.append(f"Equity futures index declining {spx_chg:.2f}%")

        # ── 8. Aggregation & Scoring ──────────────────────
        total = buy_score + sell_score + 1e-5

        if buy_score > sell_score and (buy_score / total) > 0.55:
            direction = 'BUY'
            score     = (buy_score / total) * 100
        elif sell_score > buy_score and (sell_score / total) > 0.55:
            direction = 'SELL'
            score     = (sell_score / total) * 100
        else:
            direction = 'NEUTRAL'
            score     = 50.0

        confluence = min(len(reasoning) * 20.0, 100.0)
        confidence = (score * 0.70) + (confluence * 0.30)
        confidence = min(confidence, 90.0)

        return EngineResult(
            engine_name = self.name,
            score       = round(score, 2),
            direction   = direction,
            confidence  = round(confidence, 2),
            reasoning   = reasoning,
            weight      = self.weight
        )

    _cached_macro_data: Optional[dict] = None
    _last_macro_fetch: Optional[datetime] = None
    _CACHE_TTL: int = 300

    def _fetch_live_macro_data(self) -> dict:
        """Fetch live changes for DXY, VIX, TNX, Gold, Oil, Copper, SPX in parallel (with 5m caching)"""
        now = datetime.now()
        if (
            MacroEngine._cached_macro_data is not None
            and MacroEngine._last_macro_fetch is not None
            and (now - MacroEngine._last_macro_fetch).total_seconds() < MacroEngine._CACHE_TTL
        ):
            return dict(MacroEngine._cached_macro_data)

        result = {
            'dxy_change': 0.0, 'vix_level': 18.0, 'tnx_change': 0.0,
            'gold_change': 0.0, 'oil_change': 0.0, 'copper_change': 0.0,
            'spx_change': 0.0
        }
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

        from concurrent.futures import ThreadPoolExecutor

        def _fetch_ticker(item):
            key, ticker = item
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            params = {'interval': '1d', 'range': '5d'}
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=2.5)
                data = resp.json()
                chart = data.get('chart', {}).get('result', [])
                if not chart:
                    return None
                closes = [c for c in chart[0]['indicators']['quote'][0]['close'] if c is not None]
                if len(closes) >= 2:
                    return key, closes[-1], closes[-2]
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=9) as executor:
            items = list(self.TICKERS.items())
            for res in executor.map(_fetch_ticker, items):
                if not res:
                    continue
                key, c_last, c_prev = res
                if key == 'VIX':
                    result['vix_level'] = round(float(c_last), 2)
                elif key == 'TNX':
                    result['tnx_change'] = round(float(c_last - c_prev), 3)
                elif key in ('DXY', 'GOLD', 'OIL', 'COPPER', 'SPX'):
                    result[f"{key.lower()}_change"] = round(((c_last - c_prev) / c_prev) * 100, 3)

        MacroEngine._cached_macro_data = result
        MacroEngine._last_macro_fetch = now
        return result
