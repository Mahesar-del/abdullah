"""
Unified Signal Engine — The Brain of TradeSense Pro
Phase 8 & 9 Upgrades:
- Dynamic Asset-Class Specific Weights (Forex, Crypto, Metals, Indices, Commodities).
- Multi-Engine Confluence: Technical, SMC/ICT, Price Action, Macro, News, Institutional, Intermarket, AI/ML.
- Deterministic Risk Management integration with RiskDecision persistence.
- Data Quality gating & Blackout circuit breakers.
"""
import pandas as pd
import numpy as np
import inspect
import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from .base import EngineResult
from .technical    import TechnicalEngine
from .smc_ict      import SMCEngine
from .price_action import PriceActionEngine
from .macro        import MacroEngine
from .news         import NewsEngine
from .institutional import InstitutionalEngine
from .intermarket  import IntermarketEngine
from .risk         import RiskEngine, RiskEvaluation
from .ai_ml        import AIEngine
from .godzilla     import GodzillaEngine, godzilla_lot_size
from .master_traders import MasterTradersEngine


@dataclass
class UnifiedSignal:
    """Final signal output from the Unified Engine"""
    symbol:           str
    timeframe:        str
    direction:        str          # BUY / SELL / WAIT
    strength:         str          # STRONG / MODERATE / WEAK
    confidence:       float        # 0-100
    entry:            float
    stop_loss:        float
    take_profit_1:    float
    take_profit_2:    Optional[float]
    take_profit_3:    Optional[float]
    risk_reward:      float
    analysis:         str          # Summary text
    warnings:         List[str]
    engine_results:   Dict         # Individual engine scores
    technical_score:     float = 0.0
    smc_score:           float = 0.0
    price_action_score:  float = 0.0
    macro_score:         float = 0.0
    news_score:          float = 0.0
    institutional_score: float = 0.0
    intermarket_score:   float = 0.0
    ai_ml_score:         float = 0.0
    godzilla_score:      float = 0.0   # Godzilla Order Imbalance + Volatility engine
    master_traders_score:float = 0.0   # Paul Tudor Jones, Wyckoff, Soros, Livermore, Simons, Sarao
    godzilla_sigma:      float = 0.0   # σ_t (ARCH volatility)
    godzilla_max_lev:    float = 10.0  # Max leverage from Godzilla formula
    godzilla_phi:        float = 0.0   # Relative spread (friction)
    data_quality_score:  float = 100.0
    recommended_lots:    float = 0.10
    is_trade_allowed:    bool  = True
    risk_rejection_reasons: List[str] = field(default_factory=list)
    decision_class:      str   = 'STRONG'   # STRONG / MODERATE / WEAK / CONFLICT / BLACKOUT / DATA_ERROR
    market_regime:       str   = 'TRENDING' # TRENDING / RANGING / VOLATILE / COMPRESSION
    independent_groups:  Dict[str, str] = field(default_factory=dict)
    independent_agreement_count: int = 0

    def to_dict(self) -> dict:
        return {
            'symbol':                 self.symbol,
            'timeframe':              self.timeframe,
            'direction':              self.direction,
            'strength':               self.strength,
            'confidence':             round(self.confidence, 2),
            'entry':                  self.entry,
            'stop_loss':              self.stop_loss,
            'take_profit_1':          self.take_profit_1,
            'take_profit_2':          self.take_profit_2,
            'take_profit_3':          self.take_profit_3,
            'risk_reward':            self.risk_reward,
            'analysis':               self.analysis,
            'warnings':               self.warnings,
            'data_quality_score':     round(self.data_quality_score, 2),
            'recommended_lots':       self.recommended_lots,
            'is_trade_allowed':       self.is_trade_allowed,
            'risk_rejection_reasons': self.risk_rejection_reasons,
            'decision_class':         self.decision_class,
            'market_regime':          self.market_regime,
            'independent_groups':     self.independent_groups,
            'independent_agreement_count': self.independent_agreement_count,
            'engine_scores': {
                'technical':      self.technical_score,
                'smc_ict':        self.smc_score,
                'price_action':   self.price_action_score,
                'macro':          self.macro_score,
                'news':           self.news_score,
                'institutional':  self.institutional_score,
                'intermarket':    self.intermarket_score,
                'ai_ml':          self.ai_ml_score,
                'godzilla':       self.godzilla_score,
                'master_traders': self.master_traders_score,
            },
            'godzilla_meta': {
                'sigma_t':   round(self.godzilla_sigma, 6),
                'max_lev':   round(self.godzilla_max_lev, 2),
                'phi_t':     round(self.godzilla_phi, 6),
            }
        }


class UnifiedSignalEngine:
    """
    Orchestrates all sub-engines and produces a final BUY/SELL/WAIT signal.
    Enforces dynamic asset weighting and deterministic risk criteria.
    """

    # Dynamic weights by asset class rebalanced with Master Institutional Traders:
    # 1. SMC / ICT: 35% (Core liquidity sweeps, Fair Value Gaps, and 70.5% OTE sweet spot)
    # 2. Master Traders: 25% (Paul Tudor Jones 200-EMA, Wyckoff Springs/UTAD, Livermore Pivots, Soros Fed Liquidity)
    # 3. Macro: 20% (100-Year Debt Cycles, Central Bank Policy, Inflation)
    # 4. Godzilla: 10% (Microstructure order flow imbalance + ARCH volatility leverage cap)
    # 5. Technical: 10% (Regime segmentation & momentum confirmation)
    # 6. Price Action: 0% (Naive breakout chasing eliminated to prevent false breakout losses)
    PROVEN_CORE_WEIGHTS = {
        'smc_ict':        0.35,  # Core structural engine (ICT 2022 Mentorship & OTE 70.5%)
        'master_traders': 0.25,  # PTJ 200-EMA, Wyckoff Spring/UTAD, Livermore Pivots, Soros Net Liquidity
        'macro':          0.20,  # 100-Year World Order & Dalio Debt Cycle (+37.5% win correlation)
        'godzilla':       0.10,  # Order imbalance & ARCH volatility cap
        'technical':      0.10,  # Multi-indicator regime & momentum
        'price_action':   0.00,  # Zero-weighted; naive breakout chasing removed; replaced by Wyckoff/Livermore
        'news':           0.00,  # Zero-weighted in direction; acts as protective blackout filter
        'institutional':  0.00,  # Zero-weighted on intraday to eliminate weekly lagging COT bias
        'intermarket':    0.00,
        'ai_ml':          0.00,
    }

    # Dedicated Crypto weights: Anchored by ICT liquidity sweeps & Master institutional order flow
    CRYPTO_WEIGHTS = {
        'smc_ict':        0.40,  # 40% ICT liquidity sweeps & FVG fills
        'master_traders': 0.25,  # 25% Sarao Order Book depth + Wyckoff + Simons autocorrelation
        'macro':          0.15,  # 15% Monetary inflation & fiat expansion
        'godzilla':       0.10,  # 10% Microstructure order flow & ARCH sizing
        'technical':      0.10,  # 10% Volatility & trend confirmation
        'price_action':   0.00,  # Zero-weighted (eliminates BTCUSD fake breakout losses)
        'news':           0.00,
        'institutional':  0.00,
        'intermarket':    0.00,
        'ai_ml':          0.00,
    }

    ASSET_WEIGHTS = {
        'FOREX':       PROVEN_CORE_WEIGHTS,
        'CRYPTO':      CRYPTO_WEIGHTS,
        'METALS':      PROVEN_CORE_WEIGHTS,
        'INDICES':     PROVEN_CORE_WEIGHTS,
        'COMMODITIES': PROVEN_CORE_WEIGHTS,
    }

    # Thresholds
    STRONG_THRESHOLD   = 70.0
    MODERATE_THRESHOLD = 50.0
    WAIT_THRESHOLD     = 35.0   # below this = WAIT

    # Risk Management Per Version 2.0 Specification (Section 7 & 23)
    MAX_RISK_REWARD    = 5.0
    MIN_RISK_REWARD    = 2.0
    ATR_SL_MULTIPLIER  = 1.5   # 1.5x ATR structural invalidation distance
    ATR_TP1_MULTIPLIER = 3.0   # 3.0 / 1.5 = 2.0R minimum under the execution mandate
    ATR_TP2_MULTIPLIER = 3.75  # 3.75 / 1.5 = 2.50R (Target 2 per Section 7)
    ATR_TP3_MULTIPLIER = 5.25  # 5.25 / 1.5 = 3.50R (Target 3 per Section 7)

    def __init__(self, df: pd.DataFrame, symbol: str, timeframe: str = 'H1', execution_quote=None):
        self.df        = df
        self.symbol    = symbol
        self.timeframe = timeframe
        self.execution_quote = execution_quote
        self.warnings  = []
        self.asset_class = self._get_asset_class()
        self.weights   = self.ASSET_WEIGHTS.get(self.asset_class, self.ASSET_WEIGHTS['FOREX'])

    def _get_asset_class(self) -> str:
        sym = self.symbol.upper()
        if any(c in sym for c in ['BTC', 'ETH', 'SOL', 'XRP', 'BNB']):
            return 'CRYPTO'
        elif any(m in sym for m in ['XAU', 'XAG', 'GOLD', 'SILVER']):
            return 'METALS'
        elif any(i in sym for i in ['SPX', 'NAS', 'US30', 'GER40', 'UK100', 'DAX']):
            return 'INDICES'
        elif any(o in sym for o in ['OIL', 'USOIL', 'UKOIL', 'COPPER', 'NATGAS']):
            return 'COMMODITIES'
        return 'FOREX'

    def generate(self) -> UnifiedSignal:
        """Main pipeline — runs all engines, calculates weighted scores, validates risk"""

        # ── Phase 1: Data Quality & Reliability Validation ───
        from .data_quality import DataQualityValidator
        is_crypto = self.asset_class == 'CRYPTO'
        quality_report = DataQualityValidator.validate_ohlcv(
            self.df, self.symbol, timeframe=self.timeframe, is_crypto=is_crypto
        )
        if quality_report.cleaned_df is not None:
            self.df = quality_report.cleaned_df

        self.warnings.extend(quality_report.warnings)
        if quality_report.errors:
            self.warnings.extend([f"DATA ERROR: {e}" for e in quality_report.errors])

        # Invalid input must not reach sub-engines (some train/persist models)
        # or price-level arithmetic. Return a coherent, non-executable result.
        if quality_report.force_wait or quality_report.quality_score < 70.0:
            price = 0.0
            if self.df is not None and not self.df.empty and 'close' in self.df:
                candidate = float(self.df['close'].iloc[-1])
                if math.isfinite(candidate):
                    price = candidate
            return UnifiedSignal(
                symbol=self.symbol, timeframe=self.timeframe, direction='WAIT',
                strength='WEAK', confidence=0.0, entry=price, stop_loss=price,
                take_profit_1=price, take_profit_2=None, take_profit_3=None,
                risk_reward=0.0, analysis='Market data failed validation.',
                warnings=self.warnings, engine_results={},
                data_quality_score=quality_report.quality_score,
                recommended_lots=0.0, is_trade_allowed=False,
                risk_rejection_reasons=quality_report.errors or ['Market data quality below threshold'],
                decision_class='DATA_ERROR',
            )

        # ── Run Active Engines ────────────────────────────
        engine_results = {}

        # 1. Technical Engine
        tech_result = self._run_engine(TechnicalEngine, 'technical')
        if tech_result: engine_results['technical'] = tech_result

        # 2. SMC/ICT Engine
        smc_result = self._run_engine(SMCEngine, 'smc_ict')
        if smc_result: engine_results['smc_ict'] = smc_result

        # 3. Price Action Engine
        pa_result = self._run_engine(PriceActionEngine, 'price_action')
        if pa_result: engine_results['price_action'] = pa_result

        # 4. Macro Engine
        macro_result = self._run_engine(MacroEngine, 'macro')
        if macro_result: engine_results['macro'] = macro_result

        # 5. News Engine
        news_result = self._run_engine(NewsEngine, 'news')
        if news_result: engine_results['news'] = news_result

        # 6. Institutional Engine
        inst_result = self._run_engine(InstitutionalEngine, 'institutional')
        if inst_result: engine_results['institutional'] = inst_result

        # 7. Intermarket Engine (Phase 8)
        inter_result = self._run_engine(IntermarketEngine, 'intermarket')
        if inter_result: engine_results['intermarket'] = inter_result

        # 8. AI/ML Engine
        ai_result = self._run_engine(AIEngine, 'ai_ml')
        if ai_result: engine_results['ai_ml'] = ai_result

        # 9. Godzilla Engine (Order Imbalance + ARCH Volatility + Leverage Cap)
        godzilla_result = self._run_engine(GodzillaEngine, 'godzilla')
        if godzilla_result: engine_results['godzilla'] = godzilla_result

        # 10. Master Traders Institutional Engine (PTJ, Wyckoff, Soros/Druckenmiller, Livermore, Simons, Sarao, Burry)
        master_result = self._run_engine(MasterTradersEngine, 'master_traders')
        if master_result: engine_results['master_traders'] = master_result

        missing_required = [
            name for name, weight in self.weights.items()
            if weight > 0 and name not in engine_results
        ]
        if news_result is None:
            missing_required.append('news')

        # ── Calculate Weighted Score using Dynamic Asset Weights ──
        weighted_buy  = 0.0
        weighted_sell = 0.0

        for name, result in engine_results.items():
            w = self.weights.get(name, 0.0)
            if result.direction == 'BUY':
                weighted_buy  += result.score * w
            elif result.direction == 'SELL':
                weighted_sell += result.score * w

        # Normalize to 0-100
        max_possible  = sum(self.weights.values()) * 100.0
        norm_buy      = (weighted_buy  / max_possible) * 100.0
        norm_sell     = (weighted_sell / max_possible) * 100.0

        # Net score: positive = BUY, negative = SELL
        net_score     = norm_buy - norm_sell
        abs_score     = abs(net_score)

        # ── Version 2.0 Section 5: Independent Evidence Groups ──
        # Anchor directional evidence across independent institutional pillars:
        independent_groups = {
            'Structure':       smc_result.direction if smc_result else 'NEUTRAL',
            'Master Traders':  master_result.direction if master_result else 'NEUTRAL',
            'Macro':           macro_result.direction if macro_result else 'NEUTRAL',
            'Regime/Momentum': tech_result.direction if tech_result else 'NEUTRAL',
            'OrderFlow':       godzilla_result.direction if godzilla_result else 'NEUTRAL',
            'Price Action':    pa_result.direction if pa_result else 'NEUTRAL',
            'Flow':            inst_result.direction if inst_result else 'NEUTRAL',
            'News':            news_result.direction if news_result else 'NEUTRAL',
            'Intermarket':     inter_result.direction if inter_result else 'NEUTRAL',
            'ML':              ai_result.direction if ai_result else 'NEUTRAL',
        }

        # Active voting groups anchored by institutional masters & structure
        voting_groups = ('Structure', 'Master Traders', 'Macro', 'Regime/Momentum', 'OrderFlow')

        # Market Regime Detection
        market_regime = 'TRENDING'
        if tech_result and any('RANGING' in r for r in tech_result.reasoning):
            market_regime = 'RANGING'
        elif (inter_result and any('SQUEEZE' in r for r in inter_result.reasoning)) or (tech_result and any('SQUEEZE' in r for r in tech_result.reasoning)):
            market_regime = 'COMPRESSION'
        elif tech_result and any('HIGH_VOLATILITY' in r for r in tech_result.reasoning):
            market_regime = 'VOLATILE'
        elif tech_result and any('TREND' in r for r in tech_result.reasoning):
            market_regime = 'TRENDING'

        # Independent Group Support Counts
        buy_groups  = [g for g in voting_groups if independent_groups[g] == 'BUY']
        sell_groups = [g for g in voting_groups if independent_groups[g] == 'SELL']

        is_blackout = any('BLACKOUT' in w for w in self.warnings)
        if macro_result and any('BLACKOUT' in r for r in macro_result.reasoning):
            is_blackout = True
        if news_result and any('BLACKOUT' in str(r).upper() for r in news_result.reasoning):
            is_blackout = True

        direction = 'WAIT'
        decision_class = 'WAIT'

        # Gate 1: Data Quality Gate (Section 5.1 & 8.1)
        if missing_required:
            direction = 'WAIT'
            decision_class = 'DATA_ERROR'
            self.warnings.append(f"GATE REJECTION: Required engine evidence unavailable: {', '.join(missing_required)}.")

        # Gate 2: High-Impact News Blackout Gate (Section 5.1 & 9)
        elif is_blackout:
            direction = 'WAIT'
            decision_class = 'BLACKOUT'
            self.warnings.append("GATE REJECTION: High-Impact Economic News Blackout active.")

        # Gate 3: Independent Confluence Gating (Section 5.1 & 6.1)
        else:
            cand_direction = None
            if len(buy_groups) >= 3 and len(buy_groups) > len(sell_groups):
                cand_direction = 'BUY'
            elif len(sell_groups) >= 3 and len(sell_groups) > len(buy_groups):
                cand_direction = 'SELL'

            if cand_direction is None:
                direction = 'WAIT'
                decision_class = 'WEAK'
                self.warnings.append("CONFLUENCE FILTER: Less than 3 independent evidence groups agree.")
            elif (cand_direction == 'BUY' and net_score <= 0) or (cand_direction == 'SELL' and net_score >= 0):
                direction = 'WAIT'
                decision_class = 'CONFLICT'
                self.warnings.append("CONFLUENCE FILTER: Voting direction conflicts with weighted directional evidence.")
            else:
                # Rule: "At least one of Structure or Master Traders must normally support the trade."
                struct_supports = (independent_groups['Structure'] == cand_direction)
                master_supports = (independent_groups['Master Traders'] == cand_direction)

                if not (struct_supports or master_supports):
                    direction = 'WAIT'
                    decision_class = 'WEAK'
                    self.warnings.append("STRUCTURAL FILTER: Neither Structure nor Institutional Master Traders supports the trade.")
                else:
                    # Rule: "A conflicting high-impact macro/news condition can veto the trade."
                    opp_dir = 'SELL' if cand_direction == 'BUY' else 'BUY'
                    macro_opp = (independent_groups['Macro'] == opp_dir and macro_result and macro_result.score >= 50.0)
                    news_opp  = (independent_groups['News'] == opp_dir and news_result and news_result.score >= 50.0)

                    if macro_opp or news_opp:
                        direction = 'WAIT'
                        decision_class = 'CONFLICT'
                        self.warnings.append("VETO: High-impact Macro/News condition strongly opposes directional trade.")
                    else:
                        # ── Gate 4: Paul Tudor Jones 200-EMA Institutional Capital Defense Rule ──
                        # "Never be long below the 200 EMA; never be short above the 200 EMA."
                        cur_p = float(self.df['close'].iloc[-1])
                        n_bars = len(self.df)
                        ema200 = float(pd.Series(self.df['close']).ewm(span=min(200, n_bars), adjust=False).mean().iloc[-1])

                        if cand_direction == 'BUY' and cur_p < ema200:
                            direction = 'WAIT'
                            decision_class = 'TREND_FILTERED'
                            self.warnings.append(f"PTJ 200-EMA VETO: Cannot BUY while price ({cur_p:,.2f}) is below 200 EMA ({ema200:,.2f}) — Institutional Defense Active.")
                        elif cand_direction == 'SELL' and cur_p > ema200:
                            direction = 'WAIT'
                            decision_class = 'TREND_FILTERED'
                            self.warnings.append(f"PTJ 200-EMA VETO: Cannot SELL while price ({cur_p:,.2f}) is above 200 EMA ({ema200:,.2f}) — Institutional Defense Active.")
                        # ── Gate 5: Michael Burry & Wyckoff Overextension / Tail-Risk Defense ──
                        elif cand_direction == 'BUY' and master_result and any('Burry Tail-Risk' in w for w in getattr(master_result, 'reasoning', [])):
                            direction = 'WAIT'
                            decision_class = 'TAIL_RISK_REJECTED'
                            self.warnings.append("BURRY TAIL-RISK VETO: Asset overextended >18% from 200 EMA on drying volume — Distribution top trap detected.")
                        else:
                            direction = cand_direction

        # ── Confidence Calculation ────────────────────────
        if direction in ('BUY', 'SELL'):
            agreeing_groups = len(buy_groups) if direction == 'BUY' else len(sell_groups)
            active_groups = len([g for g in voting_groups if independent_groups[g] != 'NEUTRAL'])
            group_confluence = (agreeing_groups / max(active_groups, 1)) * 100.0
            confidence = (abs_score * 0.60) + (group_confluence * 0.40)
        else:
            agreeing_groups = 0
            confidence = abs_score * 0.50

        # Scale confidence based on data quality score
        if quality_report.quality_score < 100.0:
            confidence = confidence * (quality_report.quality_score / 100.0)

        confidence = min(confidence, 98.0)  # never 100% per Section 6

        # Determine decision class if trade is active
        if direction in ('BUY', 'SELL'):
            if confidence >= self.STRONG_THRESHOLD and agreeing_groups >= 4:
                decision_class = 'STRONG'
                strength = 'STRONG'
            elif confidence >= self.MODERATE_THRESHOLD:
                decision_class = 'MODERATE'
                strength = 'MODERATE'
            else:
                decision_class = 'WEAK'
                strength = 'WEAK'
                direction = 'WAIT'
        else:
            strength = 'WEAK'

        # ── Price Levels ──────────────────────────────────
        cur_close = float(self.df['close'].iloc[-1])
        if self.execution_quote and direction in ('BUY', 'SELL'):
            quote_price = self.execution_quote.get('ask' if direction == 'BUY' else 'bid')
            if quote_price is not None and math.isfinite(float(quote_price)) and float(quote_price) > 0:
                cur_close = float(quote_price)
        atr       = self._get_atr()

        entry, sl, tp1, tp2, tp3, rr = self._calculate_levels(
            direction, cur_close, atr, engine_results
        )

        # A known structural liquidity target with inadequate reward is a veto;
        # do not replace it with an invented farther target to make the ratio pass.
        level_rejections = []
        if direction in ('BUY', 'SELL') and (not math.isfinite(rr) or rr < self.MIN_RISK_REWARD):
            level_rejections.append(f"Structural reward:risk {rr:.2f} is below required {self.MIN_RISK_REWARD:.2f}R")

        # ── Deterministic Risk Management Gating ──────────
        # Extract Godzilla volatility metadata for leverage-aware sizing
        godzilla_sigma   = 0.0
        godzilla_max_lev = 10.0
        godzilla_phi     = 0.0
        if godzilla_result and godzilla_result.entry_zone is not None:
            godzilla_sigma   = float(godzilla_result.entry_zone or 0.0)   # σ_t
            godzilla_phi     = float(godzilla_result.sl_zone or 0.0)      # φ_t
            godzilla_max_lev = float(godzilla_result.tp_zone or 10.0)     # Max_Lev

        risk_eval = RiskEngine.evaluate(
            symbol=self.symbol,
            direction=direction,
            entry=entry,
            stop_loss=sl,
            take_profit=tp1,
            confidence=confidence,
            account_balance=10000.0,
            risk_percentage=1.0,
            is_in_blackout=is_blackout,
            godzilla_sigma=godzilla_sigma,
            godzilla_max_lev=godzilla_max_lev,
        )

        if (not risk_eval.is_allowed or level_rejections) and direction != 'WAIT':
            for reason in risk_eval.rejection_reasons + level_rejections:
                self.warnings.append(f"RISK FILTER: {reason}")
            # A rejected risk decision must not remain a directional, executable signal.
            direction = 'WAIT'
            decision_class = 'RISK_REJECTED'

        # ── Analysis Summary ──────────────────────────────
        analysis = self._build_analysis(direction, confidence, engine_results)

        # ── Warnings ─────────────────────────────────────
        warnings = self._check_warnings(direction, engine_results, atr)

        return UnifiedSignal(
            symbol                 = self.symbol,
            timeframe              = self.timeframe,
            direction              = direction,
            strength               = strength,
            confidence             = round(confidence, 2),
            entry                  = round(entry, 5),
            stop_loss              = round(sl, 5),
            take_profit_1          = round(tp1, 5),
            take_profit_2          = round(tp2, 5) if tp2 else None,
            take_profit_3          = round(tp3, 5) if tp3 else None,
            risk_reward            = round(rr, 2),
            analysis               = analysis,
            warnings               = warnings + self.warnings,
            engine_results         = {k: v.to_dict() for k, v in engine_results.items()},
            technical_score        = round(engine_results.get('technical', self._stub_result('x')).score, 2),
            smc_score              = round(engine_results.get('smc_ict', self._stub_result('x')).score, 2),
            price_action_score     = round(engine_results.get('price_action', self._stub_result('x')).score, 2),
            macro_score            = round(engine_results.get('macro', self._stub_result('x')).score, 2),
            news_score             = round(engine_results.get('news', self._stub_result('x')).score, 2),
            institutional_score    = round(engine_results.get('institutional', self._stub_result('x')).score, 2),
            intermarket_score      = round(engine_results.get('intermarket', self._stub_result('x')).score, 2),
            ai_ml_score            = round(engine_results.get('ai_ml', self._stub_result('x')).score, 2),
            godzilla_score         = round(engine_results.get('godzilla', self._stub_result('x')).score, 2),
            master_traders_score   = round(engine_results.get('master_traders', self._stub_result('x')).score, 2),
            godzilla_sigma         = godzilla_sigma,
            godzilla_max_lev       = godzilla_max_lev,
            godzilla_phi           = godzilla_phi,
            data_quality_score     = round(quality_report.quality_score, 2),
            recommended_lots       = risk_eval.recommended_lots if direction in ('BUY', 'SELL') else 0.0,
            is_trade_allowed       = risk_eval.is_allowed and direction in ('BUY', 'SELL'),
            risk_rejection_reasons = risk_eval.rejection_reasons + level_rejections,
            decision_class         = decision_class,
            market_regime          = market_regime,
            independent_groups     = independent_groups,
            independent_agreement_count = agreeing_groups
        )

    generate_signal = generate

    # ── Helper Methods ────────────────────────────────────

    def _run_engine(self, engine_class, name: str) -> Optional[EngineResult]:
        try:
            # Some context-only engines explicitly accept only df/symbol; every
            # timeframe-aware engine must receive the requested timeframe.
            parameters = inspect.signature(engine_class).parameters
            kwargs = {'timeframe': self.timeframe} if 'timeframe' in parameters else {}
            result = engine_class(self.df, self.symbol, **kwargs).analyze()
            if result is None or result.direction not in ('BUY', 'SELL', 'NEUTRAL'):
                raise ValueError('Invalid engine direction/result')
            if not math.isfinite(float(result.score)) or not 0.0 <= float(result.score) <= 100.0:
                raise ValueError('Engine score must be finite and between 0 and 100')
            return result
        except Exception as e:
            self.warnings.append(f"{name} engine error: {str(e)[:80]}")
            return None

    def _stub_result(self, name: str) -> EngineResult:
        return EngineResult(
            engine_name = name,
            score       = 0.0,
            direction   = 'NEUTRAL',
            confidence  = 0.0,
            reasoning   = [f'{name} engine idle'],
            weight      = self.weights.get(name, 0.0),
        )

    def _determine_direction(self, net_score: float, results: dict) -> str:
        # Backward compatibility wrapper
        active = {k: v for k, v in results.items() if v.direction in ('BUY', 'SELL')}
        buy_engines  = [k for k, v in active.items() if v.direction == 'BUY']
        sell_engines = [k for k, v in active.items() if v.direction == 'SELL']

        if len(buy_engines) >= 3 and len(buy_engines) > len(sell_engines):
            if abs(net_score) >= self.WAIT_THRESHOLD:
                return 'BUY'
        if len(sell_engines) >= 3 and len(sell_engines) > len(buy_engines):
            if abs(net_score) >= self.WAIT_THRESHOLD:
                return 'SELL'

        return 'WAIT'

    def _get_atr(self) -> float:
        h = self.df['high']
        l = self.df['low']
        c = self.df['close']
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        return float(tr.ewm(span=14, adjust=False).mean().iloc[-1])

    def _calculate_levels(self, direction, entry, atr, results):
        sl_dist  = atr * self.ATR_SL_MULTIPLIER
        tp1_dist = atr * self.ATR_TP1_MULTIPLIER

        if direction == 'BUY':
            sl  = entry - sl_dist
            tp1 = entry + tp1_dist
        elif direction == 'SELL':
            sl  = entry + sl_dist
            tp1 = entry - tp1_dist
        else:
            sl  = entry - sl_dist
            tp1 = entry + tp1_dist

        # Anchor TP1 directly to Draw on Liquidity (DOL) and SL beyond swept liquidity
        smc_res = results.get('smc_ict')
        if smc_res and smc_res.direction == direction:
            if direction == 'BUY' and smc_res.tp_zone and smc_res.tp_zone > entry and smc_res.sl_zone and smc_res.sl_zone < entry:
                cand_rr = (smc_res.tp_zone - entry) / (entry - smc_res.sl_zone)
                if math.isfinite(cand_rr) and cand_rr > 0:
                    tp1 = smc_res.tp_zone
                    sl = smc_res.sl_zone
            elif direction == 'SELL' and smc_res.tp_zone and smc_res.tp_zone < entry and smc_res.sl_zone and smc_res.sl_zone > entry:
                cand_rr = (entry - smc_res.tp_zone) / (smc_res.sl_zone - entry)
                if math.isfinite(cand_rr) and cand_rr > 0:
                    tp1 = smc_res.tp_zone
                    sl = smc_res.sl_zone

        # Single full-position Take Profit at TP1 (100% auto-close on TP1 hit, no TP2/TP3 wait)
        tp2 = None
        tp3 = None

        rr = abs(tp1 - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0
        if rr > self.MAX_RISK_REWARD:
            # Keep displayed RR consistent with the actual submitted levels.
            distance = abs(sl - entry) * self.MAX_RISK_REWARD
            tp1 = entry - distance if direction == 'SELL' else entry + distance
            rr = self.MAX_RISK_REWARD

        return entry, sl, tp1, tp2, tp3, rr

    def _build_analysis(self, direction, confidence, results) -> str:
        lines = [
            f"Direction: {direction} | Confidence: {confidence:.1f}% | Timeframe: {self.timeframe} | Asset: {self.asset_class}",
            "",
            "Engine Breakdown:"
        ]
        for name, result in results.items():
            if result.direction != 'NEUTRAL' or result.score > 0:
                reason = result.reasoning[0] if result.reasoning else 'N/A'
                lines.append(f"  [{result.direction:7s}] {name:15s} Score={result.score:.0f} | {reason}")

        return "\n".join(lines)

    def _check_warnings(self, direction, results, atr) -> list:
        warnings = []
        buy_count  = sum(1 for r in results.values() if r.direction == 'BUY')
        sell_count = sum(1 for r in results.values() if r.direction == 'SELL')

        if buy_count > 0 and sell_count > 0 and abs(buy_count - sell_count) <= 1:
            warnings.append("Conflicting signals between engines — reduced confidence")

        df = self.df
        avg_range = float((df['high'] - df['low']).tail(20).mean())
        if atr < avg_range * 0.5:
            warnings.append("Low volatility (ATR below average) — spread costs may be significant")

        return warnings
