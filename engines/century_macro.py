"""
TradeSense Pro — 100-Year Macro & Changing World Order Intelligence Engine
Codifying 100 Years of Financial History, Classic Trading Literature & Geopolitical Debt Cycles.

Integrates:
1. Ray Dalio's "The Changing World Order" & "Big Debt Crises":
   - 75-100 Year Long-Term Sovereign Debt Cycles
   - Reserve Currency Empire Cycles & De-dollarization
   - Fiat Currency Debasement vs Hard Assets (Gold)
2. Richard Wyckoff & Jesse Livermore (1920s-1930s):
   - Accumulation, Spring Liquidity Sweeps, Mark-up, Distribution (UTAD)
   - Livermore's Core Trend Laws & Capital Survival Principles
3. Historical Crisis Regimes (1929 Great Crash, 1971 Nixon Shock, 1970s Stagflation, 1987 Black Monday, 2000 DotCom, 2008 GFC, 2020 COVID, 2022-2026 Multipolar Shift).
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CenturyMacroEngine:
    """
    Evaluates current real-time market positioning against 100 years of historical
    macro regimes, economic debt cycles, and classic trading literature principles.
    """

    # 100-Year Historical Macro Paradigms
    HISTORICAL_PARADIGMS = {
        'DE_DOLLARIZATION_GOLD_SUPERCYCLE': {
            'period': '2022-Present (Analogous to 1971-1979 Nixon Shock & Stagflation)',
            'description': 'Multipolar geopolitical alignment, sovereign central bank gold accumulation, global debt/GDP > 100%, weaponized currency sanctions forcing hard-asset reserves.',
            'primary_beneficiary': 'XAUUSD (Gold), Commodities (Oil, Copper), Real Assets',
            'fragility': 'Fiat currencies, long-duration unhedged government bonds',
            'gold_bias': 'SECULAR_BULLISH',
            'equity_bias': 'VOLATILE_SELECTIVE',
            'core_rule': 'Ray Dalio Law: When government debt exceeds 100% of GDP and real interest rates cannot be raised high without bankrupting the treasury, sovereign capital flees to Gold.'
        },
        'LATE_STAGE_DEBT_CYCLE': {
            'period': '1929 / 2007 / 2024 (Analogous to 1929 & 2007 pre-crisis)',
            'description': 'Yield curve un-inversion after prolonged inversion, massive government fiscal deficits, liquidity concentration in top mega-cap equities.',
            'primary_beneficiary': 'Short-term cash/T-bills, Gold',
            'fragility': 'High-yield credit, overleveraged real estate, cyclical equities',
            'gold_bias': 'BULLISH_HEDGE',
            'equity_bias': 'DISTRIBUTION_RISK',
            'core_rule': 'Wyckoff Law: Extended rallies driven by fewer mega-cap stocks represent late-stage Upthrust After Distribution (UTAD). Watch for structural change of character (CHoCH).'
        },
        'STAGFLATIONARY_SUPPLY_SHOCK': {
            'period': '1973-1981 (Analogous to 1970s Oil Embargoes)',
            'description': 'Commodity shortages, geopolitical trade chokepoint friction, sticky inflation combined with slowing industrial output.',
            'primary_beneficiary': 'Crude Oil, Gold, Raw Materials',
            'fragility': 'Tech/Growth equities, consumer discretionary',
            'gold_bias': 'STRONG_BULLISH',
            'equity_bias': 'BEARISH_REAL_TERMS',
            'core_rule': 'Paul Tudor Jones 1970s Playbook: In stagflation, paper financial assets lose in real purchasing power; trend-following commodities and gold provide generational alpha.'
        }
    }

    # Classic Trading Books Core Laws
    BOOK_PRINCIPLES = [
        {
            'author': 'Jesse Livermore (1923)',
            'book': 'Reminiscences of a Stock Operator',
            'law': 'The Tape Never Lies',
            'rule': 'Never average down a losing position. A stop-loss is not an admission of failure, but the cost of staying alive for the next asymmetric opportunity.'
        },
        {
            'author': 'Richard D. Wyckoff (1931)',
            'book': 'The Wyckoff Method of Trading',
            'law': 'Law of Cause and Effect & Liquidity Traps',
            'rule': 'Smart money intentionally engineers false breakouts below support (Springs) to absorb retail stop-losses before initiating multi-week markup rallies.'
        },
        {
            'author': 'Ray Dalio (2018 / 2021)',
            'book': 'Principles for Dealing with the Changing World Order',
            'law': 'The Big Debt Cycle & Reserve Currency Shifts',
            'rule': 'When empires print money faster than the growth of real goods and services, financial assets rise nominally but crash against Gold and scarce commodities.'
        },
        {
            'author': 'Nassim Nicholas Taleb (2007)',
            'book': 'The Black Swan & Antifragile',
            'law': 'Fat-Tailed Risk & Convexity',
            'rule': 'Standard bell-curve risk models underestimate real market shocks by 10x. Position sizing must survive a 6-sigma flash crash without margin call.'
        },
        {
            'author': 'Paul Tudor Jones (1987)',
            'book': 'Market Wizards (by Jack Schwager)',
            'law': '200-Day Macro Moving Average & Defense',
            'rule': 'Defense is ten times more important than offense. When price is below the 200 EMA, macro risk is elevated; never take full-size countertrend bets.'
        }
    ]

    @classmethod
    def analyze_100y_candle_and_volume(cls, df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """
        Codifies 100 Years of Classical Candlestick & Volume Spread Analysis (Richard Wyckoff 1931 & Jesse Livermore Tape Reading):
        - Candle Spread (Range = High - Low) & Body Anatomy (Wicks vs Real Body)
        - Relative Volume (RVOL = Vol / 20-MA Vol) & Volume Regimes (Climax, Institutional, Normal, Dry-up)
        - Wyckoff 3rd Law: Effort vs Result (High volume + narrow spread = Hidden institutional absorption/distribution)
        - VSA Signals: Stopping Volume, Buying Climax, No Supply Test, No Demand Test, Displacement
        """
        if df is None or len(df) < 15:
            return {
                'candle_pattern': 'Standard Candle',
                'volume_regime': 'NORMAL',
                'rvol': 1.0,
                'vsa_signal': 'Normal Volume Flow',
                'effort_vs_result': 'Effort matches price spread',
                'wyckoff_volume_law': 'Wyckoff 1931: Volume precedes price move.',
                'interpretation': 'Price action stable.'
            }

        c = df['close'].values.astype(float)
        o = df['open'].values.astype(float)
        h = df['high'].values.astype(float)
        l = df['low'].values.astype(float)

        # Volume extraction (falls back to range volatility if volume flat/zero)
        if 'volume' in df.columns and float(df['volume'].iloc[-10:].sum()) > 0:
            vol = df['volume'].values.astype(float)
        elif 'tick_volume' in df.columns and float(df['tick_volume'].iloc[-10:].sum()) > 0:
            vol = df['tick_volume'].values.astype(float)
        else:
            vol = (h - l)

        cur_c, cur_o, cur_h, cur_l = c[-1], o[-1], h[-1], l[-1]
        prev_c, prev_o = c[-2], o[-2]

        spread = float(cur_h - cur_l)
        body = float(abs(cur_c - cur_o))
        upper_wick = float(cur_h - max(cur_c, cur_o))
        lower_wick = float(min(cur_c, cur_o) - cur_l)
        is_bull = cur_c >= cur_o

        avg_spread = float(np.mean(h[-21:-1] - l[-21:-1])) or (spread or 1.0)
        avg_body = float(np.mean(np.abs(c[-21:-1] - o[-21:-1]))) or (body or 1.0)
        avg_vol = float(np.mean(vol[-21:-1])) or (vol[-1] or 1.0)
        rvol = float(vol[-1] / (avg_vol if avg_vol > 0 else 1.0))

        # Volume Regime
        if rvol >= 2.0:
            vol_regime = 'ULTRA_HIGH_CLIMAX'
        elif rvol >= 1.3:
            vol_regime = 'HIGH_INSTITUTIONAL'
        elif rvol <= 0.65:
            vol_regime = 'LOW_DRY_UP'
        else:
            vol_regime = 'NORMAL'

        # Candlestick Anatomy Pattern
        candle_pattern = 'Normal Candle'
        if lower_wick >= body * 1.8 and lower_wick >= upper_wick * 1.5:
            candle_pattern = 'Hammer / Bullish Pin Bar (Demand Rejection Wick)'
        elif upper_wick >= body * 1.8 and upper_wick >= lower_wick * 1.5:
            candle_pattern = 'Shooting Star / Bearish Pin Bar (Supply Rejection Wick)'
        elif is_bull and cur_c > prev_o and cur_o < prev_c and body > avg_body * 1.1:
            candle_pattern = 'Bullish Engulfing Bar (Institutional Demand Overcoming Supply)'
        elif not is_bull and cur_c < prev_o and cur_o > prev_c and body > avg_body * 1.1:
            candle_pattern = 'Bearish Engulfing Bar (Institutional Supply Overcoming Demand)'
        elif body <= avg_body * 0.25 and spread >= avg_spread * 0.7:
            candle_pattern = 'Doji / Market Indecision'
        elif body >= avg_body * 1.8:
            candle_pattern = 'Displacement Marubozu (Institutional Surge)'

        # Wyckoff 3rd Law: Effort vs Result
        effort_vs_result = 'Effort matches price spread'
        vsa_signal = 'Volume-Spread Synchronized'
        wyckoff_law = 'Richard Wyckoff (1931): Volume is the cause; price movement is the effect.'

        if rvol >= 1.5 and body <= avg_body * 0.6:
            if lower_wick > upper_wick or cur_c > (cur_l + spread * 0.5):
                effort_vs_result = 'High Effort, Low Downside: Smart Money Absorbing Supply'
                vsa_signal = 'Stopping Volume / Professional Absorption'
                wyckoff_law = 'Wyckoff Effort vs Result: High volume with narrow body at lows confirms institutional accumulation.'
            else:
                effort_vs_result = 'High Effort, Low Upside: Smart Money Distributing into Highs'
                vsa_signal = 'Buying Climax / Institutional Exhaustion'
                wyckoff_law = 'Wyckoff Effort vs Result: High volume stalling at highs indicates smart money selling into public buying.'
        elif rvol >= 1.5 and is_bull and lower_wick >= body * 0.8:
            vsa_signal = 'Stopping Volume (Institutional Dip Absorption)'
            effort_vs_result = 'Smart Money Defending Lows on Climax Volume'
        elif rvol >= 1.5 and not is_bull and upper_wick >= body * 0.8:
            vsa_signal = 'Upthrust / Selling Climax (Institutional Trap)'
            effort_vs_result = 'Smart Money Dumping into Breakout Buyers'
        elif rvol <= 0.70 and not is_bull and spread <= avg_spread * 0.7:
            vsa_signal = 'No Supply Test (Bullish Sign of Strength)'
            effort_vs_result = 'Supply dried up on pullback; path of least resistance is UP'
            wyckoff_law = 'Tom Williams (VSA): A test on low volume confirms absence of sellers, clearing path for markup.'
        elif rvol <= 0.70 and is_bull and spread <= avg_spread * 0.7:
            vsa_signal = 'No Demand Test (Bearish Sign of Weakness)'
            effort_vs_result = 'Buyers unwilling to follow higher on low volume'
            wyckoff_law = 'Tom Williams (VSA): Up-move on low volume shows smart money is not participating.'
        elif rvol >= 1.25 and body >= avg_body * 1.3:
            vsa_signal = 'Trend Momentum Bar (Volume-Confirmed Expansion)'
            effort_vs_result = 'Healthy Effort producing clear Result'

        return {
            'candle_pattern': candle_pattern,
            'spread': round(spread, 5),
            'body': round(body, 5),
            'upper_wick': round(upper_wick, 5),
            'lower_wick': round(lower_wick, 5),
            'is_bullish': bool(is_bull),
            'rvol': round(rvol, 2),
            'volume_regime': vol_regime,
            'vsa_signal': vsa_signal,
            'effort_vs_result': effort_vs_result,
            'wyckoff_volume_law': wyckoff_law,
            'interpretation': f"{candle_pattern} | {vol_regime} (RVOL {rvol:.2f}x) | {vsa_signal}"
        }

    @classmethod
    def evaluate_world_order_context(cls, symbol: str, current_price: float, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        Synthesizes 100 years of macro-geopolitical patterns with real-time indicators:
        - Real US Treasury Yield Curve slope (^TNX 10Y minus ^IRX 3M)
        - DXY Dollar Index regime
        - Gold vs Debt expansion dynamics
        - Wyckoff Phase & 100-Year Volume Spread Analysis (VSA)
        """
        from engines.intermarket import IntermarketEngine
        from engines.institutional import InstitutionalEngine

        intermarket = IntermarketEngine.get_real_intermarket_metrics(symbol, df)
        yield_slope = intermarket.get('yield_curve_slope', 0.96)
        dxy_corr = intermarket.get('dxy', -0.50)

        # 100-Year Candlestick & Volume Spread Analysis (VSA)
        vsa_data = cls.analyze_100y_candle_and_volume(df)

        # Detect active Century Macro Regime
        if 'XAU' in symbol or 'GOLD' in symbol:
            active_paradigm_key = 'DE_DOLLARIZATION_GOLD_SUPERCYCLE'
        elif yield_slope > 0.50:
            active_paradigm_key = 'LATE_STAGE_DEBT_CYCLE'
        else:
            active_paradigm_key = 'STAGFLATIONARY_SUPPLY_SHOCK'

        paradigm = cls.HISTORICAL_PARADIGMS[active_paradigm_key]

        # Wyckoff / Livermore structural analysis on current price action
        wyckoff_state = "Trend Markup / Structural Continuation"
        if df is not None and len(df) >= 30:
            c = df['close']
            h = df['high']
            l = df['low']
            recent_low = float(l.iloc[-25:-1].min())
            recent_high = float(h.iloc[-25:-1].max())
            cur_l = float(l.iloc[-1])
            cur_h = float(h.iloc[-1])
            cur_c = float(c.iloc[-1])

            if cur_l < recent_low and cur_c > recent_low:
                wyckoff_state = "Wyckoff Spring (1930s Accumulation Trap: Retail stopped out, smart money absorption)"
            elif cur_h > recent_high and cur_c < recent_high:
                wyckoff_state = "Wyckoff Upthrust (1929/2000 Distribution Trap: Exhaustion buyers trapped at highs)"

        # Apply Livermore / Dalio Wisdom
        applicable_principles = [
            cls.BOOK_PRINCIPLES[0], # Livermore
            cls.BOOK_PRINCIPLES[1], # Wyckoff
            cls.BOOK_PRINCIPLES[2], # Dalio
        ]

        # Calculate 100-Year Historical Macro Alignment Score (-100 to +100)
        macro_alignment_score = 0.0
        reasoning = []

        # 100-Year Candle & Volume Spread Reasoning
        if vsa_data.get('vsa_signal') and vsa_data['vsa_signal'] != 'Volume-Spread Synchronized':
            reasoning.append(f"Wyckoff VSA Tape: {vsa_data['vsa_signal']} — {vsa_data['effort_vs_result']}")
            if 'Absorption' in vsa_data['vsa_signal'] or 'No Supply' in vsa_data['vsa_signal'] or 'Trend Momentum' in vsa_data['vsa_signal']:
                macro_alignment_score += 15.0
            elif 'Distribution' in vsa_data['vsa_signal'] or 'Climax' in vsa_data['vsa_signal'] or 'No Demand' in vsa_data['vsa_signal']:
                macro_alignment_score -= 15.0

        if 'XAU' in symbol:
            # Gold in multipolar debt cycle: Structural secular tailwind
            macro_alignment_score += 35.0
            reasoning.append("100-Year Macro Law: Central banks expanding gold reserves at highest pace since 1971 Bretton Woods collapse")
            if dxy_corr > -0.30:
                # Gold decoupling from traditional strong dollar drag = Sovereign accumulation (1970s analog)
                macro_alignment_score += 25.0
                reasoning.append("Historical Analog: Gold rising despite firm USD / high yields — classic 1970s de-dollarization signature")
        elif 'US30' in symbol or 'SPX' in symbol:
            # Equities in late-stage debt cycle
            if yield_slope > 0.60:
                macro_alignment_score += 15.0
                reasoning.append("Historical Analog: Yield curve steepening post-inversion — watch for late-cycle momentum continuation followed by distribution")
            else:
                macro_alignment_score -= 10.0
                reasoning.append("Historical Caution: Flattening yield curve warning — late-cycle equity concentration")
        elif 'BTC' in symbol:
            macro_alignment_score += 20.0
            reasoning.append("100-Year Monetary Law: Digital non-sovereign bearer asset benefiting from global fiat supply expansion (M2 > $105 Trillion)")
        else:
            # Forex (Fiat vs Fiat)
            reasoning.append("Forex World Order: Relative central bank interest rate divergence and capital flight dynamics")

        timeline_100_years = [
            {'year': '1929', 'regime': 'The Great Crash', 'lesson': 'Livermore Short: Leverage & margin debt bubble burst. Wyckoff Distribution at peaks.'},
            {'year': '1944', 'regime': 'Bretton Woods', 'lesson': 'US Dollar crowned world reserve currency, backed by gold at $35/oz.'},
            {'year': '1971', 'regime': 'Nixon Shock (End of Gold Standard)', 'lesson': 'Fiat currency era begins. Gold jumps from $35 to $850 in stagflation decade.'},
            {'year': '1987', 'regime': 'Black Monday (-22.6% in 1 day)', 'lesson': 'Paul Tudor Jones 200-SMA rule & portfolio insurance cascade crash.'},
            {'year': '2000', 'regime': 'Dot-Com Tech Bubble', 'lesson': 'Speculative mania in unprofitable narratives ends in 80% collapse.'},
            {'year': '2008', 'regime': 'Great Financial Crisis (GFC)', 'lesson': 'Dalio Deleveraging: Subprime mortgage credit contagion and zero-rate QE birth.'},
            {'year': '2020', 'regime': 'COVID Global Lockdowns', 'lesson': 'Unprecedented fiscal stimulus: M2 money supply expanded by 40% in 2 years.'},
            {'year': '2022-2026', 'regime': 'Changing World Order & Multipolar Shift', 'lesson': 'US Debt > $35 Trillion, foreign central banks de-dollarizing & accumulating Gold at historic rates.'}
        ]

        if 'XAU' in symbol:
            comp_pehlay = "1971-1979 Nixon Shock: Dollar gold peg toota, high inflation or geopolitical oil shocks ny Gold ko 24x jump diya."
            comp_ab = "2024-2026 BRICS Multipolar Order: Foreign Central Banks (China, Russia, India) US Treasuries bech kar physical gold collect kar rahy hain."
            comp_decision = "Dalio Law: Fiat debasement cycle main Gold structural asset hai. Wyckoff Spring dips buy karo, secular trend ky agay mat khary ho."
        elif 'US30' in symbol or 'SPX' in symbol:
            comp_pehlay = "1929 & 2007 Pre-Crash: Prolonged yield curve inversion ky baad jab curve un-invert hua or market top 5 mega stocks par chali to distribution shuru hui."
            comp_ab = "2024-2026 Late Stage: US 10Y minus 3M curve un-invert ho chuki hai, tech mega-caps par high concentration hai."
            comp_decision = "Livermore & Wyckoff Rule: Trend jab tak 200-EMA ky ooper hai momentum follow karo, lekin stop loss tight rakho kyunky late-cycle liquidity sudden reverse hoti hai."
        else:
            comp_pehlay = "1970s Currency Volatility: Bretton Woods ky baad fiat vs fiat currencies wild swings main chali theen."
            comp_ab = "2024-2026 Sovereign Divergence: Federal Reserve vs ECB vs BOJ policy gap aur weaponized currency risks."
            comp_decision = "Taleb Rule: Forex pair trading main non-linear tail risk protect karo; tight risk to reward ratio lazmi rakho."

        c_bias = 'BULLISH' if macro_alignment_score >= 15.0 else ('BEARISH' if macro_alignment_score <= -15.0 else 'NEUTRAL')
        c_verdict = 'FAVOR_STRUCTURAL_EXPANSION' if macro_alignment_score >= 20 else ('CAUTION_LATE_CYCLE' if macro_alignment_score <= -10 else 'NEUTRAL_TACTICAL')
        confidence = min(96.0, max(52.0, 50.0 + abs(macro_alignment_score)))

        return {
            'active_paradigm': {
                'name': active_paradigm_key.replace('_', ' '),
                'analog': paradigm['period'],
                'description': paradigm['description'],
                'primary_beneficiary': paradigm['primary_beneficiary'],
                'fragility': paradigm['fragility'],
                'core_rule': paradigm['core_rule'],
            },
            'active_paradigm_name': active_paradigm_key.replace('_', ' '),
            'historical_period_analog': paradigm['period'],
            'world_order_description': paradigm['description'],
            'primary_beneficiary': paradigm['primary_beneficiary'],
            'dalio_law': paradigm['core_rule'],
            'debt_cycle_phase': 'Stage 5: High Debt & Wealth Gap (Ray Dalio Long-Term Debt Cycle)',
            'wyckoff_structure': {
                'phase': wyckoff_state,
                'bias': 'Accumulation/Markup' if 'Spring' in wyckoff_state else ('Distribution' if 'Upthrust' in wyckoff_state else 'Consolidation'),
                'description': 'Institutional smart money volume footprint analysis'
            },
            'wyckoff_structure_state': wyckoff_state,
            'macro_alignment_score': macro_alignment_score,
            'century_bias': c_bias,
            'century_confidence': round(confidence, 1),
            'century_verdict': c_verdict,
            'trading_verdict': c_verdict,
            'historical_reasoning': reasoning,
            'book_principles': applicable_principles,
            'candle_and_volume_vsa': vsa_data,
            'timeline_100_years': timeline_100_years,
            'historical_comparison': {
                'pehlay_then': comp_pehlay,
                'ab_now': comp_ab,
                'decision_rule': comp_decision,
            }
        }

