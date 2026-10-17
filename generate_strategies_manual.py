"""
TradeSense Pro — Deep-Dive Trading Strategies Manual PDF Generator
Generates a comprehensive, professional, multi-page PDF detailing every trading strategy implemented in TradeSense Pro.
"""
import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """Adds Page X of Y and running header/footer to every page"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Running header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 755, "TradeSense Pro — Comprehensive Trading Strategies & Algorithmic Blueprint")
            self.drawRightString(558, 755, "Confidential & Proprietary Execution Manual")
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.6)
            self.line(54, 747, 558, 747)

        # Footer on all pages
        self.setFont("Helvetica", 8)
        self.drawString(54, 36, "TradeSense Pro © 2026 | Multi-Engine Confluence & Quantitative Architecture")
        text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 36, text)
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.6)
        self.line(54, 48, 558, 48)

        self.restoreState()


def create_strategies_pdf(output_filename="TradeSense_Pro_Trading_Strategies_Deep_Dive.pdf"):
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Premium Color Palette
    PRIMARY = colors.HexColor("#0f172a")       # Slate Navy
    ACCENT = colors.HexColor("#2563eb")        # Royal Blue
    SECONDARY = colors.HexColor("#0284c7")     # Sky Blue
    DARK_TEXT = colors.HexColor("#1e293b")     # Dark Slate
    MUTED_TEXT = colors.HexColor("#475569")    # Charcoal Grey
    CARD_BG = colors.HexColor("#f8fafc")       # Soft Card Grey
    BORDER_COL = colors.HexColor("#e2e8f0")    # Clean Border Grey
    HIGHLIGHT_BG = colors.HexColor("#eff6ff")  # Soft Blue Box
    EMERALD = colors.HexColor("#059669")       # Profit Green
    ROSE = colors.HexColor("#e11d48")          # Risk Red
    AMBER = colors.HexColor("#d97706")         # Warning Amber

    # Custom Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=PRIMARY,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=ACCENT,
        spaceAfter=12
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=PRIMARY,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=ACCENT,
        spaceBefore=9,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=DARK_TEXT,
        spaceAfter=5
    )

    body_bold = ParagraphStyle(
        'BodyDarkBold',
        parent=body_style,
        fontName='Helvetica-Bold'
    )

    bullet_style = ParagraphStyle(
        'BulletDark',
        parent=body_style,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3
    )

    code_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.8,
        leading=10.5,
        textColor=colors.HexColor("#0f172a")
    )

    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=colors.white,
        alignment=1  # Centered
    )

    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.8,
        leading=10.5,
        textColor=DARK_TEXT
    )

    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=table_cell,
        fontName='Helvetica-Bold'
    )

    callout_text = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8.2,
        leading=11.5,
        textColor=colors.HexColor("#1e3a8a")
    )

    story = []

    # ── HEADER BANNER ──────────────────────────────────────────────
    story.append(Paragraph("TradeSense Pro — Algorithmic Trading Intelligence", title_style))
    story.append(Paragraph("Complete Technical & Architectural Manual of Active Trading Strategies", subtitle_style))
    story.append(Paragraph(
        "<b>Document Classification:</b> Production Engine Blueprint & Quantitative Strategy Manual<br/>"
        "<b>Author:</b> TradeSense Pro Quantitative Engineering Team | <b>System Release:</b> 2026 Enterprise<br/>"
        "<b>Core Architecture:</b> Multi-Engine Confluence, Dynamic Asset Weighting & Deterministic Risk Execution",
        ParagraphStyle('MetaHeader', parent=body_style, fontSize=7.8, leading=11, textColor=MUTED_TEXT)
    ))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=ACCENT, spaceBefore=2, spaceAfter=10))

    # ── EXECUTIVE SUMMARY & PHILOSOPHY ────────────────────────────
    story.append(Paragraph("1. Executive Overview & Trading Philosophy", h1_style))
    story.append(Paragraph(
        "TradeSense Pro does not rely on a single isolated indicator or simplistic retail pattern. "
        "Retail traders frequently lose capital because single indicators (such as basic RSI oversold or moving average crossovers) "
        "suffer massive drawdowns during volatile regime shifts, news releases, or institutional stop runs. "
        "To achieve institutional-grade performance, TradeSense Pro operates a <b>Multi-Engine Confluence Framework</b>. "
        "Every single trade recommendation is the result of <b>10 distinct strategy engines</b> analyzing market data concurrently, "
        "synthesized through asset-specific weightings, validated by a deterministic risk gatekeeper, and protected by macroeconomic blackout circuit breakers.",
        body_style
    ))

    # Architecture Overview Table
    summary_data = [
        [Paragraph("Engine Name", table_header),
         Paragraph("Weight (FX)", table_header),
         Paragraph("Core Mathematical / Analytical Methodology", table_header),
         Paragraph("Primary Objective", table_header)],
        
        [Paragraph("<b>1. SMC / ICT</b>", table_cell),
         Paragraph("<b>20%</b>", table_cell_bold),
         Paragraph("Market Structure Shift (MSS), Order Blocks (OB), Fair Value Gaps (FVG), Liquidity Sweeps, Kill Zones", table_cell),
         Paragraph("Identifies institutional liquidity pools and high-probability entry zones", table_cell)],

        [Paragraph("<b>2. Price Action</b>", table_cell),
         Paragraph("<b>15%</b>", table_cell_bold),
         Paragraph("Dynamic S/R pivots, Candlestick anatomy, Breakout & Retest, False Breakouts (Wyckoff Spring/Upthrust)", table_cell),
         Paragraph("Validates real-time price rejection and candle acceptance", table_cell)],

        [Paragraph("<b>3. Technical Indicators</b>", table_cell),
         Paragraph("<b>15%</b>", table_cell_bold),
         Paragraph("Triple EMA Stack (20/50/200), Supertrend, ADX regime filter, Multi-timeframe RSI, MACD & Stochastics", table_cell),
         Paragraph("Gauges momentum, trend exhaustion, and volatility regimes", table_cell)],

        [Paragraph("<b>4. Macro & Economic</b>", table_cell),
         Paragraph("<b>15%</b>", table_cell_bold),
         Paragraph("Central Bank stance, Interest Rate Spreads, CPI/GDP/NFP surprise indices, DXY, Yield Curve (2Y-10Y)", table_cell),
         Paragraph("Ensures fundamental alignment and enforces News Blackouts", table_cell)],

        [Paragraph("<b>5. News Sentiment (NLP)</b>", table_cell),
         Paragraph("<b>15%</b>", table_cell_bold),
         Paragraph("Natural Language Processing, Sentiment Polarity scoring, Geopolitical & Banking stress categorization", table_cell),
         Paragraph("Detects real-time headline shifts and unexpected market drivers", table_cell)],

        [Paragraph("<b>6. Institutional Flow & Derivatives</b>", table_cell),
         Paragraph("<b>10%</b>", table_cell_bold),
         Paragraph("CFTC COT Speculator vs Hedger positioning, Futures Open Interest (OI) 4-Quadrant Matrix, Funding Rates", table_cell),
         Paragraph("Tracks true smart money commitments and contrarian squeeze setups", table_cell)],

        [Paragraph("<b>7. Intermarket & Volatility</b>", table_cell),
         Paragraph("<b>5%</b>", table_cell_bold),
         Paragraph("Cross-asset correlations (DXY, Gold, Oil, SPX, VIX), TTM Squeeze (BB inside KC) compression", table_cell),
         Paragraph("Captures macro divergence and explosive volatility breakouts", table_cell)],

        [Paragraph("<b>8. AI / Machine Learning</b>", table_cell),
         Paragraph("<b>5%</b>", table_cell_bold),
         Paragraph("Random Forest ensemble on historical multi-engine feature vector, Walk-forward validation", table_cell),
         Paragraph("Provides statistical probability score (P_Buy, P_Sell, P_Wait)", table_cell)],

        [Paragraph("<b>9. Unified Confluence Brain</b>", table_cell),
         Paragraph("<b>Master</b>", table_cell_bold),
         Paragraph("Asset-class dynamic weighting, minimum 2-engine agreement, net score thresholding (>=35)", table_cell),
         Paragraph("Synthesizes individual engine scores into a single directional bias", table_cell)],

        [Paragraph("<b>10. Deterministic Risk Gate</b>", table_cell),
         Paragraph("<b>Mandatory</b>", table_cell_bold),
         Paragraph("Minimum 1:1.5 R:R, ATR-based SL/TP, 1% account risk lot sizing, spread-to-SL <= 20% limit", table_cell),
         Paragraph("Protects capital; rejects trades that fail mathematical safety rules", table_cell)],
    ]

    t_summary = Table(summary_data, colWidths=[110, 65, 185, 144])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COL),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CARD_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 10))

    # ── STRATEGY ENGINE 1: SMC / ICT ──────────────────────────────
    story.append(Paragraph("2. Strategy Engine 1: Advanced SMC / ICT (Smart Money Concepts)", h1_style))
    story.append(Paragraph(
        "<b>Weight: 20% (Forex) | 25% (Crypto) | 20% (Metals)</b><br/>"
        "Smart Money Concepts (SMC) and Inner Circle Trader (ICT) principles model how institutional algorithmic liquidity providers "
        "(tier-1 banks, sovereign funds, prime brokers) manipulate and accumulate positions. "
        "Retail stop-loss orders represent liquidity pools that market makers target before executing large-scale institutional moves.",
        body_style
    ))

    smc_items = [
        "<b>Market Structure Shift (MSS) & Break of Structure (BOS):</b> The engine monitors 4-bar rolling swing highs and swing lows. "
        "A <i>Break of Structure (BOS)</i> occurs when price breaks the recent swing high in an uptrend (or swing low in a downtrend) with candle closure, confirming trend continuation. "
        "A <i>Market Structure Shift (MSS) / Change of Character (CHoCH)</i> occurs when price violently breaks the opposite swing point, signaling an institutional reversal.",

        "<b>Institutional Order Blocks (OB):</b> Detected as the final opposing candle before a powerful, multi-candle displacement move. "
        "A Bullish Order Block is the last down candle before a violent bullish rally that creates a new swing high. "
        "The engine validates Order Blocks based on three criteria: <i>Displacement strength</i> (move > 1.5x ATR), <i>Presence of an imbalance/FVG</i>, and <i>Freshness</i> (unmitigated status).",

        "<b>Fair Value Gaps (FVG) / Liquidity Imbalances:</b> An FVG is an inefficiency created during rapid one-sided institutional buying or selling. "
        "It is identified across a 3-candle sequence: Candle 1 High and Candle 3 Low do not overlap (Bullish FVG), leaving open unfilled price action. "
        "The engine filters FVGs by size (must be >= 0.25x ATR). Institutional algorithms routinely return to rebalance these gaps before continuing.",

        "<b>Breaker Blocks & Mitigation:</b> When an Order Block fails to hold and is aggressively penetrated by price, it converts into a <i>Breaker Block</i>. "
        "The former demand zone flips into structural supply (or vice versa), providing a reliable retest entry on pullbacks.",

        "<b>Liquidity Sweeps & Turtle Soup Reversals:</b> Identifies Equal Highs (EQH - Buy-Side Liquidity BSL) and Equal Lows (EQL - Sell-Side Liquidity SSL). "
        "When price penetrates above EQH or below EQL by a small margin and instantly closes back within the range with long rejection wicks, "
        "the engine detects a <i>Liquidity Sweep</i> (stop-loss hunt). This generates an immediate contrarian entry signal.",

        "<b>Premium vs. Discount Valuation & OTE (Optimal Trade Entry):</b> The active swing range (High to Low) is divided at the 50% equilibrium level. "
        "Long trades are strictly prohibited in the Premium zone (> 50%); Short trades are prohibited in Discount (< 50%). "
        "Optimal Trade Entry (OTE) is calibrated at the Fibonacci 61.8% to 78.6% retracement zone within Discount/Premium.",

        "<b>Time & Price Kill Zones:</b> High-frequency institutional flow occurs during specific geographic session overlaps: "
        "<br/>• <i>Asian Consolidation:</i> 00:00 – 08:00 UTC (defines liquidity boundaries). "
        "<br/>• <i>London Kill Zone:</i> 07:00 – 10:00 UTC (Judas swing / false morning breakout). "
        "<br/>• <i>New York Kill Zone:</i> 12:00 – 15:00 UTC (Expansion & real institutional trend continuation)."
    ]
    for item in smc_items:
        story.append(Paragraph(f"• {item}", bullet_style))

    story.append(Spacer(1, 8))

    # ── STRATEGY ENGINE 2: PRICE ACTION ───────────────────────────
    story.append(Paragraph("3. Strategy Engine 2: Pure Price Action & Candlestick Anatomy", h1_style))
    story.append(Paragraph(
        "<b>Weight: 15% across all asset classes</b><br/>"
        "The Price Action engine evaluates real-time raw price behavior, stripping away lagging indicators to focus on buyer/seller dominance, "
        "dynamic support/resistance validation, and institutional candle closing mechanics.",
        body_style
    ))

    pa_items = [
        "<b>Dynamic Support & Resistance Clusters:</b> Swing pivots are dynamically clustered using a density tolerance algorithm. "
        "Zones with 3 or more confirmed touches are designated as significant institutional support or resistance levels.",

        "<b>Breakout & Retest Confirmation:</b> A breakout is confirmed only when a candle body closes completely beyond a key S/R level. "
        "The engine then waits for a retest candle touching the boundary with rejection wicks before approving an entry, filtering out retail fakeouts.",

        "<b>False Breakouts (Wyckoff Spring & Upthrust):</b> A rapid breakout that fails to sustain and closes back inside the channel within 1 to 2 candles "
        "is recognized as an Upthrust (bearish) or Spring (bullish), indicating smart money trap execution.",

        "<b>High-Probability Candlestick Formations:</b> Algorithmic detection of high-confluence candlestick structures: "
        "<br/>• <i>Bullish / Bearish Engulfing:</i> Candle body covers >= 105% of prior candle range with volume expansion. "
        "<br/>• <i>Pin Bars & Hammers:</i> Rejection shadow must be >= 2.0x the candle body length, signaling strong rejection of higher/lower prices. "
        "<br/>• <i>Morning Star & Evening Star:</i> 3-bar reversal sequence showing exhaustion, indecision, and aggressive counter-expansion. "
        "<br/>• <i>Inside Bar Breakouts:</i> Consolidation candle completely submerged within prior mother bar, coiling energy for high-momentum directional expansion.",

        "<b>Reference Anchor Levels:</b> Tracks Previous Daily High (PDH), Previous Daily Low (PDL), Previous Weekly High (PWH), "
        "and Previous Weekly Low (PWL) as daily institutional targets."
    ]
    for item in pa_items:
        story.append(Paragraph(f"• {item}", bullet_style))

    story.append(Spacer(1, 8))

    # ── STRATEGY ENGINE 3: TECHNICAL INDICATORS ───────────────────
    story.append(Paragraph("4. Strategy Engine 3: Quantitative Technical Indicators & Regimes", h1_style))
    story.append(Paragraph(
        "<b>Weight: 15% (Forex) | 20% (Crypto) | 20% (Indices)</b><br/>"
        "Technical indicators in TradeSense Pro are not used in isolation; they are deployed as <i>regime filters</i> "
        "and <i>momentum confirmation matrices</i> configured with asset-specific sensitivities.",
        body_style
    ))

    tech_items = [
        "<b>Triple EMA Trend Stack:</b> Employs Exponential Moving Averages 20 (Fast), 50 (Intermediate), and 200 (Long-Term Macro). "
        "Bullish trend is confirmed when Close > EMA20 > EMA50 > EMA200. "
        "Golden Cross (50 crossing 200 up) and Death Cross (50 crossing 200 down) establish the overarching structural regime.",

        "<b>ADX Trend Strength Filter:</b> Average Directional Index (14-period). "
        "If ADX > 25, trend-following strategies receive full weighting. If ADX < 20, the market is classified as <i>Chop/Range</i>, "
        "suppressing breakout signals and activating mean-reversion filters.",

        "<b>Multi-Timeframe RSI & Divergence Detection:</b> 14-period RSI tuned by asset (Crypto: 75/25 extremes; Forex: 70/30). "
        "The engine calculates both Regular Divergence (Price creates Higher High while RSI creates Lower High = Trend Exhaustion) "
        "and Hidden Divergence (Price creates Higher Low while RSI creates Lower Low = Institutional Trend Continuation).",

        "<b>MACD Histogram Acceleration:</b> Moving Average Convergence Divergence (12, 26, 9). "
        "Monitors 2nd derivative of MACD histogram to detect momentum deceleration before price turns.",

        "<b>Supertrend Trailing Guide:</b> 10-period ATR with 3.0 multiplier. "
        "Provides a mathematical trailing stop-loss baseline and confirms that momentum remains aligned with the signal direction.",

        "<b>Volume Profile & Institutional POC:</b> Analyzes volume distribution across price levels. "
        "The Point of Control (POC) represents the price level with the highest traded volume. "
        "Price trading above POC indicates bullish institutional acceptance; price below POC indicates bearish distribution."
    ]
    for item in tech_items:
        story.append(Paragraph(f"• {item}", bullet_style))

    story.append(Spacer(1, 8))

    # ── STRATEGY ENGINE 4: INSTITUTIONAL FLOW & COT ──────────────
    story.append(Paragraph("5. Strategy Engine 4: Institutional Flow, COT & Derivatives", h1_style))
    story.append(Paragraph(
        "<b>Weight: 10% (Forex/Metals) | 15% (Crypto/Indices/Commodities)</b><br/>"
        "This engine tracks real capital positioning by institutions, hedge funds, and commercial hedgers via futures and options data, "
        "preventing retail traders from trading directly into major institutional walls.",
        body_style
    ))

    inst_items = [
        "<b>CFTC Commitments of Traders (COT) Positioning:</b> Tracks weekly non-commercial (speculative hedge funds) versus commercial (bank hedgers) positioning. "
        "The engine calculates a rolling 52-week positioning percentile and Z-score: "
        "<br/>• <i>Overcrowded Bullish (> 85th percentile):</i> Speculators are aggressively long; high risk of long liquidation. Contrarian bearish warning triggered. "
        "<br/>• <i>Overcrowded Bearish (< 15th percentile):</i> Speculators are heavily short; short-squeeze candidate. Contrarian bullish alert triggered. "
        "<br/>• <i>Standard Trend (60% – 85%):</i> Confirms Smart Money accumulation supporting trend continuation.",

        "<b>Futures Open Interest (OI) 4-Quadrant Dynamics:</b> Correlates 24-hour price delta against Open Interest changes: "
        "<br/>• <i>Price UP + OI UP:</i> <b>Long Accumulation</b> — Aggressive new institutional capital entering long (Strong Bullish). "
        "<br/>• <i>Price UP + OI DOWN:</i> <b>Short Covering</b> — Rally driven merely by short covering; vulnerable to sudden reversal. "
        "<br/>• <i>Price DOWN + OI UP:</i> <b>Short Addition</b> — Aggressive institutional short sellers driving market down (Strong Bearish). "
        "<br/>• <i>Price DOWN + OI DOWN:</i> <b>Long Liquidation</b> — Weak longs exiting; market searching for absorption bottom.",

        "<b>Options Put/Call Ratio & IV Percentile:</b> Put/Call ratio > 1.2 indicates extreme retail fear (contrarian bullish buy signal). "
        "P/C ratio < 0.7 indicates extreme retail complacency (contrarian top warning).",

        "<b>Crypto Perpetual Funding Rates & Liquidation Heatmap:</b> Evaluates perpetual contract funding rates. "
        "Extremely positive funding rates indicate retail longs are paying high fees to stay leveraged, triggering high probability of a long-squeeze flush."
    ]
    for item in inst_items:
        story.append(Paragraph(f"• {item}", bullet_style))

    story.append(Spacer(1, 8))

    # ── STRATEGY ENGINE 5: MACRO & CENTRAL BANK ───────────────────
    story.append(Paragraph("6. Strategy Engine 5: Macroeconomic Regimes & Central Bank Divergence", h1_style))
    story.append(Paragraph(
        "<b>Weight: 15% (Forex) | 25% (Metals/Commodities) | 20% (Indices)</b><br/>"
        "Currencies and commodities move primarily based on capital flows driven by interest rate differentials and sovereign economic growth. "
        "This engine measures fundamental macroeconomic gravity.",
        body_style
    ))

    macro_items = [
        "<b>Central Bank Monetary Policy Stance:</b> Evaluates rate differentials between Federal Reserve (USD), ECB (EUR), BOE (GBP), BOJ (JPY), "
        "RBA (AUD), and SNB (CHF). Tracks Hawkish versus Dovish bias, quantitative tightening (QT), and balance sheet expansion.",

        "<b>Economic Surprise Index:</b> Computes standardized surprise metrics for high-impact releases: "
        "<i>Surprise = (Actual - Forecast) / Historical Standard Deviation</i>. "
        "Covers Core CPI, PPI, Non-Farm Payrolls (NFP), Unemployment Rate, GDP, and Manufacturing PMI.",

        "<b>US Dollar Index (DXY) & Treasury Yield Spreads:</b> Monitors DXY momentum and the 10-Year Treasury Yield (^TNX). "
        "Rising real yields strengthen the USD and exert downward pressure on Gold (XAUUSD) and equities. "
        "Yield Curve slope (2Y vs 10Y) serves as an early recession and risk-off indicator.",

        "<b>High-Impact News Blackout Circuit Breaker:</b> TradeSense Pro strictly enforces an automated <b>45-minute blackout window</b> "
        "before and after red-folder economic releases (e.g., FOMC rate decisions, US CPI, NFP). "
        "All new trade generation is frozen during blackouts to eliminate catastrophic slippage and spread blowout."
    ]
    for item in macro_items:
        story.append(Paragraph(f"• {item}", bullet_style))

    story.append(Spacer(1, 8))

    # ── STRATEGY ENGINE 6: INTERMARKET & VOLATILITY ──────────────
    story.append(Paragraph("7. Strategy Engine 6: Cross-Asset Intermarket Correlations & Volatility", h1_style))
    story.append(Paragraph(
        "<b>Weight: 5% (Forex/Crypto) | 10% (Metals/Indices/Commodities)</b><br/>"
        "No financial asset trades in a vacuum. The Intermarket engine checks whether correlated global markets support or contradict the proposed trade.",
        body_style
    ))

    inter_items = [
        "<b>Rolling Benchmark Correlations:</b> Assesses asset behavior against historical correlation matrix: "
        "<br/>• EURUSD vs DXY (-0.96 benchmark correlation). "
        "<br/>• Gold (XAUUSD) vs DXY (-0.82) and Gold vs Real Yields (-0.75). "
        "<br/>• Crude Oil vs USDCAD (-0.72 petrocurrency inverse correlation).",

        "<b>Intermarket Divergences (Anomalies):</b> When two strongly correlated assets diverge, a major market move is brewing. "
        "For example, if Gold rallies while DXY also rallies, it signals extreme safe-haven geopolitical fear rather than standard dollar debasement.",

        "<b>TTM Squeeze Volatility Compression:</b> Identifies periods when Bollinger Bands (20, 2.0 std dev) contract entirely inside Keltner Channels (20, 1.5 ATR). "
        "This indicates extreme price coiling (low volatility). "
        "When bands expand out of Keltner Channels, the engine triggers an explosive breakout alert in the direction of the momentum histogram."
    ]
    for item in inter_items:
        story.append(Paragraph(f"• {item}", bullet_style))

    story.append(Spacer(1, 8))

    # ── STRATEGY ENGINE 7: NEWS SENTIMENT NLP ─────────────────────
    story.append(Paragraph("8. Strategy Engine 7: Real-Time NLP News Sentiment & Geopolitics", h1_style))
    story.append(Paragraph(
        "<b>Weight: 15% (Forex/Crypto) | 5% (Metals/Indices)</b><br/>"
        "Processes real-time global news feeds using specialized financial domain Natural Language Processing (NLP) "
        "to gauge market sentiment before it fully prices into technical charts.",
        body_style
    ))

    news_items = [
        "<b>Financial Sentiment Lexicon Scoring:</b> Evaluates incoming articles using domain-specific sentiment weighting "
        "(e.g., words like 'surge', 'record high', 'rate cut' produce positive scores; 'plunge', 'recession', 'default', 'stagflation' produce negative scores).",

        "<b>Source Reliability Tiering:</b> News feeds are classified into reliability tiers: "
        "<br/>• <i>Tier 1 (Multiplier 1.5x):</i> Reuters, Bloomberg, Financial Times, Wall Street Journal. "
        "<br/>• <i>Tier 2 (Multiplier 1.0x):</i> CNBC, MarketWatch, Yahoo Finance. "
        "<br/>• <i>Tier 3 (Multiplier 0.5x):</i> General news aggregators and social channels.",

        "<b>Categorical Event Filtering:</b> Classifies news into high-impact categories: Geopolitics (war, sanctions, tariffs), "
        "Central Banking, Financial Stress (banking crises, credit default swaps), and Energy Supplies (OPEC+ quotas)."
    ]
    for item in news_items:
        story.append(Paragraph(f"• {item}", bullet_style))

    story.append(Spacer(1, 8))

    # ── STRATEGY ENGINE 8: AI / ML ENSEMBLE ────────────────────────
    story.append(Paragraph("9. Strategy Engine 8: AI / Machine Learning Ensemble Model", h1_style))
    story.append(Paragraph(
        "<b>Weight: 5% (Forex) | 0% - 10% (Tuned per asset)</b><br/>"
        "TradeSense Pro utilizes an ensemble Machine Learning model (Random Forest & Gradient Boosting) "
        "to discover non-linear patterns across multi-engine features without look-ahead bias.",
        body_style
    ))

    ai_items = [
        "<b>Multi-Engine Feature Store:</b> Feature vector extracts normalized returns, moving average spreads, rolling volatility, "
        "RSI momentum, ATR normalized ranges, and volume differentials over a 60-candle lookback.",

        "<b>Walk-Forward Validation:</b> Strict out-of-sample time-series validation prevents overfitting. "
        "The model is prohibited from using future bars during historical training.",

        "<b>Probabilistic Output:</b> Generates class probabilities: <i>P(BUY)</i>, <i>P(SELL)</i>, and <i>P(WAIT)</i>. "
        "A signal is only reinforced if the AI probability confirms the dominant directional bias.",

        "<b>AI Safety Gate:</b> By design, the AI/ML engine operates purely as an advisory evidence engine. "
        "It is mathematically forbidden from overriding deterministic risk rules or forcing trades during blackout periods."
    ]
    for item in ai_items:
        story.append(Paragraph(f"• {item}", bullet_style))

    story.append(Spacer(1, 8))

    # ── UNIFIED CONFLUENCE & WEIGHTING ────────────────────────────
    story.append(Paragraph("10. Master Synthesis: Unified Confluence & Asset Weights", h1_style))
    story.append(Paragraph(
        "The <b>Unified Signal Engine</b> serves as the master decision matrix. "
        "It aggregates raw directional scores (-100 to +100) from all active engines using asset-specific weighting profiles. "
        "Because crypto behaves differently from gold or foreign exchange, weights dynamically adjust according to asset class characteristics:",
        body_style
    ))

    # Weight Table
    weights_data = [
        [Paragraph("Engine", table_header),
         Paragraph("Forex", table_header),
         Paragraph("Crypto", table_header),
         Paragraph("Metals (Gold)", table_header),
         Paragraph("Indices (SPX)", table_header),
         Paragraph("Commodities", table_header)],
        
        [Paragraph("SMC / ICT", table_cell_bold), Paragraph("20%", table_cell), Paragraph("25%", table_cell), Paragraph("20%", table_cell), Paragraph("15%", table_cell), Paragraph("15%", table_cell)],
        [Paragraph("Price Action", table_cell_bold), Paragraph("15%", table_cell), Paragraph("15%", table_cell), Paragraph("15%", table_cell), Paragraph("15%", table_cell), Paragraph("15%", table_cell)],
        [Paragraph("Technical Indicators", table_cell_bold), Paragraph("15%", table_cell), Paragraph("20%", table_cell), Paragraph("15%", table_cell), Paragraph("20%", table_cell), Paragraph("15%", table_cell)],
        [Paragraph("Macro & Central Bank", table_cell_bold), Paragraph("15%", table_cell), Paragraph("5%", table_cell), Paragraph("25%", table_cell), Paragraph("20%", table_cell), Paragraph("25%", table_cell)],
        [Paragraph("News Sentiment (NLP)", table_cell_bold), Paragraph("15%", table_cell), Paragraph("15%", table_cell), Paragraph("5%", table_cell), Paragraph("5%", table_cell), Paragraph("5%", table_cell)],
        [Paragraph("Institutional Flow / COT", table_cell_bold), Paragraph("10%", table_cell), Paragraph("15%", table_cell), Paragraph("10%", table_cell), Paragraph("15%", table_cell), Paragraph("15%", table_cell)],
        [Paragraph("Intermarket Correlation", table_cell_bold), Paragraph("5%", table_cell), Paragraph("5%", table_cell), Paragraph("10%", table_cell), Paragraph("10%", table_cell), Paragraph("10%", table_cell)],
        [Paragraph("AI / ML Ensemble", table_cell_bold), Paragraph("5%", table_cell), Paragraph("0%", table_cell), Paragraph("0%", table_cell), Paragraph("0%", table_cell), Paragraph("0%", table_cell)],
        [Paragraph("<b>TOTAL</b>", table_cell_bold), Paragraph("<b>100%</b>", table_cell_bold), Paragraph("<b>100%</b>", table_cell_bold), Paragraph("<b>100%</b>", table_cell_bold), Paragraph("<b>100%</b>", table_cell_bold), Paragraph("<b>100%</b>", table_cell_bold)]
    ]

    t_weights = Table(weights_data, colWidths=[130, 70, 70, 75, 75, 84])
    t_weights.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COL),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, CARD_BG]),
        ('BACKGROUND', (0, -1), (-1, -1), HIGHLIGHT_BG),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_weights)
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "<b>Confluence Thresholds & Decision Rules:</b><br/>"
        "• <b>Minimum 2-Engine Rule:</b> A trade is never issued unless at least 2 distinct engines agree on the direction (BUY or SELL).<br/>"
        "• <b>Net Score Threshold:</b> Normalized Net Score must be >= 35.0. Any score below 35 results in a mandatory <b>WAIT</b> state.<br/>"
        "• <b>Confidence Formula:</b> <code>Confidence = (Normalized Net Score × 0.60) + (Engine Confluence % × 0.40)</code>. "
        "Scaled down if data quality is degraded. Maximum confidence is capped at 98.0% (acknowledging market uncertainty).<br/>"
        "• <b>Classification:</b> STRONG (Confidence >= 70%), MODERATE (50% – 69.9%), WEAK (< 50%).",
        body_style
    ))

    story.append(Spacer(1, 8))

    # ── DETERMINISTIC RISK MANAGEMENT ─────────────────────────────
    story.append(Paragraph("11. Deterministic Risk Management & Execution Rules", h1_style))
    story.append(Paragraph(
        "Capital protection is paramount. Even the highest-confidence signal is discarded if it fails any deterministic risk rule. "
        "The Risk Engine operates as an independent, non-overridable gatekeeper.",
        body_style
    ))

    risk_items = [
        "<b>Strict Risk:Reward Ratio (Minimum 1:1.5 Mandatory):</b> The ratio of projected reward (TP1 distance) to risk (SL distance) "
        "must be at least 1:1.5. Trades offering less than 1.5 R:R are immediately rejected with an explicit rejection log.",

        "<b>Multi-Tier Profit Targets (ATR Multipliers):</b> "
        "<br/>• <i>Stop Loss (SL):</i> Entry ± (1.5 × ATR). Placed beyond key structural invalidation points. "
        "<br/>• <i>Take Profit 1 (TP1):</i> Entry ± (2.0 × ATR) — Target for securing initial profits and moving SL to Breakeven. "
        "<br/>• <i>Take Profit 2 (TP2):</i> Entry ± (3.5 × ATR) — Extended structural swing target. "
        "<br/>• <i>Take Profit 3 (TP3):</i> Entry ± (5.0 × ATR) — Runner target for strong trending expansions.",

        "<b>Mathematical Position Sizing (1% Account Risk):</b> Lot sizing is calculated dynamically using the formula: "
        "<br/><code>Lots = (Account Balance × Risk Percentage) / (Stop Loss in Points × Point Value per Lot)</code>. "
        "Ensures consistent risk exposure regardless of volatility or timeframe.",

        "<b>Spread-to-Stop-Loss Cost Ratio:</b> The live broker spread cannot consume more than <b>20% of the Stop Loss distance</b>. "
        "If a wide spread during illiquid sessions would eat into the trade's risk envelope, the trade is rejected.",

        "<b>Data Quality & Reliability Gating:</b> The OHLCV data feed is constantly audited for anomalous zero-volume candles, "
        "stale timestamps (> 2 bars old), and inverted High-Low ticks. Any integrity breach immediately forces the system to <b>WAIT</b>."
    ]
    for item in risk_items:
        story.append(Paragraph(f"• {item}", bullet_style))

    story.append(Spacer(1, 10))

    # ── COMPLETE TRADE LIFECYCLE ──────────────────────────────────
    story.append(Paragraph("12. Complete Lifecycle of a Trade (Step-by-Step)", h1_style))
    
    lifecycle_data = [
        [Paragraph("Step", table_header),
         Paragraph("Phase", table_header),
         Paragraph("Action Performed", table_header),
         Paragraph("Exit / Failure Condition", table_header)],

        [Paragraph("<b>1</b>", table_cell_bold),
         Paragraph("Data Ingestion", table_cell),
         Paragraph("Fetch 200 OHLCV candles, validate bar continuity, check for spread anomalies.", table_cell),
         Paragraph("Data error / Stale feed -> Force WAIT.", table_cell)],

        [Paragraph("<b>2</b>", table_cell_bold),
         Paragraph("Blackout Check", table_cell),
         Paragraph("Audit Economic Calendar for red-folder news within ±45 min window.", table_cell),
         Paragraph("Active Blackout -> Trade suppressed.", table_cell)],

        [Paragraph("<b>3</b>", table_cell_bold),
         Paragraph("Engine Execution", table_cell),
         Paragraph("Concurrently execute SMC, Price Action, Technical, Macro, News, COT, Intermarket & AI.", table_cell),
         Paragraph("Engine errors handled gracefully as neutral.", table_cell)],

        [Paragraph("<b>4</b>", table_cell_bold),
         Paragraph("Confluence Synthesis", table_cell),
         Paragraph("Calculate asset-weighted score. Check minimum 2-engine agreement and >=35 score.", table_cell),
         Paragraph("Score < 35 or conflicting engines -> Force WAIT.", table_cell)],

        [Paragraph("<b>5</b>", table_cell_bold),
         Paragraph("Price Level Calculation", table_cell),
         Paragraph("Derive Entry, SL (1.5x ATR), TP1 (2.0x ATR), TP2 (3.5x ATR), TP3 (5.0x ATR).", table_cell),
         Paragraph("R:R < 1.5 -> Trade rejected.", table_cell)],

        [Paragraph("<b>6</b>", table_cell_bold),
         Paragraph("Risk Gatekeeper", table_cell),
         Paragraph("Calculate lot size for 1% risk. Verify spread cost <= 20% of SL.", table_cell),
         Paragraph("Excessive spread -> Trade rejected.", table_cell)],

        [Paragraph("<b>7</b>", table_cell_bold),
         Paragraph("Signal Dispatch", table_cell),
         Paragraph("Publish validated signal with full analysis, confidence rating, and recommended lots.", table_cell),
         Paragraph("Signal logged to database & live dashboard.", table_cell)],
    ]

    t_life = Table(lifecycle_data, colWidths=[35, 95, 230, 144])
    t_life.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COL),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CARD_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_life)
    story.append(Spacer(1, 14))

    # ── CONCLUSION / SIGN-OFF BOX ─────────────────────────────────
    conclusion_text = (
        "<b>Summary & Production Verification:</b><br/>"
        "TradeSense Pro's multi-layered strategy framework ensures that no trade is taken based on a single arbitrary signal. "
        "By fusing Smart Money accumulation zones with macroeconomic fundamentals, institutional order flow, technical trend confirmation, "
        "and strict mathematical risk budgeting, the system achieves maximum edge while actively shielding investor capital from market volatility."
    )
    t_box = Table([[Paragraph(conclusion_text, callout_text)]], colWidths=[504])
    t_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HIGHLIGHT_BG),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#93c5fd")),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(t_box)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated: {output_filename}")


if __name__ == '__main__':
    out_file = sys.argv[1] if len(sys.argv) > 1 else "TradeSense_Pro_Trading_Strategies_Deep_Dive.pdf"
    create_strategies_pdf(out_file)
