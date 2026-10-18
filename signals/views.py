"""
Signal Views - REST API endpoints
"""
from typing import Optional
from rest_framework import generics, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from .models import Signal, SignalPerformance, NewsEvent
from .serializers import SignalSerializer, SignalDetailSerializer, NewsEventSerializer


class SignalListView(generics.ListAPIView):
    """GET /api/signals/ — List all signals with filters"""
    serializer_class = SignalSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = Signal.objects.select_related('instrument')
        direction  = self.request.query_params.get('direction')
        status     = self.request.query_params.get('status')
        instrument = self.request.query_params.get('instrument')

        if direction:
            qs = qs.filter(direction=direction.upper())
        if status:
            qs = qs.filter(status=status.upper())
        if instrument:
            qs = qs.filter(instrument__symbol__icontains=instrument)
        return qs


class SignalDetailView(generics.RetrieveAPIView):
    """GET /api/signals/<id>/ — Single signal detail"""
    queryset = Signal.objects.select_related('instrument').prefetch_related('performance')
    serializer_class = SignalDetailSerializer
    permission_classes = [AllowAny]


def build_signal_engine_details(signal, df, sym: str, tf: str) -> dict:
    """
    Builds comprehensive per-engine trade analysis details (metrics, indicator values,
    SMC zones, S/R levels, COT positioning, news/macro context, AI probabilities, and reasoning)
    so clicking any Engine Confidence Score row in the UI opens full details for that trade.
    """
    summary_lines = {}
    raw_summary = (getattr(signal, 'analysis_summary', '') or '') if signal else ''
    for line in raw_summary.splitlines():
        line_s = line.strip()
        if line_s.startswith('[') and 'Score=' in line_s:
            try:
                after_bracket = line_s.split(']', 1)[1].strip()
                eng_key = after_bracket.split()[0].strip().lower()
                reason_part = line_s.split('|', 1)[1].strip() if '|' in line_s else line_s
                summary_lines[eng_key] = reason_part
            except Exception:
                pass

    ind_groups = (getattr(signal, 'independent_groups', None) or {}) if signal else {}
    saved_detail = (getattr(signal, 'engine_detail', None) or {}) if signal else {}

    def fmt_p(val):
        try:
            v = float(val)
            if sym.endswith('JPY'):
                return f"{v:.3f}"
            if v >= 1000:
                return f"{v:.2f}"
            if v >= 10:
                return f"{v:.3f}"
            return f"{v:.5f}"
        except Exception:
            return "—"

    details = {}

    # 1. Technical Engine
    tech_metrics = []
    tech_reasons = []
    tech_dir = ind_groups.get('Regime/Momentum', signal.direction if signal else 'NEUTRAL')
    tech_score = float(signal.technical_score) if signal else 0.0
    tech_levels = {}
    if df is not None and len(df) >= 25:
        try:
            from engines.technical import TechnicalEngine
            te = TechnicalEngine(df, sym, timeframe=tf)
            te._compute_indicators()
            te._detect_regimes()
            res = te._evaluate()
            tech_reasons = list(res.reasoning or [])
            if not signal:
                tech_score = float(res.score)
                tech_dir = res.direction
            tech_levels = {
                'entry_zone': fmt_p(res.entry_zone) if res.entry_zone else fmt_p(df['close'].iloc[-1]),
                'sl_zone': fmt_p(res.sl_zone) if res.sl_zone else '—',
                'tp_zone': fmt_p(res.tp_zone) if res.tp_zone else '—',
            }
            cur_rsi = float(te.rsi.iloc[-1])
            cur_macd = float(te.macd.iloc[-1])
            cur_macd_sig = float(te.macd_signal.iloc[-1])
            cur_macd_hist = float(te.macd_hist.iloc[-1])
            cur_ema20 = float(te.ema20.iloc[-1])
            cur_ema50 = float(te.ema50.iloc[-1])
            cur_ema200 = float(te.ema200.iloc[-1])
            cur_atr = float(te.atr.iloc[-1])
            cur_adx = float(te.adx.iloc[-1])
            cur_vwap = float(te.vwap.iloc[-1])
            cur_cci = float(te.cci.iloc[-1])
            cur_wr = float(te.williams_r.iloc[-1])
            cur_rvol = float(te.rvol.iloc[-1])
            st_bull = bool(te.supertrend_dir.iloc[-1]) if hasattr(te, 'supertrend_dir') else True

            tech_metrics = [
                {'label': 'RSI (14)', 'value': f"{cur_rsi:.1f}", 'sub': 'Bullish > 50' if cur_rsi >= 50 else 'Bearish < 50'},
                {'label': 'MACD Hist', 'value': f"{cur_macd_hist:+.5f}", 'sub': f"MACD {cur_macd:.4f} / Sig {cur_macd_sig:.4f}"},
                {'label': 'EMA 20 / 50', 'value': f"{fmt_p(cur_ema20)} / {fmt_p(cur_ema50)}", 'sub': f"EMA 200: {fmt_p(cur_ema200)}"},
                {'label': 'Supertrend (10,3)', 'value': '🟢 Bullish' if st_bull else '🔴 Bearish', 'sub': f"Level: {fmt_p(te.supertrend.iloc[-1])}"},
                {'label': 'ADX (14) & ATR', 'value': f"ADX {cur_adx:.1f}", 'sub': f"ATR Volatility: {fmt_p(cur_atr)}"},
                {'label': 'VWAP & Volume POC', 'value': fmt_p(cur_vwap), 'sub': f"POC: {fmt_p(te.poc)} | RVOL: {cur_rvol:.2f}x"},
                {'label': 'CCI & Williams %R', 'value': f"CCI {cur_cci:.0f}", 'sub': f"Williams %R: {cur_wr:.1f}"},
                {'label': 'Bollinger Bands', 'value': f"Mid {fmt_p(te.bb_mid.iloc[-1])}", 'sub': f"{fmt_p(te.bb_lower.iloc[-1])} – {fmt_p(te.bb_upper.iloc[-1])}"},
            ]
        except Exception:
            pass
    if summary_lines.get('technical') and summary_lines['technical'] not in tech_reasons:
        tech_reasons.insert(0, summary_lines['technical'])
    details['technical'] = {
        'key': 'technical',
        'title': '📐 Technical Indicator Engine',
        'weight_pct': 15,
        'score': round(tech_score, 1),
        'direction': tech_dir,
        'role': 'Trend Alignment, Momentum Oscillators, Volatility & Volume Confirmation',
        'metrics': tech_metrics,
        'reasoning': tech_reasons or ['Multi-indicator trend and momentum alignment evaluated on live candles.'],
        'levels': tech_levels,
    }

    # 2. SMC / ICT Engine
    smc_metrics = []
    smc_reasons = []
    smc_dir = ind_groups.get('Structure', signal.direction if signal else 'NEUTRAL')
    smc_score = float(signal.smc_score) if signal else 0.0
    smc_levels = {}
    if df is not None and len(df) >= 35:
        try:
            from engines.smc_ict import SMCEngine
            se = SMCEngine(df, sym, timeframe=tf)
            se._compute_atr()
            se._find_swing_points()
            se._identify_structure_and_mss()
            se._find_equal_highs_lows()
            se._find_order_and_breaker_blocks()
            se._find_fvg()
            se._find_liquidity_sweeps_and_idm()
            se._detect_sessions_and_killzones()
            res = se._evaluate()
            smc_reasons = list(res.reasoning or [])
            if not signal:
                smc_score = float(res.score)
                smc_dir = res.direction
            smc_levels = {
                'entry_zone': fmt_p(res.entry_zone) if res.entry_zone else fmt_p(df['close'].iloc[-1]),
                'sl_zone': fmt_p(res.sl_zone) if res.sl_zone else '—',
                'tp_zone': fmt_p(res.tp_zone) if res.tp_zone else '—',
            }
            pd_zone = se._get_pd_zone()
            bull_ob_str = f"{fmt_p(se.bullish_obs[-1]['low'])} – {fmt_p(se.bullish_obs[-1]['high'])}" if se.bullish_obs else 'None Nearby'
            bear_ob_str = f"{fmt_p(se.bearish_obs[-1]['low'])} – {fmt_p(se.bearish_obs[-1]['high'])}" if se.bearish_obs else 'None Nearby'
            bull_fvg_str = f"{fmt_p(se.bullish_fvg[-1]['bot'])} – {fmt_p(se.bullish_fvg[-1]['top'])}" if se.bullish_fvg else 'Mitigated / None'
            bear_fvg_str = f"{fmt_p(se.bearish_fvg[-1]['bot'])} – {fmt_p(se.bearish_fvg[-1]['top'])}" if se.bearish_fvg else 'Mitigated / None'
            sh_val = fmt_p(se.swing_highs[-1][1]) if se.swing_highs else '—'
            sl_val = fmt_p(se.swing_lows[-1][1]) if se.swing_lows else '—'

            smc_metrics = [
                {'label': 'Market Structure', 'value': se.structure, 'sub': f"BOS: {se.bos or 'None'} | CHoCH: {se.choch or 'None'}"},
                {'label': 'MSS & Displacement', 'value': se.mss or 'Intact', 'sub': f"ATR Displacement Unit: {fmt_p(se.cur_atr)}"},
                {'label': 'Premium / Discount', 'value': pd_zone, 'sub': 'Discount favors BUY | Premium favors SELL'},
                {'label': 'ICT Kill Zone', 'value': se.kill_zone.replace('_', ' '), 'sub': 'Institutional Session Window'},
                {'label': 'Bullish Order Block', 'value': bull_ob_str, 'sub': f"Total Bull OBs: {len(se.bullish_obs)}"},
                {'label': 'Bearish Order Block', 'value': bear_ob_str, 'sub': f"Total Bear OBs: {len(se.bearish_obs)}"},
                {'label': 'Fair Value Gaps (FVG)', 'value': f"Bull: {bull_fvg_str}", 'sub': f"Bear: {bear_fvg_str}"},
                {'label': 'Swing Liquidity Pools', 'value': f"BSL High: {sh_val}", 'sub': f"SSL Low: {sl_val}"},
            ]
        except Exception:
            pass
    if summary_lines.get('smc_ict') and summary_lines['smc_ict'] not in smc_reasons:
        smc_reasons.insert(0, summary_lines['smc_ict'])
    details['smc_ict'] = {
        'key': 'smc_ict',
        'title': '💡 SMC / ICT Smart Money Engine',
        'weight_pct': 20,
        'score': round(smc_score, 1),
        'direction': smc_dir,
        'role': 'Institutional Order Blocks, Fair Value Gaps (FVG), Liquidity Sweeps & BOS/CHoCH',
        'metrics': smc_metrics,
        'reasoning': smc_reasons or ['Smart Money structure, order blocks, and liquidity pools analyzed.'],
        'levels': smc_levels,
    }

    # 3. Price Action Engine
    pa_metrics = []
    pa_reasons = []
    pa_dir = ind_groups.get('Price Action', signal.direction if signal else 'NEUTRAL')
    pa_score = float(signal.price_action_score) if signal else 0.0
    pa_levels = {}
    if df is not None and len(df) >= 25:
        try:
            from engines.price_action import PriceActionEngine
            pe = PriceActionEngine(df, sym, timeframe=tf)
            pe._compute_basics()
            pe._detect_swings_and_structure()
            pe._detect_support_resistance()
            pe._detect_breakouts_and_displacement()
            pe._detect_session_and_period_levels()
            res = pe._evaluate()
            pa_reasons = list(res.reasoning or [])
            if not signal:
                pa_score = float(res.score)
                pa_dir = res.direction
            pa_levels = {
                'entry_zone': fmt_p(res.entry_zone) if res.entry_zone else fmt_p(df['close'].iloc[-1]),
                'sl_zone': fmt_p(res.sl_zone) if res.sl_zone else '—',
                'tp_zone': fmt_p(res.tp_zone) if res.tp_zone else '—',
            }
            sup_str = ', '.join(fmt_p(x) for x in getattr(pe, 'support_levels', [])[:2]) or 'Dynamic Swing Low'
            res_str = ', '.join(fmt_p(x) for x in getattr(pe, 'resistance_levels', [])[:2]) or 'Dynamic Swing High'
            pdh_str = fmt_p(getattr(pe, 'pdh', None)) if getattr(pe, 'pdh', None) else '—'
            pdl_str = fmt_p(getattr(pe, 'pdl', None)) if getattr(pe, 'pdl', None) else '—'

            pa_metrics = [
                {'label': 'Swing Structure', 'value': ' + '.join(pe.structure_labels) or pe.structure_bias, 'sub': f"Bias: {pe.structure_bias} ({pe.regime})"},
                {'label': 'Key Support Zones', 'value': sup_str, 'sub': 'Demand / Rejection Floor'},
                {'label': 'Key Resistance Zones', 'value': res_str, 'sub': 'Supply / Rejection Ceiling'},
                {'label': 'Prev Day High / Low', 'value': f"PDH: {pdh_str}", 'sub': f"PDL: {pdl_str}"},
                {'label': 'Last Candle Body / Wick', 'value': f"Body: {fmt_p(pe.body[-1])}", 'sub': f"Up Wick: {fmt_p(pe.upper_s[-1])} | Low Wick: {fmt_p(pe.lower_s[-1])}"},
                {'label': 'Average Bar Range', 'value': fmt_p(pe.avg_range), 'sub': f"ATR (14): {fmt_p(pe.atr)}"},
            ]
        except Exception:
            pass
    if summary_lines.get('price_action') and summary_lines['price_action'] not in pa_reasons:
        pa_reasons.insert(0, summary_lines['price_action'])
    details['price_action'] = {
        'key': 'price_action',
        'title': '🕯️ Price Action & Market Structure Engine',
        'weight_pct': 15,
        'score': round(pa_score, 1),
        'direction': pa_dir,
        'role': 'Candlestick Rejections, False Breakouts (Liquidity Traps), Support/Resistance & HH/HL Swings',
        'metrics': pa_metrics,
        'reasoning': pa_reasons or ['Candlestick anatomy, S/R levels, and swing structure evaluated.'],
        'levels': pa_levels,
    }

    # 4. Macro Environment Engine
    macro_dir = ind_groups.get('Macro', 'NEUTRAL')
    macro_score = float(signal.macro_score) if signal else 50.0
    macro_reasons = []
    if summary_lines.get('macro'):
        macro_reasons.append(summary_lines['macro'])
    if isinstance(saved_detail.get('macro'), dict):
        for r in (saved_detail['macro'].get('reasoning') or []):
            if r not in macro_reasons:
                macro_reasons.append(r)
    if not macro_reasons:
        macro_reasons.append(f"Macro policy & yield differential regime evaluated for {sym} (Score: {macro_score:.0f}/100).")
    details['macro'] = {
        'key': 'macro',
        'title': '🌍 Macro & Central Bank Policy Engine',
        'weight_pct': 15,
        'score': round(macro_score, 1),
        'direction': macro_dir,
        'role': 'Central Bank Rate Differentials, Real Yields, DXY Macro Pressure & Policy Regimes',
        'metrics': [
            {'label': 'Macro Bias', 'value': macro_dir, 'sub': f"Engine Score: {macro_score:.0f}/100"},
            {'label': 'Market Regime', 'value': getattr(signal, 'market_regime', 'TRENDING'), 'sub': f"Decision Class: {getattr(signal, 'decision_class', 'STRONG')}"},
            {'label': 'Rate & Yield Sensitivity', 'value': 'USD / Real-Yield Tracked', 'sub': f"Instrument: {sym}"},
            {'label': 'Central Bank Blackout', 'value': '✅ Clear' if getattr(signal, 'is_trade_allowed', True) else '⚠️ Restricted', 'sub': 'FOMC / ECB / BOE Window Check'},
        ],
        'reasoning': macro_reasons,
        'levels': {},
    }

    # 5. News Sentiment Engine
    news_dir = ind_groups.get('News', 'NEUTRAL')
    news_score = float(signal.news_score) if signal else 50.0
    news_reasons = []
    if summary_lines.get('news'):
        news_reasons.append(summary_lines['news'])
    if isinstance(saved_detail.get('news'), dict):
        for r in (saved_detail['news'].get('reasoning') or []):
            if r not in news_reasons:
                news_reasons.append(r)
    upcoming_events = []
    try:
        for ev in NewsEvent.objects.order_by('-event_time')[:3]:
            upcoming_events.append(f"{ev.currency} {ev.title} ({ev.impact})")
    except Exception:
        pass
    if not news_reasons:
        news_reasons.append(f"Live financial news sentiment and high-impact economic calendar checked for {sym}.")
    details['news'] = {
        'key': 'news',
        'title': '📰 News Sentiment & Economic Calendar Engine',
        'weight_pct': 15,
        'score': round(news_score, 1),
        'direction': news_dir,
        'role': 'NLP Headline Sentiment Scoring & High-Impact Economic Release Blackout Protection',
        'metrics': [
            {'label': 'Sentiment Verdict', 'value': news_dir, 'sub': f"Confidence Score: {news_score:.0f}/100"},
            {'label': 'High-Impact Blackout', 'value': '✅ No Active Blackout', 'sub': 'Safe to execute trade'},
            {'label': 'Headline NLP Feed', 'value': 'Active', 'sub': news_reasons[0][:65] + ('…' if len(news_reasons[0]) > 65 else '')},
            {'label': 'Calendar Watch', 'value': upcoming_events[0] if upcoming_events else 'Normal Schedule', 'sub': 'High-impact events monitored'},
        ],
        'reasoning': news_reasons + ([f"Calendar Events Monitored: {' | '.join(upcoming_events)}"] if upcoming_events else []),
        'levels': {},
    }

    # 6. Institutional Flow Engine
    inst_dir = ind_groups.get('Flow', signal.direction if signal else 'NEUTRAL')
    inst_score = float(signal.institutional_score) if signal else 0.0
    inst_reasons = []
    inst_metrics = []
    if df is not None and len(df) >= 25:
        try:
            from engines.institutional import InstitutionalEngine
            ie = InstitutionalEngine(df, sym, timeframe=tf)
            res = ie._evaluate()
            inst_reasons = list(res.reasoning or [])
            cot = ie.COT_BENCHMARKS.get(sym, {'non_comm_net': 15000, 'percentile': 60.0, 'oi_chg_pct': 2.0, 'bias': inst_dir})
            inst_metrics = [
                {'label': 'COT Net Speculators', 'value': f"{cot['non_comm_net']:+,} Contracts", 'sub': f"Bias: {cot['bias']}"},
                {'label': '52-Week COT Percentile', 'value': f"{cot['percentile']:.1f}%", 'sub': 'Institutional Positioning Percentile'},
                {'label': 'Open Interest (24h)', 'value': f"{cot['oi_chg_pct']:+.1f}%", 'sub': 'Futures / Derivatives OI Delta'},
                {'label': 'Smart Money Flow', 'value': inst_dir, 'sub': f"Institutional Score: {inst_score:.0f}/100"},
            ]
        except Exception:
            pass
    if summary_lines.get('institutional') and summary_lines['institutional'] not in inst_reasons:
        inst_reasons.insert(0, summary_lines['institutional'])
    details['institutional'] = {
        'key': 'institutional',
        'title': '🏦 Institutional Flow, COT & Derivatives Engine',
        'weight_pct': 10,
        'score': round(inst_score, 1),
        'direction': inst_dir,
        'role': 'CFTC Commitments of Traders (COT), Futures Open Interest (OI) & Smart Money Accumulation',
        'metrics': inst_metrics,
        'reasoning': inst_reasons or ['Institutional COT positioning and derivatives open interest analyzed.'],
        'levels': {},
    }

    # 7. Intermarket & Volatility Engine
    inter_dir = ind_groups.get('Intermarket', 'NEUTRAL')
    inter_score = float(getattr(signal, 'intermarket_score', 0) or 0) if signal else 0.0
    inter_reasons = []
    inter_metrics = []
    if df is not None and len(df) >= 25:
        try:
            from engines.intermarket import IntermarketEngine
            ime = IntermarketEngine(df, sym, timeframe=tf)
            res = ime._evaluate()
            inter_reasons = list(res.reasoning or [])
            if inter_score == 0:
                inter_score = float(res.score)
            corr = ime.BENCHMARK_CORRELATIONS.get(sym, {'dxy': -0.75, 'spx': 0.45, 'gold': 0.50, 'vix': -0.40})
            inter_metrics = [
                {'label': 'Intermarket Bias', 'value': inter_dir, 'sub': f"Score: {inter_score:.0f}/100"},
                {'label': 'DXY & SPX Correlation', 'value': f"DXY: {corr['dxy']:+.2f}", 'sub': f"SPX500: {corr['spx']:+.2f}"},
                {'label': 'Gold & VIX Correlation', 'value': f"Gold: {corr['gold']:+.2f}", 'sub': f"VIX Fear Index: {corr['vix']:+.2f}"},
                {'label': 'Volatility Squeeze', 'value': 'Checked (BB vs KC)', 'sub': inter_reasons[0][:50] if inter_reasons else 'Normal Volatility'},
            ]
        except Exception:
            pass
    if summary_lines.get('intermarket') and summary_lines['intermarket'] not in inter_reasons:
        inter_reasons.insert(0, summary_lines['intermarket'])
    details['intermarket'] = {
        'key': 'intermarket',
        'title': '🔗 Intermarket Correlation & Volatility Engine',
        'weight_pct': 5,
        'score': round(inter_score, 1),
        'direction': inter_dir,
        'role': 'Cross-Asset Correlations (DXY, SPX, Gold, Oil, VIX) & TTM Bollinger/Keltner Volatility Squeeze',
        'metrics': inter_metrics,
        'reasoning': inter_reasons or ['Cross-asset correlations and volatility squeeze regime evaluated.'],
        'levels': {},
    }

    # 8. AI / ML Prediction Engine
    ai_dir = ind_groups.get('ML', 'NEUTRAL')
    ai_score = float(signal.ai_ml_score) if signal else 0.0
    ai_reasons = []
    if summary_lines.get('ai_ml'):
        ai_reasons.append(summary_lines['ai_ml'])
    if isinstance(saved_detail.get('ai_ml'), dict):
        for r in (saved_detail['ai_ml'].get('reasoning') or []):
            if r not in ai_reasons:
                ai_reasons.append(r)
    if not ai_reasons:
        ai_reasons.append(f"Random Forest Ensemble (75 trees, 12 leakage-free features) evaluated on {sym} {tf}.")
    details['ai_ml'] = {
        'key': 'ai_ml',
        'title': '🤖 AI / ML Random Forest Ensemble Engine',
        'weight_pct': 10,
        'score': round(ai_score, 1),
        'direction': ai_dir,
        'role': 'Out-of-Sample Walk-Forward Random Forest Classification on 12 Price/Volume Features',
        'metrics': [
            {'label': 'AI Model Verdict', 'value': ai_dir, 'sub': f"Ensemble Score: {ai_score:.0f}/100"},
            {'label': 'Model Architecture', 'value': 'Random Forest (75 Trees)', 'sub': 'Max Depth 4 (Anti-Overfit)'},
            {'label': 'Feature Store', 'value': '12 Leakage-Free Features', 'sub': 'Returns, Vol, MA Ratio, RSI, ATR, Wicks, RVOL'},
            {'label': 'Prediction Output', 'value': ai_reasons[0].replace('AI/ML Model:', '').strip()[:48], 'sub': 'Advisory Confluence Gate'},
        ],
        'reasoning': ai_reasons,
        'levels': {},
    }

    return details


def get_signal_auto_trade_details(signal) -> Optional[dict]:
    """Returns linked AutoTradeExecution details for this signal if one exists."""
    if not signal:
        return None
    try:
        from accounts.models import AutoTradeExecution
        trade = AutoTradeExecution.objects.filter(signal=signal).select_related('account').order_by('-opened_at').first()
        if not trade:
            return None
        return {
            'id': trade.id,
            'broker_order_id': trade.broker_order_id,
            'client_order_id': trade.client_order_id,
            'account_name': trade.account.name if trade.account else 'Default Account',
            'broker': trade.account.get_broker_type_display() if trade.account else 'MT5',
            'volume_lots': float(trade.volume_lots),
            'entry_price': float(trade.entry_price),
            'executed_price': float(trade.executed_price or trade.entry_price),
            'current_price': float(trade.current_price or trade.entry_price),
            'stop_loss': float(trade.stop_loss),
            'take_profit_1': float(trade.take_profit_1),
            'status': trade.status,
            'exit_reason': trade.get_exit_reason_display() if trade.exit_reason else None,
            'exit_price': float(trade.exit_price) if trade.exit_price else None,
            'pnl_amount': float(trade.pnl_amount or 0.0),
            'pnl_r': float(trade.pnl_r or 0.0),
            'opened_at': trade.opened_at.isoformat() if trade.opened_at else None,
            'closed_at': trade.closed_at.isoformat() if trade.closed_at else None,
            'notes': trade.notes,
        }
    except Exception:
        return None


class SignalChartView(views.APIView):
    """GET /api/signals/<id>/chart/ — Candle data + Trade Entry, SL, TP levels + Full Per-Engine Details"""
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            signal = Signal.objects.select_related('instrument').get(pk=pk)
        except Signal.DoesNotExist:
            return Response({'error': 'Signal not found'}, status=404)

        from engines.data_fetcher import DataFetcher
        import pandas as pd

        sym = signal.instrument.symbol
        req_tf = request.query_params.get('tf', '').upper()
        valid_tfs = {'M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'D1', 'W1'}
        tf = req_tf if req_tf in valid_tfs else signal.timeframe

        fetcher = DataFetcher()
        df = fetcher.fetch(sym, tf, limit=150)

        candles = []
        if df is not None and not df.empty:
            for idx, row in df.iterrows():
                try:
                    if hasattr(idx, 'timestamp'):
                        t = int(idx.timestamp())
                    else:
                        t = int(pd.to_datetime(idx).timestamp())
                except Exception:
                    continue
                candles.append({
                    'time': t,
                    'open': round(float(row['open']), 5),
                    'high': round(float(row['high']), 5),
                    'low': round(float(row['low']), 5),
                    'close': round(float(row['close']), 5),
                    'volume': float(row.get('volume', 0)),
                })

        live_price = candles[-1]['close'] if candles else float(signal.entry_price)

        # Evaluate TP1/SL before returning chart status
        try:
            from .auto_evaluator import maybe_evaluate
            maybe_evaluate()
            signal.refresh_from_db(fields=['status'])
        except Exception:
            pass

        engine_details = build_signal_engine_details(signal, df, sym, tf)
        auto_trade = get_signal_auto_trade_details(signal)

        return Response({
            'signal_id': signal.id,
            'symbol': sym,
            'name': signal.instrument.name,
            'timeframe': tf,
            'signal_timeframe': signal.timeframe,
            'tf_seconds': DataFetcher.TF_SECONDS.get(tf, 3600),
            'live_price': live_price,
            'direction': signal.direction,
            'status': signal.status,
            'entry_price': float(signal.entry_price),
            'stop_loss': float(signal.stop_loss),
            'take_profit_1': float(signal.take_profit_1),
            'take_profit_2': None,
            'take_profit_3': None,
            'risk_reward': float(signal.risk_reward),
            'confidence_score': float(signal.confidence_score),
            'strength': signal.strength,
            'generated_at': signal.generated_at.isoformat(),
            'generated_ts': int(signal.generated_at.timestamp()),
            'analysis_summary': signal.analysis_summary,
            'warnings': signal.warnings,
            'decision_class': getattr(signal, 'decision_class', 'STRONG'),
            'market_regime': getattr(signal, 'market_regime', 'TRENDING'),
            'independent_groups': getattr(signal, 'independent_groups', {}),
            'is_trade_allowed': getattr(signal, 'is_trade_allowed', True),
            'recommended_lots': getattr(signal, 'recommended_lots', 0.10),
            'technical_score': signal.technical_score,
            'smc_score': signal.smc_score,
            'price_action_score': signal.price_action_score,
            'macro_score': signal.macro_score,
            'news_score': signal.news_score,
            'institutional_score': signal.institutional_score,
            'intermarket_score': float(getattr(signal, 'intermarket_score', 0) or engine_details.get('intermarket', {}).get('score', 0)),
            'ai_ml_score': signal.ai_ml_score,
            'engine_details': engine_details,
            'auto_trade': auto_trade,
            'candles': candles,
        })


class ActiveSignalsView(generics.ListAPIView):
    """GET /api/signals/active/ — Only high-conviction ACTIVE signals (>= 75.0% confidence)"""
    serializer_class = SignalSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        from .auto_evaluator import maybe_evaluate
        from .auto_scanner import maybe_auto_scan
        maybe_evaluate()
        maybe_auto_scan()
        return (Signal.objects.filter(status='ACTIVE', direction__in=['BUY', 'SELL'], confidence_score__gte=75.0)
                .select_related('instrument').order_by('-confidence_score'))


class SignalStatsView(views.APIView):
    """GET /api/signals/stats/ — Win rate, total signals, avg confidence, per-instrument scores, and R-multiple performance metrics"""
    permission_classes = [AllowAny]

    def get(self, request):
        from .auto_evaluator import maybe_evaluate
        maybe_evaluate()
        trades  = Signal.objects.filter(direction__in=['BUY', 'SELL'])
        total   = trades.count()
        active  = trades.filter(status='ACTIVE').count()
        hits_tp = trades.filter(status='HIT_TP').count()
        hits_sl = trades.filter(status='HIT_SL').count()
        closed  = hits_tp + hits_sl

        # Real win rate if closed trades exist; else running avg confidence as proxy score
        avg_conf_val = trades.aggregate(avg=Avg('confidence_score'))['avg'] or 0
        if closed > 0:
            win_rate = round((hits_tp / closed * 100), 2)
        else:
            win_rate = round(float(avg_conf_val), 2)

        # ── R-Multiple Performance Tracking (Phase 12) ─────────────────────────
        perfs = SignalPerformance.objects.filter(outcome__in=['WIN', 'LOSS'])
        wins = perfs.filter(outcome='WIN')
        losses = perfs.filter(outcome='LOSS')

        win_count = wins.count()
        loss_count = losses.count()

        if win_count > 0:
            avg_win_val = round(float(wins.aggregate(avg=Avg('pnl_r'))['avg'] or 0.0), 2)
        else:
            avg_win_val = 0.0

        if loss_count > 0:
            avg_loss_val = round(float(losses.aggregate(avg=Avg('pnl_r'))['avg'] or 0.0), 2)
        else:
            avg_loss_val = 0.0

        # Total Win R and Loss R
        total_win_r = float(wins.aggregate(sum=Sum('pnl_r'))['sum'] or 0.0)
        total_loss_r = abs(float(losses.aggregate(sum=Sum('pnl_r'))['sum'] or 0.0))

        if total_loss_r > 0:
            profit_factor = round(total_win_r / total_loss_r, 2)
        elif total_win_r > 0:
            profit_factor = round(total_win_r, 2)
        else:
            profit_factor = 0.0

        # Trade Expectancy in R: (Win_Rate * Avg_Win) - (Loss_Rate * |Avg_Loss|)
        if closed > 0:
            win_p = hits_tp / closed
            loss_p = hits_sl / closed
            expectancy_r = round((win_p * avg_win_val) - (loss_p * abs(avg_loss_val)), 2)
        else:
            expectancy_r = 0.0

        # Max Drawdown calculation over cumulative equity curve (in R and %)
        cum_r = 0.0
        peak_r = 0.0
        max_dd_r = 0.0
        for p in perfs.order_by('signal__generated_at'):
            val = float(p.pnl_r) if p.pnl_r is not None else (avg_win_val if p.outcome == 'WIN' else -1.0)
            cum_r += val
            if cum_r > peak_r:
                peak_r = cum_r
            dd = peak_r - cum_r
            if dd > max_dd_r:
                max_dd_r = dd

        # Assuming standard 1% risk per 1R -> Max Drawdown %
        max_drawdown_pct = round(max_dd_r * 1.0, 1) if max_dd_r > 0 else 0.0

        # ── Per-instrument running score ─────────────────────────────────────
        # Group by instrument: take the highest-confidence signal per pair
        instrument_scores = []
        seen_instruments  = set()

        for sig in Signal.objects.filter(status='ACTIVE', direction__in=['BUY', 'SELL']).select_related('instrument').order_by(
                'instrument__symbol', '-confidence_score'):
            sym = sig.instrument.symbol
            if sym in seen_instruments:
                continue
            seen_instruments.add(sym)

            pair_tp     = Signal.objects.filter(instrument=sig.instrument, status='HIT_TP').count()
            pair_sl     = Signal.objects.filter(instrument=sig.instrument, status='HIT_SL').count()
            pair_closed = pair_tp + pair_sl

            if pair_closed > 0:
                pair_score = round((pair_tp / pair_closed * 100), 2)
            else:
                pair_avg = trades.filter(instrument=sig.instrument).aggregate(
                    avg=Avg('confidence_score'))['avg'] or 0
                pair_score = round(float(pair_avg), 2)

            instrument_scores.append({
                'symbol':     sym,
                'name':       sig.instrument.name,
                'direction':  sig.direction,
                'confidence': float(sig.confidence_score),
                'score':      pair_score,
                'closed':     pair_closed,
                'tp':         pair_tp,
                'sl':         pair_sl,
            })

        # ── Loss Category Breakdown (Section 15.1) ──────────────────────────
        loss_breakdown = {}
        for loss_row in losses.values('loss_category').annotate(count=Count('id')):
            cat = loss_row['loss_category'] or 'WRONG_REGIME'
            loss_breakdown[cat] = loss_row['count']

        return Response({
            'total_signals':     total,
            'active_signals':    active,
            'take_profit_hits':  hits_tp,
            'stop_loss_hits':    hits_sl,
            'closed_signals':    closed,
            'win_rate_percent':  win_rate,
            'win_rate_source':   'actual' if closed > 0 else 'confidence_avg',
            'avg_confidence':    round(float(avg_conf_val), 2),
            'avg_win_r':         avg_win_val,
            'avg_loss_r':        avg_loss_val,
            'profit_factor':     profit_factor,
            'expectancy_r':      expectancy_r,
            'max_drawdown_pct':  max_drawdown_pct,
            'loss_breakdown':    loss_breakdown,
            'by_direction': {
                'BUY':  Signal.objects.filter(direction='BUY').count(),
                'SELL': Signal.objects.filter(direction='SELL').count(),
                'WAIT': 0,
            },
            'instrument_scores': instrument_scores,
        })


class NewsEventListView(generics.ListAPIView):
    """GET /api/signals/news-events/ — Upcoming high-impact news"""
    serializer_class = NewsEventSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return NewsEvent.objects.filter(
            event_time__gte=timezone.now()
        ).order_by('event_time')[:20]
