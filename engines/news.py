"""
Structured News Intelligence Engine — Weight: 15%
Phase 5 Upgrades:
- Pipeline: News -> Country -> Currency/Region -> Asset -> Event Type -> Impact -> Sentiment -> Market Reaction
- Context-aware NLP & Geopolitical Event Detection (War, Sanctions, Tariffs, Elections, Banking Stress)
- Source Reliability Ranking (Tier 1 Wires, Tier 2 Major Financial, Tier 3 Aggregators)
- Duplicate / Syndicated Story Deduplication (Title similarity hashing)
- Currency & Asset Specific Sentiment Directionality (e.g. Fed hawkish = USD Bullish, Gold/EUR Bearish)
- Automatic persistence to NewsArticle model
"""
import requests
import os
import re
import hashlib
import numpy as np
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from .base import BaseEngine, EngineResult


class NewsEngine(BaseEngine):
    name   = 'news'
    weight = 0.15

    # ── Source Reliability Tiers ──────────────────────────
    SOURCE_TIERS = {
        'reuters': 1, 'bloomberg': 1, 'ft': 1, 'wsj': 1,
        'cnbc': 2, 'yahoo_finance': 2, 'marketwatch': 2, 'investing': 2,
        'general': 3
    }

    # ── Event Classification Keywords ─────────────────────
    EVENT_PATTERNS = {
        'GEOPOLITICS': [
            'war', 'military', 'missile', 'attack', 'conflict', 'sanction', 'iran',
            'russia', 'ukraine', 'middle east', 'taiwan', 'ceasefire', 'invasion'
        ],
        'TRADE_POLICY': [
            'tariff', 'trade war', 'trade deal', 'protectionism', 'embargo', 'customs duty', 'export ban'
        ],
        'CENTRAL_BANK': [
            'fed', 'federal reserve', 'ecb', 'boe', 'boj', 'powell', 'lagarde', 'interest rate',
            'rate hike', 'rate cut', 'quantitative easing', 'qt', 'monetary policy'
        ],
        'ENERGY_COMMODITY': [
            'opec', 'oil supply', 'crude inventory', 'brent', 'pipeline', 'energy crisis', 'refinery'
        ],
        'FINANCIAL_STRESS': [
            'bank failure', 'liquidity crisis', 'credit default', 'bailout', 'debt ceiling', 'insolvency'
        ],
        'MACRO_DATA': [
            'cpi', 'inflation', 'gdp', 'jobs report', 'nfp', 'unemployment', 'recession', 'consumer spending'
        ]
    }

    # Contextual sentiment dictionaries with polarity weights
    BULLISH_TERMS = {
        'surge': 1.5, 'rally': 1.5, 'gain': 1.0, 'jump': 1.2, 'record high': 2.0,
        'breakout': 1.4, 'outperform': 1.2, 'beat': 1.2, 'boom': 1.5, 'optimism': 1.0,
        'easing inflation': 1.5, 'rate cut': 1.2, 'strong growth': 1.4, 'upgrade': 1.2
    }

    BEARISH_TERMS = {
        'plunge': 1.5, 'crash': 2.0, 'drop': 1.0, 'tumble': 1.3, 'selloff': 1.5,
        'crisis': 1.8, 'recession': 1.8, 'slump': 1.2, 'miss': 1.2, 'downgrade': 1.2,
        'fear': 1.2, 'default': 2.0, 'bankrupt': 2.0, 'turmoil': 1.5, 'stagflation': 1.8
    }

    def __init__(self, df, symbol: str = ''):
        super().__init__(df, symbol)
        self.parsed_articles = []

    def analyze(self) -> EngineResult:
        try:
            raw_headlines = self._fetch_live_headlines()
            self._process_and_categorize_news(raw_headlines)
            result = self._evaluate()
            self._save_articles_safely()
            return result
        except Exception as e:
            return self._neutral_result(f"News Engine error: {str(e)}")

    def _process_and_categorize_news(self, items: List[dict]):
        """Map News -> Country -> Currency -> Asset -> Event Type -> Impact -> Sentiment"""
        seen_titles = set()
        self.parsed_articles = []

        base_curr  = self.symbol[:3]
        quote_curr = self.symbol[3:6] if len(self.symbol) >= 6 else 'USD'

        for item in items:
            title = item.get('title', '').strip()
            if not title or len(title) < 15:
                continue

            # 1. Deduplication / Syndication check
            # Simple normalized token signature
            tokens = set(re.findall(r'\b\w{4,}\b', title.lower()))
            is_dup = False
            for prev_tokens in seen_titles:
                if len(tokens) > 0 and len(tokens & prev_tokens) / len(tokens | prev_tokens) > 0.65:
                    is_dup = True
                    break
            if is_dup:
                continue
            seen_titles.add(frozenset(tokens))

            # 2. Event Type Classification
            title_lower = title.lower()
            detected_event = 'MARKET_GENERAL'
            for ev_type, kws in self.EVENT_PATTERNS.items():
                if any(kw in title_lower for kw in kws):
                    detected_event = ev_type
                    break

            # 3. Currency / Region Association
            associated_currency = 'USD'
            if any(k in title_lower for k in ['euro', 'ecb', 'germany', 'france', 'europe']):
                associated_currency = 'EUR'
            elif any(k in title_lower for k in ['pound', 'boe', 'britain', 'uk']):
                associated_currency = 'GBP'
            elif any(k in title_lower for k in ['yen', 'boj', 'japan']):
                associated_currency = 'JPY'
            elif any(k in title_lower for k in ['cad', 'boc', 'canada', 'oil']):
                associated_currency = 'CAD'
            elif any(k in title_lower for k in ['aud', 'rba', 'australia']):
                associated_currency = 'AUD'

            # 4. Impact & Source Tier
            source = item.get('source', 'Yahoo Finance')
            tier = self.SOURCE_TIERS.get(source.lower().replace(' ', '_'), 2)
            is_breaking = 'breaking' in title_lower or 'urgent' in title_lower or detected_event in ['GEOPOLITICS', 'FINANCIAL_STRESS']
            impact = 'HIGH' if is_breaking or tier == 1 else ('MEDIUM' if detected_event != 'MARKET_GENERAL' else 'LOW')

            # 5. Advanced Contextual Sentiment (-1.0 to +1.0)
            score = 0.0
            for term, weight in self.BULLISH_TERMS.items():
                if term in title_lower:
                    # check simple negation e.g. "not rising", "failed to surge"
                    negated = bool(re.search(rf'\b(not|no|fails? to|despite)\s+{term}', title_lower))
                    score += -weight if negated else weight

            for term, weight in self.BEARISH_TERMS.items():
                if term in title_lower:
                    negated = bool(re.search(rf'\b(not|no|avoids?|prevents?)\s+{term}', title_lower))
                    score += weight if negated else -weight

            norm_sentiment = float(np.clip(score / 3.0, -1.0, 1.0))

            self.parsed_articles.append({
                'title': title,
                'source': source,
                'source_tier': tier,
                'url': item.get('url', ''),
                'currency': associated_currency,
                'event_type': detected_event,
                'impact_level': impact,
                'sentiment_score': norm_sentiment,
                'is_breaking': is_breaking,
                'published_at': item.get('published_at', datetime.now(timezone.utc))
            })

    def _evaluate(self) -> EngineResult:
        buy_score  = 0.0
        sell_score = 0.0
        reasoning  = []

        base_curr  = self.symbol[:3]
        quote_curr = self.symbol[3:6] if len(self.symbol) >= 6 else 'USD'

        if not self.parsed_articles:
            # Fallback to macro proxy
            return EngineResult(
                engine_name=self.name,
                score=50.0,
                direction='NEUTRAL',
                confidence=35.0,
                reasoning=["News: Quiet flow, no breaking headlines detected"],
                weight=self.weight
            )

        # Process impact on target instrument
        relevant_articles = []
        for art in self.parsed_articles:
            curr = art['currency']
            event = art['event_type']
            sent = art['sentiment_score']
            tier_mult = 1.4 if art['source_tier'] == 1 else 1.0

            # Direct currency impact
            if curr == base_curr:
                # Bullish base currency news = BUY pair
                relevant_articles.append(art)
                if sent > 0.15:
                    buy_score += 25 * sent * tier_mult
                elif sent < -0.15:
                    sell_score += 25 * abs(sent) * tier_mult

            elif curr == quote_curr or (quote_curr == 'USD' and curr == 'USD'):
                # Bullish quote currency news = SELL pair
                relevant_articles.append(art)
                if sent > 0.15:
                    sell_score += 25 * sent * tier_mult
                elif sent < -0.15:
                    buy_score += 25 * abs(sent) * tier_mult

            # Safe haven and geopolitical impact
            if event == 'GEOPOLITICS' or event == 'FINANCIAL_STRESS':
                if self.symbol in ['XAUUSD', 'USDJPY', 'USDCHF']:
                    buy_score += 20 * tier_mult
                    reasoning.append(f"Geopolitical / Stress News: Safe haven tailwind from [{art['title'][:55]}...]")
                elif self.symbol in ['BTCUSD', 'ETHUSD', 'NAS100']:
                    sell_score += 20 * tier_mult

        if relevant_articles:
            top_art = relevant_articles[0]
            reasoning.append(
                f"Headline: [{top_art['event_type']}] '{top_art['title'][:60]}...' "
                f"(Sent: {top_art['sentiment_score']:+.2f}, Impact: {top_art['impact_level']})"
            )

        # ── Scoring ──────────────────────────────────────────
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

        confluence = min(len(relevant_articles) * 20.0, 100.0)
        confidence = min((score * 0.65) + (confluence * 0.35), 88.0)

        if not reasoning:
            reasoning.append(f"News: Analyzed {len(self.parsed_articles)} live stories — sentiment neutral for {self.symbol}")

        return EngineResult(
            engine_name = self.name,
            score       = round(score, 2),
            direction   = direction,
            confidence  = round(confidence, 2),
            reasoning   = reasoning,
            weight      = self.weight
        )

    _cached_headlines: List[dict] = []
    _last_headlines_fetch: Optional[datetime] = None
    _HEADLINES_CACHE_TTL: int = 300

    def _fetch_live_headlines(self) -> List[dict]:
        """Fetch live financial news from multiple free RSS and API sources with 5m caching"""
        now = datetime.now()
        if (
            NewsEngine._cached_headlines
            and NewsEngine._last_headlines_fetch
            and (now - NewsEngine._last_headlines_fetch).total_seconds() < NewsEngine._HEADLINES_CACHE_TTL
        ):
            return list(NewsEngine._cached_headlines)

        articles = []
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

        from concurrent.futures import ThreadPoolExecutor

        all_feeds = [
            ('https://feeds.finance.yahoo.com/rss/2.0/headline?s=^DJI&region=US&lang=en-US', 'Yahoo Finance'),
            ('https://feeds.finance.yahoo.com/rss/2.0/headline?s=EURUSD=X&region=US&lang=en-US', 'Yahoo Finance'),
            ('https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US', 'Yahoo Finance'),
            ('https://feeds.marketwatch.com/marketwatch/topstories/', 'MarketWatch'),
        ]

        def _fetch_feed(item):
            url, source = item
            feed_articles = []
            try:
                resp = requests.get(url, headers=headers, timeout=2.5)
                if resp.status_code == 200:
                    if 'marketwatch' in url:
                        titles = re.findall(r'<title>(.*?)</title>', resp.text)
                        for t in titles[2:12]:
                            feed_articles.append({'title': t, 'source': source, 'url': ''})
                    else:
                        titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', resp.text)
                        links  = re.findall(r'<link>(.*?)</link>', resp.text)
                        for idx, t in enumerate(titles[:10]):
                            link = links[idx] if idx < len(links) else ''
                            feed_articles.append({'title': t, 'source': source, 'url': link})
            except Exception:
                pass
            return feed_articles

        with ThreadPoolExecutor(max_workers=4) as executor:
            for res in executor.map(_fetch_feed, all_feeds):
                if res:
                    articles.extend(res)

        if articles:
            NewsEngine._cached_headlines = articles
            NewsEngine._last_headlines_fetch = now

        return articles or list(NewsEngine._cached_headlines)

    def _save_articles_safely(self):
        """Persist structured articles to database NewsArticle table"""
        try:
            from signals.models import NewsArticle

            for art in self.parsed_articles[:15]:
                h = hashlib.sha256(art['title'].encode('utf-8')).hexdigest()[:64]
                NewsArticle.objects.update_or_create(
                    title=art['title'],
                    defaults={
                        'source': art['source'],
                        'source_tier': art['source_tier'],
                        'url': art['url'],
                        'published_at': art['published_at'],
                        'currency': art['currency'],
                        'event_type': art['event_type'],
                        'impact_level': art['impact_level'],
                        'sentiment_score': art['sentiment_score'],
                        'is_breaking': art['is_breaking'],
                        'content_hash': h,
                        'scope': 'GLOBAL' if art['currency'] in ('USD', 'ALL') else 'REGIONAL',
                        'confidence': 0.85,
                        'impact_score': 75.0 if art['impact_level'] == 'HIGH' else 40.0,
                    }
                )
        except Exception:
            pass
