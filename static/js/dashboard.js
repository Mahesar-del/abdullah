/**
 * TradeSense Pro — Dashboard JavaScript
 * Fetches live data from Django API and updates UI
 */

// ── State ──────────────────────────────────────────────
let allSignals = [];
let currentFilter = 'ALL';
let currentTimeframe = 'ALL';

const TF_LABELS = { M1: '1m', M5: '5m', M15: '15m', M30: '30m', H1: '1H', H2: '2H', H4: '4H' };

// ── On Load ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    startClock();
    loadDashboardData();
    updateMarketSession();
    loadAutomationStatus();
    setInterval(updateMarketSession, 60000);
    setInterval(loadStats, 15000);   // auto-refresh scores every 15s
    setInterval(loadActiveSignals, 10000); // auto-refresh active signals every 10s (high-conviction signals appear automatically)
    setInterval(loadAutomationStatus, 5000); // auto-refresh automated trading engine status every 5s
    setupSidebarNav();

    // Restore Automated Trading console collapse state (opened if previously toggled open)
    const savedAutoState = localStorage.getItem('ts_auto_console_open');
    const autoSec = document.getElementById('auto-console-section');
    const navAutoBtn = document.getElementById('nav-auto-trading-btn');
    if (savedAutoState === 'true' && autoSec) {
        autoSec.classList.remove('collapsed');
        if (navAutoBtn) navAutoBtn.classList.add('active');
    }
});

// ── Sidebar & Mobile/Tablet Navigation ─────────────────
function toggleMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (!sidebar) return;
    const isOpen = sidebar.classList.toggle('open');
    if (backdrop) backdrop.classList.toggle('open', isOpen);
}

function closeMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (sidebar) sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('open');
}

function mobileNavJump(targetKey, btnEl) {
    closeMobileSidebar();
    document.querySelectorAll('.mobile-nav-item').forEach(b => b.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');

    if (targetKey === 'top') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
    }
    if (targetKey === 'auto') {
        const autoSec = document.getElementById('auto-console-section');
        const navBtn = document.getElementById('nav-auto-trading-btn');
        if (autoSec) {
            autoSec.classList.remove('collapsed');
            if (navBtn) navBtn.classList.add('active');
            localStorage.setItem('ts_auto_console_open', 'true');
            autoSec.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        return;
    }
    if (targetKey === 'signals') {
        document.querySelector('.signals-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
    }
    if (targetKey === 'pairs') {
        document.getElementById('pair-scores-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
    }
}

function setupSidebarNav() {
    const navItems = document.querySelectorAll('.nav-item');
    
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Remove active class from all
            navItems.forEach(nav => nav.classList.remove('active'));
            // Add active class to clicked
            item.classList.add('active');
            
            // Scroll to section based on ID
            const id = item.id;
            let target = null;
            
            if (id === 'nav-dashboard')   target = document.querySelector('.stats-grid');
            if (id === 'nav-signals')     target = document.querySelector('.signals-section');
            if (id === 'nav-markets')     target = document.querySelector('.engine-section');
            if (id === 'nav-analysis')    target = document.querySelector('.direction-bar-section');
            if (id === 'nav-news')        target = document.querySelector('.news-section');
            if (id === 'nav-performance') target = document.querySelector('.r-multiple-section');
            
            closeMobileSidebar();

            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
}


// ── Live Clock ─────────────────────────────────────────
function startClock() {
    function tick() {
        const now = new Date();
        document.getElementById('live-clock').textContent =
            now.toLocaleTimeString('en-US', { hour12: false, timeZone: 'Asia/Karachi' });
    }
    tick();
    setInterval(tick, 1000);
}

// ── Market Session ─────────────────────────────────────
function updateMarketSession() {
    const now = new Date();
    const utcHour = now.getUTCHours();

    let session = 'Closed';
    let isOpen  = false;

    if (utcHour >= 22 || utcHour < 7)  { session = '🇦🇺 Sydney Session';     isOpen = true; }
    if (utcHour >= 0  && utcHour < 9)  { session = '🇯🇵 Tokyo Session';      isOpen = true; }
    if (utcHour >= 7  && utcHour < 16) { session = '🇬🇧 London Session';     isOpen = true; }
    if (utcHour >= 12 && utcHour < 21) { session = '🇺🇸 New York Session';   isOpen = true; }
    if (utcHour >= 12 && utcHour < 16) { session = '⚡ London-NY Overlap';   isOpen = true; }

    const dot = document.querySelector('.status-dot');
    const statusEl = document.getElementById('market-status');
    const sessionEl = document.getElementById('session-info');

    if (isOpen) {
        dot.classList.add('active');
        statusEl.querySelector('span').textContent = 'Market Open';
        statusEl.style.color = 'var(--buy-color)';
    } else {
        dot.classList.remove('active');
        statusEl.querySelector('span').textContent = 'Market Closed';
        statusEl.style.color = 'var(--text-muted)';
    }

    sessionEl.textContent = session;
}

// ── Load All Data ──────────────────────────────────────
async function loadDashboardData() {
    const btn = document.getElementById('refresh-btn');
    btn.innerHTML = '<span class="refresh-icon" style="animation:spin 1s linear infinite">↻</span> Loading...';
    btn.disabled = true;

    try {
        await Promise.all([
            loadStats(),
            loadActiveSignals(),
            loadNewsEvents(),
        ]);
    } catch (err) {
        console.error('Error loading dashboard:', err);
    }

    btn.innerHTML = '<span class="refresh-icon">↻</span> Refresh';
    btn.disabled = false;
}

// ── Load Stats ─────────────────────────────────────────
async function loadStats() {
    try {
        const res  = await fetch('/api/signals/stats/');
        const data = await res.json();

        animateValue('stat-total-val',  data.total_signals,  0);
        animateValue('stat-active-val', data.active_signals, 0);
        document.getElementById('stat-winrate-val').textContent    = data.win_rate_percent + '%';
        
        // ── Institutional R-Multiple Context Display Next to Win Rate ─────
        const elSampleN = document.getElementById('winrate-sample-n');
        if (elSampleN) elSampleN.textContent = `n=${data.sample_size_trades || 0}`;
        const elWinR = document.getElementById('winrate-avg-win');
        if (elWinR) elWinR.textContent = `Win: +${Number(data.avg_win_r || 0).toFixed(2)}R`;
        const elLossR = document.getElementById('winrate-avg-loss');
        if (elLossR) elLossR.textContent = `Loss: -${Number(data.avg_loss_r || 0).toFixed(2)}R`;
        const elPf = document.getElementById('winrate-pf');
        if (elPf) elPf.textContent = `PF: ${Number(data.profit_factor || 0).toFixed(2)}`;
        const elExp = document.getElementById('winrate-exp');
        if (elExp) {
            const expVal = Number(data.expectancy_r || 0);
            elExp.textContent = `Exp: ${expVal >= 0 ? '+' : ''}${expVal.toFixed(2)}R`;
            elExp.style.color = expVal >= 0 ? '#10b981' : '#ef4444';
        }
        const elCi = document.getElementById('winrate-ci');
        if (elCi) {
            if (data.expectancy_ci_95 && data.sample_size_trades >= 100) {
                elCi.textContent = `95% CI: [${Number(data.expectancy_ci_95[0]).toFixed(2)}, ${Number(data.expectancy_ci_95[1]).toFixed(2)}]`;
            } else {
                elCi.textContent = `95% CI: [n < 100 trades]`;
            }
        }

        document.getElementById('stat-confidence-val').textContent = data.avg_confidence;
        
        animateValue('stat-won-val', data.take_profit_hits || 0, 0);
        animateValue('stat-lost-val', data.stop_loss_hits || 0, 0);

        // ── R-Multiple Performance Tracking (Phase 12) ─────
        const avgWinEl = document.getElementById('stat-avg-win-val');
        if (avgWinEl) {
            const winR = data.avg_win_r !== undefined ? Number(data.avg_win_r).toFixed(2) : '0.00';
            avgWinEl.textContent = `+${winR} R`;
        }

        const avgLossEl = document.getElementById('stat-avg-loss-val');
        if (avgLossEl) {
            const lossR = data.avg_loss_r !== undefined ? Number(data.avg_loss_r).toFixed(2) : '0.00';
            avgLossEl.textContent = `${lossR} R`;
        }

        const pfEl = document.getElementById('stat-profit-factor-val');
        if (pfEl) {
            const pf = data.profit_factor !== undefined ? Number(data.profit_factor).toFixed(2) : '0.00';
            pfEl.textContent = pf;
        }

        const expEl = document.getElementById('stat-expectancy-val');
        if (expEl) {
            const exp = data.expectancy_r !== undefined ? Number(data.expectancy_r) : 0.0;
            expEl.textContent = `${exp >= 0 ? '+' : ''}${exp.toFixed(2)} R`;
        }

        // Strictly Computed Edge Status & Badges (Honesty Rule 1)
        const nTrades = data.sample_size_trades || 0;
        const expVal = Number(data.expectancy_r || 0);
        const bootP5 = data.bootstrap_p5 !== undefined && data.bootstrap_p5 !== null ? Number(data.bootstrap_p5) : -1.0;

        let computedStatus = 'INSUFFICIENT_DATA';
        let computedLabel = `Insufficient data (n=${nTrades}/100)`;
        let computedColor = '#94a3b8';

        if (nTrades < 100) {
            computedStatus = 'INSUFFICIENT_DATA';
            computedLabel = `Insufficient data (n=${nTrades}/100)`;
            computedColor = '#94a3b8';
        } else if (expVal < 0) {
            computedStatus = 'NEGATIVE_EDGE';
            computedLabel = 'Negative edge';
            computedColor = '#ef4444';
        } else if (bootP5 > 0) {
            computedStatus = 'POSITIVE_EDGE';
            computedLabel = 'Positive edge';
            computedColor = '#10b981';
        } else {
            computedStatus = 'UNCERTAIN_EDGE';
            computedLabel = 'Unproven edge (CI spans 0)';
            computedColor = '#f59e0b';
        }

        const edgeBadge = document.getElementById('edge-badge');
        if (edgeBadge) {
            edgeBadge.textContent = computedLabel;
            edgeBadge.style.color = computedColor;
            edgeBadge.style.borderColor = computedColor;
            edgeBadge.style.background = `${computedColor}26`;
        }

        const expEdge = document.getElementById('stat-expectancy-edge');
        if (expEdge) {
            expEdge.textContent = computedLabel;
            expEdge.style.color = computedColor;
            expEdge.className = computedStatus === 'POSITIVE_EDGE' ? 'stat-trend up' : (computedStatus === 'NEGATIVE_EDGE' ? 'stat-trend down' : 'stat-trend');
        }

        const ddEl = document.getElementById('stat-max-drawdown-val');
        if (ddEl) {
            const dd = data.max_drawdown_pct !== undefined ? Number(data.max_drawdown_pct).toFixed(1) : '0.0';
            ddEl.textContent = `${dd}%`;
        }

        // ── Section 15.1 Loss Breakdown Diagnostics ─────────
        const lb = data.loss_breakdown || {};
        const elWrongRegime = document.getElementById('loss-wrong-regime');
        if (elWrongRegime) elWrongRegime.textContent = lb.WRONG_REGIME || 0;
        const elFalseBreak = document.getElementById('loss-false-breakout');
        if (elFalseBreak) elFalseBreak.textContent = lb.FALSE_BREAKOUT_TRAP || 0;
        const elNewsShock = document.getElementById('loss-news-shock');
        if (elNewsShock) elNewsShock.textContent = lb.NEWS_SHOCK || 0;
        const elPoorInval = document.getElementById('loss-poor-invalidation');
        if (elPoorInval) elPoorInval.textContent = lb.POOR_STRUCTURAL_INVALIDATION || 0;

        // Adaptive win rate label
        const isActual = data.win_rate_source === 'actual';
        document.getElementById('winrate-label').textContent = isActual ? 'Win Rate'      : 'Running Score';
        const ratioText = isActual ? `Actual Trades (${data.take_profit_hits}W / ${data.stop_loss_hits}L)` : 'Avg Confidence';
        document.getElementById('winrate-trend').textContent = ratioText;

        // Direction bar
        const total   = data.by_direction.BUY + data.by_direction.SELL + data.by_direction.WAIT || 1;
        const buyPct  = (data.by_direction.BUY  / total * 100).toFixed(1);
        const sellPct = (data.by_direction.SELL / total * 100).toFixed(1);
        const waitPct = (data.by_direction.WAIT / total * 100).toFixed(1);

        document.getElementById('bar-buy').style.width  = buyPct  + '%';
        document.getElementById('bar-sell').style.width = sellPct + '%';
        document.getElementById('bar-wait').style.width = waitPct + '%';

        document.getElementById('buy-count').textContent  = data.by_direction.BUY;
        document.getElementById('sell-count').textContent = data.by_direction.SELL;
        document.getElementById('wait-count').textContent = data.by_direction.WAIT;

        // Per-pair running score cards
        renderPairScores(data.instrument_scores || [], data.win_rate_source);

    } catch (err) {
        console.log('Stats not available:', err.message);
        document.getElementById('stat-total-val').textContent      = '0';
        document.getElementById('stat-active-val').textContent     = '0';
        document.getElementById('stat-won-val').textContent        = '0';
        document.getElementById('stat-lost-val').textContent       = '0';
        document.getElementById('stat-winrate-val').textContent    = '0%';
        document.getElementById('stat-confidence-val').textContent = '0';
    }
}

// ── Render Per-Pair Score Cards ────────────────────────
function renderPairScores(scores, source) {
    const grid  = document.getElementById('pair-scores-grid');
    const badge = document.getElementById('pair-scores-source-badge');

    if (badge) {
        badge.textContent = source === 'actual' ? '✅ Actual Win Rate' : '📊 Avg Confidence Score';
        badge.style.background = source === 'actual'
            ? 'rgba(34,197,94,0.15)' : 'rgba(59,130,246,0.15)';
        badge.style.color = source === 'actual' ? 'var(--buy-color)' : 'var(--accent-blue)';
    }

    if (!scores || scores.length === 0) {
        grid.innerHTML = '<div class="pair-score-loading">No instrument data available.</div>';
        return;
    }

    grid.innerHTML = scores.map(p => {
        const dirClass = p.direction.toLowerCase();
        const icon = p.direction === 'BUY' ? '🟢' : p.direction === 'SELL' ? '🔴' : '🟡';
        const metaText = p.closed > 0
            ? `${p.tp}W / ${p.sl}L (${p.closed} closed)`
            : `${p.closed === 0 ? 'No closed trades' : p.closed + ' closed'}`;

        return `
        <div class="pair-score-card dir-${dirClass}" style="cursor:pointer" title="Click to view trade history" onclick="openPairHistory('${p.symbol}')">
            <div class="pair-score-header">
                <div>
                    <div class="pair-score-symbol">${p.symbol}</div>
                    <div class="pair-score-name">${p.name || ''}</div>
                </div>
                <span class="pair-score-dir ${dirClass}">${icon} ${p.direction}</span>
            </div>
            <div class="pair-score-pct">${p.score.toFixed(1)}<span>%</span></div>
            <div class="pair-score-bar">
                <div class="pair-score-bar-fill" style="width:0%" data-target="${Math.min(p.score, 100)}"></div>
            </div>
            <div class="pair-score-meta">
                <span>${metaText}</span>
                <span>Conf: ${p.confidence.toFixed(0)}%</span>
            </div>
        </div>`;
    }).join('');

    // Animate progress bars after render
    requestAnimationFrame(() => {
        document.querySelectorAll('.pair-score-bar-fill').forEach(bar => {
            bar.style.width = bar.dataset.target + '%';
        });
    });
}

// ── Load Active Signals ────────────────────────────────
async function loadActiveSignals() {
    try {
        const res  = await fetch('/api/signals/active/');
        const data = await res.json();
        allSignals = data.results || data || [];
        renderSignals(allSignals);
    } catch (err) {
        console.log('Signals not available:', err.message);
        renderEmptySignals('No signals yet. Database setup pending.');
    }
}

// ── Render Signals Table ───────────────────────────────
function renderSignals(signals) {
    const tbody = document.getElementById('signals-tbody');

    const filtered = signals.filter(s =>
        (currentFilter === 'ALL' || s.direction === currentFilter) &&
        (currentTimeframe === 'ALL' || s.timeframe === currentTimeframe)
    );

    if (filtered.length === 0) {
        const tfText = currentTimeframe === 'ALL' ? '' : ` on ${TF_LABELS[currentTimeframe]}`;
        renderEmptySignals(currentFilter === 'ALL'
            ? `Continuous auto-scanner is actively monitoring live markets${tfText}... Only high-probability setups (≥75% confidence) appear automatically.`
            : `No high-conviction ${currentFilter} signals${tfText} (filtered for ≥75% confidence).`);
        return;
    }

    tbody.innerHTML = filtered.map(s => {
        const dClass = s.decision_class || s.strength || 'STRONG';
        const regime = s.market_regime || 'TRENDING';
        return `
        <tr onclick="openSignalModal(${s.id})" title="Click for details">
            <td>
                <div style="font-weight:600">${s.instrument_symbol}</div>
                <div style="font-size:11px;color:var(--text-muted)">${s.instrument_name || ''}</div>
            </td>
            <td><span class="badge badge-${s.direction.toLowerCase()}">${directionIcon(s.direction)} ${s.direction}</span></td>
            <td><span class="badge badge-${dClass.toLowerCase()}" style="font-size:11px">${dClass}</span></td>
            <td><span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--accent-cyan);background:rgba(56,189,248,0.1);padding:2px 6px;border-radius:4px">${regime}</span></td>
            <td><span style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-secondary)">${s.timeframe}</span></td>
            <td><span class="price-val">${s.entry_price}</span></td>
            <td><span class="price-val sl-val">${s.stop_loss}</span></td>
            <td><span class="price-val tp-val">${s.take_profit_1}</span></td>
            <td><span class="rr-val" style="color:#10b981;font-weight:700">${s.risk_reward}:1</span></td>
            <td>
                <div class="conf-bar-wrap">
                    <div class="conf-bar"><div class="conf-fill" style="width:${s.confidence_score}%"></div></div>
                    <span class="conf-text">${s.confidence_score}%</span>
                </div>
            </td>
            <td style="color:var(--text-muted);font-size:12px">${formatTime(s.generated_at)}</td>
        </tr>
    `;}).join('');
}

function renderEmptySignals(msg) {
    document.getElementById('signals-tbody').innerHTML = `
        <tr>
            <td colspan="11" class="empty-state">
                <div class="empty-icon">📡</div>
                <div>${msg}</div>
            </td>
        </tr>`;
}

// ── Filter Signals ─────────────────────────────────────
function filterSignals(direction) {
    currentFilter = direction;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));

    const map = { ALL: 0, BUY: 1, SELL: 2, WAIT: 3 };
    document.querySelectorAll('.filter-btn')[map[direction]]?.classList.add('active');

    renderSignals(allSignals);
}

// ── Timeframe Selector ─────────────────────────────────
// Auto-scan interval per timeframe (= one candle length)
const TF_SCAN_MS = {
    M1: 60e3, M5: 300e3, M15: 900e3, M30: 1800e3,
    H1: 3600e3, H2: 7200e3, H4: 14400e3,
};
let autoScanTimer = null;

function selectTimeframe(tf) {
    clearInterval(autoScanTimer);
    autoScanTimer = null;
    currentTimeframe = tf;
    document.querySelectorAll('.tf-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.tf === tf));
    closeMobileSidebar();
    renderSignals(allSignals);
    document.querySelector('.signals-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });

    if (tf !== 'ALL') {
        scanWhenIdle();  // scan right away (waits if a previous scan is still running)
        autoScanTimer = setInterval(() => scanMarkets(true), TF_SCAN_MS[tf]);
    }
}

// Run a silent scan for the current timeframe once any running scan finishes
function scanWhenIdle() {
    const tfAtClick = currentTimeframe;
    const tryScan = () => {
        if (tfAtClick !== currentTimeframe) return;  // user switched again
        if (isScanning) { setTimeout(tryScan, 1000); return; }
        scanMarkets(true);
    };
    tryScan();
}

// ── Load News Events ───────────────────────────────────
async function loadNewsEvents() {
    const el = document.getElementById('news-list');
    try {
        const res  = await fetch('/api/signals/news-events/');
        const data = await res.json();
        const events = data.results || data || [];

        if (events.length === 0) {
            el.innerHTML = '<div class="news-no-data">📅 No upcoming high-impact news events found.</div>';
            return;
        }

        el.innerHTML = events.map(e => `
            <div class="news-item">
                <span class="news-impact impact-${e.impact.toLowerCase()}">${e.impact}</span>
                <span class="news-time">${formatTime(e.event_time)}</span>
                <span class="news-currency">${e.currency}</span>
                <span class="news-title">${e.title}</span>
                ${e.forecast ? `<span style="font-size:11px;color:var(--text-muted)">F: ${e.forecast}</span>` : ''}
            </div>
        `).join('');
    } catch (err) {
        el.innerHTML = '<div class="news-no-data">News events will load once database is connected.</div>';
    }
}

// ── Signal Chart & Real-Time Live Streaming Modal ──────
let currentChartInstance = null;
let currentChartSeries = null;
let currentChartData = [];
let currentSignalPayload = null;
let currentChartTf = 'H1';
let currentChartMode = 'PLACEMENT'; // 'PLACEMENT' | 'TRADINGVIEW'
let showEmaOverlay = true;
let showVolumeOverlay = true;
let livePollTimer = null;
let liveHeartbeatTimer = null;
let liveWebSocket = null;
let chartResizeObserver = null;
let lastDisplayedPrice = null;
let wsInitialPrice = null;
let wsAnchorChartPrice = null;
let isHoveringCrosshair = false;

const BINANCE_WS_MAP = {
    BTCUSD: 'btcusdt',
    ETHUSD: 'ethusdt',
    BNBUSD: 'bnbusdt',
    SOLUSD: 'solusdt',
    XRPUSD: 'xrpusdt',
    XAUUSD: 'paxgusdt',
    EURUSD: 'eurusdt',
    GBPUSD: 'gbpusdt',
};

const TRADINGVIEW_SYMBOL_MAP = {
    XAUUSD: 'OANDA:XAUUSD',
    XAGUSD: 'OANDA:XAGUSD',
    EURUSD: 'FX:EURUSD',
    GBPUSD: 'FX:GBPUSD',
    USDJPY: 'FX:USDJPY',
    USDCHF: 'FX:USDCHF',
    AUDUSD: 'FX:AUDUSD',
    USDCAD: 'FX:USDCAD',
    NZDUSD: 'FX:NZDUSD',
    EURGBP: 'FX:EURGBP',
    EURJPY: 'FX:EURJPY',
    GBPJPY: 'FX:GBPJPY',
    BTCUSD: 'BINANCE:BTCUSDT',
    ETHUSD: 'BINANCE:ETHUSDT',
    BNBUSD: 'BINANCE:BNBUSDT',
    SOLUSD: 'BINANCE:SOLUSDT',
    XRPUSD: 'BINANCE:XRPUSDT',
    US30:   'BLACKBULL:US30',
    NAS100: 'BLACKBULL:NAS100',
    SPX500: 'FOREXCOM:SPXUSD',
    USOIL:  'TVC:USOIL',
};

const TV_INTERVAL_MAP = {
    M1: '1', M5: '5', M15: '15', M30: '30',
    H1: '60', H2: '120', H4: '240', D1: 'D',
};

const TF_SECONDS_MAP = {
    M1: 60, M5: 300, M15: 900, M30: 1800,
    H1: 3600, H2: 7200, H4: 14400, D1: 86400,
};

function formatChartPrice(val, symbol = '') {
    const num = Number(val);
    if (!Number.isFinite(num)) return '—';
    const sym = (symbol || '').toUpperCase();
    if (sym.includes('JPY')) return num.toFixed(3);
    if (num >= 1000) return num.toFixed(2);
    if (num >= 10) return num.toFixed(3);
    return num.toFixed(5);
}

function formatVolumeCompact(val) {
    const v = Number(val) || 0;
    if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B';
    if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
    return v > 0 ? v.toFixed(0) : '—';
}

function computeEMASeries(candles, period) {
    if (!candles || candles.length === 0) return [];
    const k = 2 / (period + 1);
    const out = [];
    let emaVal = candles[0].close;
    for (let i = 0; i < candles.length; i++) {
        emaVal = i === 0 ? candles[i].close : candles[i].close * k + emaVal * (1 - k);
        out.push({ time: candles[i].time, value: emaVal });
    }
    return out;
}

function stopLiveChartStream() {
    if (livePollTimer) {
        clearInterval(livePollTimer);
        livePollTimer = null;
    }
    if (liveHeartbeatTimer) {
        clearInterval(liveHeartbeatTimer);
        liveHeartbeatTimer = null;
    }
    if (liveWebSocket) {
        try {
            liveWebSocket.onclose = null;
            liveWebSocket.onerror = null;
            liveWebSocket.onmessage = null;
            liveWebSocket.close();
        } catch (e) {}
        liveWebSocket = null;
    }
    if (chartResizeObserver) {
        try { chartResizeObserver.disconnect(); } catch (e) {}
        chartResizeObserver = null;
    }
    if (currentChartInstance) {
        try { currentChartInstance.remove(); } catch (e) {}
        currentChartInstance = null;
    }
    currentChartSeries = null;
    wsInitialPrice = null;
    wsAnchorChartPrice = null;
    isHoveringCrosshair = false;
}

async function openSignalModal(id, customTf = null, expandEngineKey = null) {
    const modal = document.getElementById('signal-modal');
    const modalBox = modal.querySelector('.modal-box');
    const body  = document.getElementById('modal-body');

    stopLiveChartStream();
    modalBox.classList.add('modal-large');
    document.getElementById('modal-title').textContent = 'Loading Live Chart & Signal Details…';
    body.innerHTML = '<div class="empty-state" style="padding:40px;text-align:center"><div class="empty-icon" style="animation:spin 1s linear infinite">⏳</div><div>Connecting to live market feed…</div></div>';
    modal.classList.add('open');

    try {
        const tfQuery = customTf ? `?tf=${encodeURIComponent(customTf)}` : '';
        const res  = await fetch(`/api/signals/${id}/chart/${tfQuery}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const s    = await res.json();

        currentSignalPayload = s;
        currentChartTf = s.timeframe || 'H1';
        renderSignalModalLayout(s);
        if (expandEngineKey) {
            setTimeout(() => toggleEngineDetailPanel(expandEngineKey, true), 120);
        }
    } catch (err) {
        console.error('Modal error:', err);
        body.innerHTML = `<div style="padding:30px;text-align:center;color:var(--sell-color)">Failed to load chart: ${err.message}</div>`;
    }
}

async function openLiveSymbolChart(symbol, tf = 'H1', expandEngineKey = null) {
    const modal = document.getElementById('signal-modal');
    const modalBox = modal.querySelector('.modal-box');
    const body  = document.getElementById('modal-body');

    stopLiveChartStream();
    modalBox.classList.add('modal-large');
    document.getElementById('modal-title').textContent = `Loading ${symbol} Live Chart…`;
    body.innerHTML = '<div class="empty-state" style="padding:40px;text-align:center"><div class="empty-icon" style="animation:spin 1s linear infinite">⏳</div><div>Connecting to live market stream…</div></div>';
    modal.classList.add('open');

    try {
        const res = await fetch(`/api/market/live-chart/?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(tf)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const s = await res.json();
        if (s.signal_id) {
            return openSignalModal(s.signal_id, tf, expandEngineKey);
        }
        currentSignalPayload = s;
        currentChartTf = s.timeframe || tf;
        renderSignalModalLayout(s);
        if (expandEngineKey) {
            setTimeout(() => toggleEngineDetailPanel(expandEngineKey, true), 120);
        }
    } catch (err) {
        console.error('Live symbol chart error:', err);
        body.innerHTML = `<div style="padding:30px;text-align:center;color:var(--sell-color)">Failed to load live chart: ${err.message}</div>`;
    }
}

function renderSignalModalLayout(s) {
    const body = document.getElementById('modal-body');
    const dirBadge = (s.direction || 'BUY').toLowerCase();
    const lastCandle = (s.candles && s.candles.length) ? s.candles[s.candles.length - 1] : null;
    const initPrice = lastCandle ? lastCandle.close : (s.live_price || s.entry_price);
    lastDisplayedPrice = initPrice;

    const statusLabel = s.status === 'HIT_TP' ? '🎯 TP1 HIT — AUTO CLOSED' : (s.status === 'HIT_SL' ? '🛑 SL HIT — CLOSED' : (s.status || 'LIVE'));
    document.getElementById('modal-title').innerHTML = `
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <span>${directionIcon(s.direction)} ${s.symbol} <span style="color:var(--text-muted);font-weight:400">·</span> <span id="modal-header-tf">${s.timeframe}</span></span>
            <span class="badge badge-${dirBadge}">${s.direction}</span>
            <span id="modal-signal-status-badge" class="badge badge-${(s.status||'ACTIVE').toLowerCase()}">${statusLabel}</span>
            <span class="tv-live-pill"><span class="tv-live-dot"></span> LIVE FEED</span>
        </div>
    `;

    const tfButtonsHtml = ['M1', 'M5', 'M15', 'M30', 'H1', 'H2', 'H4', 'D1'].map(tf => {
        const label = TF_LABELS[tf] || (tf === 'D1' ? '1D' : tf);
        const activeCls = tf === currentChartTf ? 'active' : '';
        return `<button class="tv-tf-btn ${activeCls}" data-chart-tf="${tf}" onclick="switchLiveChartTimeframe('${tf}')">${label}</button>`;
    }).join('');

    body.innerHTML = `
        <!-- Trade Levels Banner -->
        <div class="modal-grid" style="grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); margin-bottom: 14px;">
            <div class="modal-field"><label>Live Market Price</label><span class="price-val" id="modal-live-price-top" style="color:#10b981;font-size:16px;font-weight:800;">${formatChartPrice(initPrice, s.symbol)}</span></div>
            <div class="modal-field"><label>Entry Price</label><span class="price-val" style="color:#60a5fa;font-size:16px;">${s.entry_price ?? '—'}</span></div>
            <div class="modal-field"><label>Stop Loss (SL)</label><span class="price-val sl-val" style="font-size:16px;">${s.stop_loss ?? '—'}</span></div>
            <div class="modal-field"><label>Take Profit (TP1 · Auto-Close)</label><span class="price-val tp-val" style="font-size:16px;">${s.take_profit_1 ? `${s.take_profit_1} (100% Close)` : '—'}</span></div>
            <div class="modal-field"><label>Risk : Reward</label><span class="rr-val" style="color:#10b981;font-weight:700">${s.risk_reward || '1.5'}:1</span></div>
            <div class="modal-field"><label>Confidence</label><span style="color:var(--accent-cyan)">${s.confidence_score || 0}%</span></div>
        </div>

        ${s.decision_class ? `
        <!-- Version 2.0 Architectural Gates & Regime Bar -->
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px;padding:10px 14px;background:rgba(255,255,255,0.03);border-radius:8px;border:1px solid rgba(255,255,255,0.08);align-items:center;justify-content:space-between;">
            <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
                <span style="font-size:12px;color:var(--text-muted)">Decision Class:</span>
                <span class="badge badge-${(s.decision_class||'strong').toLowerCase()}" style="font-size:11px">${s.decision_class || 'STRONG'}</span>
                <span style="font-size:12px;color:var(--text-muted)">Regime:</span>
                <span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--accent-cyan);background:rgba(56,189,248,0.1);padding:2px 8px;border-radius:4px">${s.market_regime || 'TRENDING'}</span>
            </div>
            <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
                <span style="font-size:12px;color:var(--text-muted)">Execution Gate:</span>
                <span style="font-size:12px;font-weight:600;color:${s.is_trade_allowed ? '#10b981' : '#ef4444'}">${s.is_trade_allowed ? '✅ Eligible' : '❌ Rejection Filtered'}</span>
                <span style="font-size:12px;color:var(--text-muted)">Position:</span>
                <span style="font-family:'JetBrains Mono',monospace;font-size:12px;color:#fff">${s.recommended_lots || '0.10'} Lots</span>
            </div>
        </div>` : ''}

        ${s.independent_groups && Object.keys(s.independent_groups).length ? `
        <!-- Section 5: Independent Evidence Groups Matrix -->
        <div style="margin-bottom:14px;padding:12px 14px;background:var(--bg-surface);border:1px solid rgba(255,255,255,0.06);border-radius:8px;">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
                <span style="font-size:11px;text-transform:uppercase;color:var(--text-muted);font-weight:700;">
                    🏛️ Section 5 Independent Evidence Groups (3+ Required)
                </span>
                <span style="font-size:11px;color:#60a5fa;font-weight:600;">👆 Click any group for full trade &amp; engine details</span>
            </div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(125px, 1fr));gap:6px;">
                ${renderEvidenceGroups(s.independent_groups || {})}
            </div>
        </div>` : ''}

        <!-- TradingView-Style Live Candlestick Chart with Trade Placement -->
        <div class="chart-card-wrap tv-chart-shell">
            <div class="chart-card-header tv-toolbar-top">
                <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                    <div style="font-size:13px;font-weight:700;display:flex;align-items:center;gap:7px;color:#f8fafc;">
                        <span>📊 Live Price Action &amp; Trade Placement</span>
                    </div>
                    <div id="tv-live-price-box" class="tv-live-price-box up">
                        <span id="tv-live-price-val">${formatChartPrice(initPrice, s.symbol)}</span>
                        <span id="tv-live-price-arrow">▲</span>
                    </div>
                    <span id="tv-live-pnl-badge" class="tv-pnl-pill">—</span>
                    <span id="tv-bar-countdown" class="tv-countdown-pill" title="Time remaining until current candle closes">⏱ --:--</span>
                </div>

                <!-- Mode Switcher: Live Trade Chart vs Official TradingView Widget -->
                <div class="tv-mode-switch">
                    <button id="btn-mode-placement" class="tv-mode-btn ${currentChartMode === 'PLACEMENT' ? 'active' : ''}" onclick="switchChartViewMode('PLACEMENT')">
                        🎯 Trade Placement Live
                    </button>
                    <button id="btn-mode-tv" class="tv-mode-btn ${currentChartMode === 'TRADINGVIEW' ? 'active' : ''}" onclick="switchChartViewMode('TRADINGVIEW')">
                        📈 TradingView Pro
                    </button>
                </div>
            </div>

            <!-- Interactive Timeframe & Indicator Sub-Toolbar -->
            <div class="tv-subtoolbar">
                <div class="tv-tf-group" id="tv-tf-group">
                    ${tfButtonsHtml}
                </div>
                <div class="tv-tools-group" id="tv-placement-tools" style="${currentChartMode === 'TRADINGVIEW' ? 'display:none' : ''}">
                    <button id="btn-toggle-ema" class="tv-tool-btn ${showEmaOverlay ? 'active' : ''}" onclick="toggleChartIndicator('EMA')" title="Toggle EMA 20 & EMA 50">
                        📈 EMA 20/50
                    </button>
                    <button id="btn-toggle-vol" class="tv-tool-btn ${showVolumeOverlay ? 'active' : ''}" onclick="toggleChartIndicator('VOL')" title="Toggle Volume Histogram">
                        📊 Volume
                    </button>
                    <button class="tv-tool-btn" onclick="scrollChartToLive()" title="Scroll to Real-Time Candle">
                        ⏩ Live Bar
                    </button>
                    <button class="tv-tool-btn" onclick="fitChartContent()" title="Fit All Candles & Trade Levels">
                        ⛶ Fit All
                    </button>
                </div>
                <div class="chart-levels-legend">
                    ${s.entry_price ? `<span class="chart-lvl-tag entry">🔵 Entry: ${s.entry_price}</span>` : ''}
                    ${s.stop_loss ? `<span class="chart-lvl-tag sl">🔴 SL: ${s.stop_loss}</span>` : ''}
                    ${s.take_profit_1 ? `<span class="chart-lvl-tag tp">🟢 TP1 (Auto-Close): ${s.take_profit_1}</span>` : ''}
                </div>
            </div>

            <!-- Chart Viewport Container -->
            <div class="tv-viewport-wrapper" style="position:relative;">
                <!-- Floating TradingView-Style Top-Left OHLCV Legend -->
                <div id="tv-ohlc-overlay" class="tv-ohlc-overlay" style="${currentChartMode === 'TRADINGVIEW' ? 'display:none' : ''}">
                    <div class="tv-ohlc-row1">
                        <span class="tv-sym-title">${s.symbol} · ${currentChartTf}</span>
                        <span id="tv-ohlc-values" class="tv-ohlc-nums">Loading OHLC…</span>
                    </div>
                    <div class="tv-ohlc-row2" id="tv-ema-values">
                        <span style="color:#3b82f6">EMA20: —</span>
                        <span style="color:#f59e0b">EMA50: —</span>
                        <span style="color:#94a3b8">Vol: —</span>
                    </div>
                </div>
                <div id="signal-chart-viewport" class="chart-viewport" style="height:430px;"></div>
            </div>
        </div>

        ${s.analysis_summary ? renderInteractiveConfluenceSummary(s.analysis_summary, s) : ''}
        ${s.warnings?.length ? `<div style="padding:10px 14px;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);border-radius:8px;font-size:12px;color:var(--wait-color);margin-bottom:16px">⚠️ ${s.warnings.join(' | ')}</div>` : ''}
        
        <div id="engine-scores-interactive-container">
            ${renderAllEngineScoreRows(s)}
        </div>
    `;

    if (currentChartMode === 'TRADINGVIEW') {
        renderOfficialTradingViewWidget(s);
    } else {
        renderSignalCandleChart(s);
        startLiveChartStream(s);
    }
}

async function switchLiveChartTimeframe(newTf) {
    if (!currentSignalPayload || newTf === currentChartTf) return;
    currentChartTf = newTf;

    document.querySelectorAll('.tv-tf-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.chartTf === newTf);
    });
    const hdrTf = document.getElementById('modal-header-tf');
    if (hdrTf) hdrTf.textContent = newTf;

    if (currentChartMode === 'TRADINGVIEW') {
        currentSignalPayload.timeframe = newTf;
        renderOfficialTradingViewWidget(currentSignalPayload);
        return;
    }

    const container = document.getElementById('signal-chart-viewport');
    if (container) {
        container.style.opacity = '0.5';
    }

    try {
        stopLiveChartStream();
        const url = currentSignalPayload.signal_id
            ? `/api/signals/${currentSignalPayload.signal_id}/chart/?tf=${encodeURIComponent(newTf)}`
            : `/api/market/live-chart/?symbol=${encodeURIComponent(currentSignalPayload.symbol)}&tf=${encodeURIComponent(newTf)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const updated = await res.json();
        currentSignalPayload = updated;
        currentChartTf = updated.timeframe || newTf;
        if (container) container.style.opacity = '1';
        renderSignalCandleChart(updated);
        startLiveChartStream(updated);
        const engineBox = document.getElementById('engine-scores-interactive-container');
        if (engineBox) {
            engineBox.innerHTML = renderAllEngineScoreRows(updated);
        }
    } catch (e) {
        console.error('Timeframe switch error:', e);
        if (container) container.style.opacity = '1';
    }
}

function switchChartViewMode(mode) {
    if (!currentSignalPayload || mode === currentChartMode) return;
    currentChartMode = mode;

    document.getElementById('btn-mode-placement')?.classList.toggle('active', mode === 'PLACEMENT');
    document.getElementById('btn-mode-tv')?.classList.toggle('active', mode === 'TRADINGVIEW');

    const toolsEl = document.getElementById('tv-placement-tools');
    const ohlcEl = document.getElementById('tv-ohlc-overlay');

    if (mode === 'TRADINGVIEW') {
        stopLiveChartStream();
        if (toolsEl) toolsEl.style.display = 'none';
        if (ohlcEl) ohlcEl.style.display = 'none';
        renderOfficialTradingViewWidget(currentSignalPayload);
    } else {
        if (toolsEl) toolsEl.style.display = 'flex';
        if (ohlcEl) ohlcEl.style.display = 'block';
        renderSignalCandleChart(currentSignalPayload);
        startLiveChartStream(currentSignalPayload);
    }
}

function renderOfficialTradingViewWidget(s) {
    const container = document.getElementById('signal-chart-viewport');
    if (!container) return;
    container.innerHTML = '<div id="tv_official_widget_container" style="width:100%;height:100%;"></div>';

    const tvSym = TRADINGVIEW_SYMBOL_MAP[s.symbol] || s.symbol;
    const tvInterval = TV_INTERVAL_MAP[currentChartTf] || '60';

    const initWidget = () => {
        if (!window.TradingView || !document.getElementById('tv_official_widget_container')) return;
        new window.TradingView.widget({
            autosize: true,
            symbol: tvSym,
            interval: tvInterval,
            timezone: 'Asia/Karachi',
            theme: 'dark',
            style: '1',
            locale: 'en',
            toolbar_bg: '#070c18',
            enable_publishing: false,
            hide_top_toolbar: false,
            hide_legend: false,
            save_image: false,
            container_id: 'tv_official_widget_container',
            studies: ['MASimple@tv-basicstudies'],
        });
    };

    if (window.TradingView) {
        initWidget();
    } else {
        const script = document.createElement('script');
        script.src = 'https://s3.tradingview.com/tv.js';
        script.onload = initWidget;
        document.head.appendChild(script);
    }
}

function toggleChartIndicator(type) {
    if (type === 'EMA') {
        showEmaOverlay = !showEmaOverlay;
        document.getElementById('btn-toggle-ema')?.classList.toggle('active', showEmaOverlay);
        if (currentChartSeries?.ema20Series && currentChartSeries?.ema50Series) {
            currentChartSeries.ema20Series.applyOptions({ visible: showEmaOverlay });
            currentChartSeries.ema50Series.applyOptions({ visible: showEmaOverlay });
        }
    } else if (type === 'VOL') {
        showVolumeOverlay = !showVolumeOverlay;
        document.getElementById('btn-toggle-vol')?.classList.toggle('active', showVolumeOverlay);
        if (currentChartSeries?.volumeSeries) {
            currentChartSeries.volumeSeries.applyOptions({ visible: showVolumeOverlay });
        }
    }
}

function scrollChartToLive() {
    if (currentChartInstance) {
        currentChartInstance.timeScale().scrollToRealTime();
    }
}

function fitChartContent() {
    if (currentChartInstance) {
        currentChartInstance.timeScale().fitContent();
    }
}

// ── Render Chart with Trade Points ─────────────────────
function renderSignalCandleChart(s) {
    const container = document.getElementById('signal-chart-viewport');
    if (!container) return;

    if (currentChartInstance) {
        try { currentChartInstance.remove(); } catch(e) {}
        currentChartInstance = null;
    }
    container.innerHTML = '';

    const rawCandles = s.candles || [];
    if (rawCandles.length === 0) {
        container.innerHTML = '<div style="display:grid;place-items:center;height:100%;color:var(--text-muted);font-size:13px;">No historical candles available for this symbol.</div>';
        return;
    }

    // Sort ascending by time & deduplicate
    const sorted = [...rawCandles].sort((a, b) => a.time - b.time);
    const seen = new Set();
    const candleData = [];
    for (const c of sorted) {
        if (!seen.has(c.time)) {
            seen.add(c.time);
            candleData.push({
                time: Number(c.time),
                open: Number(c.open),
                high: Number(c.high),
                low: Number(c.low),
                close: Number(c.close),
                volume: Number(c.volume || 0),
            });
        }
    }
    currentChartData = candleData;

    const isForexLowPrice = candleData[candleData.length - 1].close < 10;
    const pricePrecision = s.symbol?.includes('JPY') ? 3 : (isForexLowPrice ? 5 : 2);
    const minMove = Number((1 / Math.pow(10, pricePrecision)).toFixed(pricePrecision));

    if (window.LightweightCharts) {
        try {
            const chart = LightweightCharts.createChart(container, {
                width: container.clientWidth || 860,
                height: container.clientHeight || 430,
                layout: {
                    background: { color: '#070c18' },
                    textColor: '#94a3b8',
                    fontFamily: "'JetBrains Mono', 'Inter', monospace",
                    fontSize: 11,
                },
                grid: {
                    vertLines: { color: 'rgba(148, 163, 184, 0.06)' },
                    horzLines: { color: 'rgba(148, 163, 184, 0.06)' },
                },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: {
                        color: 'rgba(96, 165, 250, 0.45)',
                        width: 1,
                        style: LightweightCharts.LineStyle.Dashed,
                        labelBackgroundColor: '#1e293b',
                    },
                    horzLine: {
                        color: 'rgba(96, 165, 250, 0.45)',
                        width: 1,
                        style: LightweightCharts.LineStyle.Dashed,
                        labelBackgroundColor: '#1e293b',
                    },
                },
                rightPriceScale: {
                    borderColor: 'rgba(255, 255, 255, 0.12)',
                    scaleMargins: { top: 0.1, bottom: 0.2 },
                    autoScale: true,
                },
                timeScale: {
                    borderColor: 'rgba(255, 255, 255, 0.12)',
                    timeVisible: true,
                    secondsVisible: currentChartTf === 'M1',
                    rightOffset: 7,
                    barSpacing: 9,
                    minBarSpacing: 2,
                },
                handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
                handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
            });

            // 1. Volume Histogram Series (Bottom 18% like TradingView)
            const volumeSeries = chart.addHistogramSeries({
                priceFormat: { type: 'volume' },
                priceScaleId: '',
                visible: showVolumeOverlay,
            });
            volumeSeries.priceScale().applyOptions({
                scaleMargins: { top: 0.82, bottom: 0 },
            });
            volumeSeries.setData(candleData.map(c => ({
                time: c.time,
                value: c.volume || 0,
                color: c.close >= c.open ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)',
            })));

            // 2. EMA 20 & EMA 50 Overlay Series
            const ema20Series = chart.addLineSeries({
                color: '#3b82f6',
                lineWidth: 1.5,
                priceLineVisible: false,
                lastValueVisible: false,
                crosshairMarkerVisible: false,
                visible: showEmaOverlay,
            });
            const ema50Series = chart.addLineSeries({
                color: '#f59e0b',
                lineWidth: 1.5,
                priceLineVisible: false,
                lastValueVisible: false,
                crosshairMarkerVisible: false,
                visible: showEmaOverlay,
            });
            const ema20Data = computeEMASeries(candleData, 20);
            const ema50Data = computeEMASeries(candleData, 50);
            ema20Series.setData(ema20Data);
            ema50Series.setData(ema50Data);

            // 3. Main Candlestick Series (TradingView Emerald & Crimson)
            const candleSeries = chart.addCandlestickSeries({
                upColor: '#089981',
                downColor: '#f23645',
                borderUpColor: '#10b981',
                borderDownColor: '#ef4444',
                wickUpColor: '#10b981',
                wickDownColor: '#ef4444',
                priceLineVisible: true,
                priceLineWidth: 1,
                priceLineStyle: LightweightCharts.LineStyle.Dotted,
                lastValueVisible: true,
                priceFormat: {
                    type: 'price',
                    precision: pricePrecision,
                    minMove: minMove,
                },
            });

            candleSeries.setData(candleData);

            // ── Trade Points & Levels ──────────────────────
            if (s.entry_price) {
                candleSeries.createPriceLine({
                    price: Number(s.entry_price),
                    color: '#38bdf8',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Solid,
                    axisLabelVisible: true,
                    title: `ENTRY: ${s.entry_price}`,
                });
            }

            if (s.stop_loss) {
                candleSeries.createPriceLine({
                    price: Number(s.stop_loss),
                    color: '#ef4444',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: `SL: ${s.stop_loss}`,
                });
            }

            if (s.take_profit_1) {
                candleSeries.createPriceLine({
                    price: Number(s.take_profit_1),
                    color: '#10b981',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: `TP1 (AUTO-CLOSE): ${s.take_profit_1}`,
                });
            }

            // ── Trade Marker at Signal Point ────────────────
            if (s.direction === 'BUY' || s.direction === 'SELL') {
                const signalTs = s.generated_ts || candleData[candleData.length - 1].time;
                let markerCandle = candleData[candleData.length - 1];
                for (let i = candleData.length - 1; i >= 0; i--) {
                    if (candleData[i].time <= signalTs) {
                        markerCandle = candleData[i];
                        break;
                    }
                }

                candleSeries.setMarkers([
                    {
                        time: markerCandle.time,
                        position: s.direction === 'BUY' ? 'belowBar' : 'aboveBar',
                        color: s.direction === 'BUY' ? '#10b981' : '#ef4444',
                        shape: s.direction === 'BUY' ? 'arrowUp' : 'arrowDown',
                        text: `${s.direction} @ ${s.entry_price}`,
                    }
                ]);
            }

            // Position view on recent ~70 candles + right offset like TradingView
            const visibleCount = Math.min(75, candleData.length);
            chart.timeScale().setVisibleLogicalRange({
                from: Math.max(0, candleData.length - visibleCount),
                to: candleData.length + 5,
            });

            currentChartInstance = chart;
            currentChartSeries = { candleSeries, volumeSeries, ema20Series, ema50Series };

            // Initial OHLCV header render
            const lastBar = candleData[candleData.length - 1];
            const prevBar = candleData.length > 1 ? candleData[candleData.length - 2] : lastBar;
            updateTvOhlcOverlay(
                s.symbol,
                lastBar,
                prevBar.close,
                ema20Data[ema20Data.length - 1]?.value,
                ema50Data[ema50Data.length - 1]?.value
            );
            updateLiveTradeTelemetry(s, lastBar.close);

            // Crosshair hover listener (TradingView-style dynamic OHLCV inspection)
            chart.subscribeCrosshairMove(param => {
                if (!param || !param.time || !param.seriesData) {
                    isHoveringCrosshair = false;
                    const latest = currentChartData[currentChartData.length - 1];
                    const prev = currentChartData.length > 1 ? currentChartData[currentChartData.length - 2] : latest;
                    if (latest) {
                        const e20 = computeEMASeries(currentChartData, 20).at(-1)?.value;
                        const e50 = computeEMASeries(currentChartData, 50).at(-1)?.value;
                        updateTvOhlcOverlay(s.symbol, latest, prev.close, e20, e50);
                    }
                    return;
                }
                const bar = param.seriesData.get(candleSeries);
                if (!bar) return;
                isHoveringCrosshair = true;
                const e20 = param.seriesData.get(ema20Series)?.value;
                const e50 = param.seriesData.get(ema50Series)?.value;
                const idx = currentChartData.findIndex(c => c.time === bar.time);
                const prevClose = idx > 0 ? currentChartData[idx - 1].close : bar.open;
                const vol = idx >= 0 ? currentChartData[idx].volume : 0;
                updateTvOhlcOverlay(s.symbol, { ...bar, volume: vol }, prevClose, e20, e50);
            });

            // Handle responsive resize
            chartResizeObserver = new ResizeObserver(() => {
                if (currentChartInstance && container && container.clientWidth > 0) {
                    currentChartInstance.applyOptions({
                        width: container.clientWidth,
                        height: container.clientHeight || 430,
                    });
                }
            });
            chartResizeObserver.observe(container);
            return;
        } catch (e) {
            console.warn('LightweightCharts error, falling back to canvas:', e);
        }
    }

    // ── Self-Contained Canvas Fallback (Works 100% offline) ──
    renderCanvasCandlestickChart(container, candleData, s);
}

// ── Real-Time Live Streaming Engine (WebSocket + Backend Tick + 1s Heartbeat) ──
function startLiveChartStream(s) {
    if (!s || !currentChartData || currentChartData.length === 0) return;

    const symbol = s.symbol;
    const tf = currentChartTf || s.timeframe || 'H1';
    const tfSeconds = s.tf_seconds || TF_SECONDS_MAP[tf] || 3600;

    wsAnchorChartPrice = currentChartData[currentChartData.length - 1].close;
    wsInitialPrice = null;

    // 1. Connect to Binance WebSocket for sub-second real-time trade ticks (delta-anchored to chart price scale)
    const binanceSym = BINANCE_WS_MAP[symbol];
    if (binanceSym && window.WebSocket) {
        try {
            const ws = new WebSocket(`wss://data-stream.binance.vision/ws/${binanceSym}@aggTrade`);
            liveWebSocket = ws;
            ws.onmessage = (evt) => {
                if (!currentChartInstance || !currentChartSeries || currentChartData.length === 0) return;
                try {
                    const msg = JSON.parse(evt.data);
                    const tradePrice = parseFloat(msg.p);
                    if (!Number.isFinite(tradePrice)) return;
                    if (wsInitialPrice === null) {
                        wsInitialPrice = tradePrice;
                        wsAnchorChartPrice = currentChartData[currentChartData.length - 1].close;
                        return;
                    }
                    // Apply proportional relative price movement onto chart's price feed
                    const pctMove = (tradePrice - wsInitialPrice) / wsInitialPrice;
                    const newLivePrice = wsAnchorChartPrice * (1 + pctMove);
                    applyLivePriceTickToChart(newLivePrice, tfSeconds, parseFloat(msg.q) || 0);
                } catch (e) {}
            };
        } catch (e) {
            console.warn('WebSocket fallback to polling:', e);
        }
    }

    // 2. Poll Backend Live Tick Endpoint every 2.5 seconds for authoritative market price, bar sync & TP1 auto-close
    livePollTimer = setInterval(async () => {
        if (!currentChartInstance || !currentSignalPayload || currentChartMode !== 'PLACEMENT') return;
        try {
            const sigParam = currentSignalPayload.signal_id ? `&signal_id=${encodeURIComponent(currentSignalPayload.signal_id)}` : '';
            const res = await fetch(`/api/market/live-tick/?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(tf)}${sigParam}`);
            if (!res.ok) return;
            const tick = await res.json();
            if (!tick || !tick.candle) return;

            const srvCandle = tick.candle;
            wsAnchorChartPrice = Number(srvCandle.close);
            wsInitialPrice = null; // re-anchor WebSocket delta to fresh backend price

            if (tick.signal_status && tick.signal_status !== currentSignalPayload.status) {
                handleSignalAutoClosedOnChart(currentSignalPayload, tick.signal_status);
            }

            syncServerCandlesToChart(tick.recent_candles || [srvCandle], tfSeconds);
        } catch (e) {}
    }, 2500);

    // 3. 1-Second TradingView Heartbeat: Bar Close Countdown + Sub-Tick Price Action Breathing
    liveHeartbeatTimer = setInterval(() => {
        if (!currentChartInstance || !currentChartData.length || currentChartMode !== 'PLACEMENT') return;

        // Update candle close countdown timer
        updateBarCloseCountdown(tfSeconds);

        // Smooth real-time micro-tick movement so candle & price axis stay live every second
        const lastBar = currentChartData[currentChartData.length - 1];
        const prevBar = currentChartData.length > 1 ? currentChartData[currentChartData.length - 2] : lastBar;
        const barRange = Math.max(
            Math.abs(lastBar.high - lastBar.low),
            Math.abs(prevBar.high - prevBar.low),
            lastBar.close * 0.00018
        );
        // Mean-reverting micro-step around anchor price
        const anchor = wsAnchorChartPrice || lastBar.close;
        const drift = (anchor - lastBar.close) * 0.35;
        const microJitter = (Math.random() - 0.495) * (barRange * 0.08);
        const nextPrice = lastBar.close + drift + microJitter;

        applyLivePriceTickToChart(nextPrice, tfSeconds, 0);
    }, 1000);

    updateBarCloseCountdown(tfSeconds);
}

function handleSignalAutoClosedOnChart(s, newStatus) {
    if (!s || s.status === newStatus) return;
    s.status = newStatus;
    const statusBadge = document.getElementById('modal-signal-status-badge');
    if (statusBadge) {
        statusBadge.className = `badge badge-${newStatus.toLowerCase()}`;
        statusBadge.textContent = newStatus === 'HIT_TP'
            ? '🎯 TP1 HIT — AUTO CLOSED'
            : (newStatus === 'HIT_SL' ? '🛑 SL HIT — CLOSED' : newStatus);
    }
    // Refresh dashboard tables & counters immediately so closed trade disappears from Active Signals and increments Won/Lost
    loadActiveSignals();
    loadStats();
    loadAutomationStatus();
}

function syncServerCandlesToChart(recentCandles, tfSeconds) {
    if (!currentChartSeries || !currentChartData.length || !recentCandles?.length) return;
    const { candleSeries, volumeSeries, ema20Series, ema50Series } = currentChartSeries;

    const latestServer = recentCandles[recentCandles.length - 1];
    const lastLocal = currentChartData[currentChartData.length - 1];

    if (latestServer.time > lastLocal.time) {
        // New candle bar opened on server
        const newBar = {
            time: Number(latestServer.time),
            open: lastLocal.close,
            high: Math.max(lastLocal.close, Number(latestServer.high)),
            low: Math.min(lastLocal.close, Number(latestServer.low)),
            close: Number(latestServer.close),
            volume: Number(latestServer.volume || 0),
        };
        currentChartData.push(newBar);
        candleSeries.update(newBar);
        volumeSeries.update({
            time: newBar.time,
            value: newBar.volume,
            color: newBar.close >= newBar.open ? 'rgba(16, 185, 129, 0.28)' : 'rgba(239, 68, 68, 0.28)',
        });
    } else {
        // Update current active candle
        lastLocal.close = Number(latestServer.close);
        lastLocal.high = Math.max(lastLocal.high, Number(latestServer.high), lastLocal.close);
        lastLocal.low = Math.min(lastLocal.low, Number(latestServer.low), lastLocal.close);
        if (latestServer.volume > lastLocal.volume) {
            lastLocal.volume = Number(latestServer.volume);
        }
        candleSeries.update(lastLocal);
        volumeSeries.update({
            time: lastLocal.time,
            value: lastLocal.volume,
            color: lastLocal.close >= lastLocal.open ? 'rgba(16, 185, 129, 0.28)' : 'rgba(239, 68, 68, 0.28)',
        });
    }

    const e20 = computeEMASeries(currentChartData, 20).at(-1);
    const e50 = computeEMASeries(currentChartData, 50).at(-1);
    if (e20) ema20Series.update(e20);
    if (e50) ema50Series.update(e50);

    const activeBar = currentChartData[currentChartData.length - 1];
    const prevBar = currentChartData.length > 1 ? currentChartData[currentChartData.length - 2] : activeBar;
    if (!isHoveringCrosshair && currentSignalPayload) {
        updateTvOhlcOverlay(currentSignalPayload.symbol, activeBar, prevBar.close, e20?.value, e50?.value);
    }
    if (currentSignalPayload) {
        updateLiveTradeTelemetry(currentSignalPayload, activeBar.close);
    }
}

function applyLivePriceTickToChart(rawPrice, tfSeconds, addedVolume = 0) {
    if (!currentChartSeries || !currentChartData.length || !currentSignalPayload) return;
    const { candleSeries, volumeSeries, ema20Series, ema50Series } = currentChartSeries;

    const sym = currentSignalPayload.symbol || '';
    const isLowP = rawPrice < 10;
    const decimals = sym.includes('JPY') ? 3 : (isLowP ? 5 : 2);
    const price = Number(rawPrice.toFixed(decimals));

    const nowSec = Math.floor(Date.now() / 1000);
    const currentBucket = Math.floor(nowSec / tfSeconds) * tfSeconds;
    let lastBar = currentChartData[currentChartData.length - 1];

    // Roll over to a new bar if current timeframe bucket advanced beyond the last candle's bucket
    if (currentBucket > lastBar.time && (currentBucket - lastBar.time) <= tfSeconds * 4) {
        const newBar = {
            time: currentBucket,
            open: lastBar.close,
            high: Math.max(lastBar.close, price),
            low: Math.min(lastBar.close, price),
            close: price,
            volume: addedVolume > 0 ? addedVolume : Math.max(1, (lastBar.volume || 100) * 0.02),
        };
        currentChartData.push(newBar);
        lastBar = newBar;
    } else {
        lastBar.close = price;
        if (price > lastBar.high) lastBar.high = price;
        if (price < lastBar.low) lastBar.low = price;
        lastBar.volume = (lastBar.volume || 0) + (addedVolume > 0 ? addedVolume : Math.max(0.1, (lastBar.volume || 50) * 0.002));
    }

    const isBullish = lastBar.close >= lastBar.open;
    candleSeries.applyOptions({
        priceLineColor: isBullish ? '#10b981' : '#ef4444',
    });

    candleSeries.update({
        time: lastBar.time,
        open: lastBar.open,
        high: lastBar.high,
        low: lastBar.low,
        close: lastBar.close,
    });

    volumeSeries.update({
        time: lastBar.time,
        value: lastBar.volume,
        color: isBullish ? 'rgba(16, 185, 129, 0.28)' : 'rgba(239, 68, 68, 0.28)',
    });

    const e20 = computeEMASeries(currentChartData, 20).at(-1);
    const e50 = computeEMASeries(currentChartData, 50).at(-1);
    if (e20) ema20Series.update(e20);
    if (e50) ema50Series.update(e50);

    const prevBar = currentChartData.length > 1 ? currentChartData[currentChartData.length - 2] : lastBar;
    if (!isHoveringCrosshair) {
        updateTvOhlcOverlay(sym, lastBar, prevBar.close, e20?.value, e50?.value);
    }
    updateLiveTradeTelemetry(currentSignalPayload, price);
}

function updateTvOhlcOverlay(symbol, bar, prevClose, ema20Val, ema50Val) {
    const valEl = document.getElementById('tv-ohlc-values');
    const emaEl = document.getElementById('tv-ema-values');
    if (!valEl || !bar) return;

    const isUp = bar.close >= bar.open;
    const col = isUp ? '#10b981' : '#ef4444';
    const base = prevClose || bar.open || 1;
    const diff = bar.close - base;
    const pct = (diff / base) * 100;
    const sign = diff >= 0 ? '+' : '';

    valEl.innerHTML = `
        <span>O <b style="color:${col}">${formatChartPrice(bar.open, symbol)}</b></span>
        <span>H <b style="color:${col}">${formatChartPrice(bar.high, symbol)}</b></span>
        <span>L <b style="color:${col}">${formatChartPrice(bar.low, symbol)}</b></span>
        <span>C <b style="color:${col}">${formatChartPrice(bar.close, symbol)}</b></span>
        <span style="color:${col};font-weight:700">${sign}${formatChartPrice(diff, symbol)} (${sign}${pct.toFixed(2)}%)</span>
    `;

    if (emaEl) {
        emaEl.innerHTML = `
            <span style="color:#60a5fa">EMA 20: <b>${ema20Val ? formatChartPrice(ema20Val, symbol) : '—'}</b></span>
            <span style="color:#fbbf24">EMA 50: <b>${ema50Val ? formatChartPrice(ema50Val, symbol) : '—'}</b></span>
            <span style="color:#94a3b8">Vol: <b>${formatVolumeCompact(bar.volume)}</b></span>
        `;
    }
}

function updateLiveTradeTelemetry(s, livePrice) {
    const priceBox = document.getElementById('tv-live-price-box');
    const priceVal = document.getElementById('tv-live-price-val');
    const priceArr = document.getElementById('tv-live-price-arrow');
    const topPrice = document.getElementById('modal-live-price-top');
    const pnlBadge = document.getElementById('tv-live-pnl-badge');

    const formatted = formatChartPrice(livePrice, s.symbol);
    const isTickUp = lastDisplayedPrice === null ? true : livePrice >= lastDisplayedPrice;
    lastDisplayedPrice = livePrice;

    if (priceVal) priceVal.textContent = formatted;
    if (priceArr) priceArr.textContent = isTickUp ? '▲' : '▼';
    if (priceBox) {
        priceBox.classList.toggle('up', isTickUp);
        priceBox.classList.toggle('down', !isTickUp);
    }
    if (topPrice) {
        topPrice.textContent = formatted;
        topPrice.style.color = isTickUp ? '#10b981' : '#ef4444';
    }

    // Immediate client-side detection if live price crosses TP1 or SL while ACTIVE
    if (s.status === 'ACTIVE' && s.take_profit_1 && s.stop_loss && (s.direction === 'BUY' || s.direction === 'SELL')) {
        const tp1 = Number(s.take_profit_1);
        const sl = Number(s.stop_loss);
        if (s.direction === 'BUY') {
            if (livePrice >= tp1) handleSignalAutoClosedOnChart(s, 'HIT_TP');
            else if (livePrice <= sl) handleSignalAutoClosedOnChart(s, 'HIT_SL');
        } else if (s.direction === 'SELL') {
            if (livePrice <= tp1) handleSignalAutoClosedOnChart(s, 'HIT_TP');
            else if (livePrice >= sl) handleSignalAutoClosedOnChart(s, 'HIT_SL');
        }
    }

    if (pnlBadge && s.entry_price && (s.direction === 'BUY' || s.direction === 'SELL')) {
        if (s.status === 'HIT_TP') {
            pnlBadge.style.background = 'rgba(16, 185, 129, 0.22)';
            pnlBadge.style.color = '#34d399';
            pnlBadge.style.borderColor = 'rgba(16, 185, 129, 0.5)';
            pnlBadge.textContent = `🎯 TP1 HIT! Trade Auto-Closed @ ${s.take_profit_1}`;
            return;
        }
        if (s.status === 'HIT_SL') {
            pnlBadge.style.background = 'rgba(239, 68, 68, 0.22)';
            pnlBadge.style.color = '#f87171';
            pnlBadge.style.borderColor = 'rgba(239, 68, 68, 0.5)';
            pnlBadge.textContent = `🛑 SL HIT! Trade Closed @ ${s.stop_loss}`;
            return;
        }
        const entry = Number(s.entry_price);
        const rawDiff = s.direction === 'BUY' ? (livePrice - entry) : (entry - livePrice);
        const pctDiff = (rawDiff / entry) * 100;
        const inProfit = rawDiff >= 0;
        const sign = rawDiff >= 0 ? '+' : '';
        pnlBadge.style.background = inProfit ? 'rgba(16, 185, 129, 0.16)' : 'rgba(239, 68, 68, 0.16)';
        pnlBadge.style.color = inProfit ? '#34d399' : '#f87171';
        pnlBadge.style.borderColor = inProfit ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)';
        pnlBadge.textContent = `${inProfit ? '🟢' : '🔴'} ${sign}${formatChartPrice(rawDiff, s.symbol)} (${sign}${pctDiff.toFixed(2)}%) vs Entry`;
    }
}

function updateBarCloseCountdown(tfSeconds) {
    const el = document.getElementById('tv-bar-countdown');
    if (!el) return;
    const nowSec = Math.floor(Date.now() / 1000);
    const rem = tfSeconds - (nowSec % tfSeconds);
    const hrs = Math.floor(rem / 3600);
    const mins = Math.floor((rem % 3600) / 60);
    const secs = rem % 60;
    const pad = n => String(n).padStart(2, '0');
    el.textContent = hrs > 0
        ? `⏱ Next Bar: ${pad(hrs)}:${pad(mins)}:${pad(secs)}`
        : `⏱ Next Bar: ${pad(mins)}:${pad(secs)}`;
}

// ── Built-in Canvas Candlestick Chart ───────────────────
function renderCanvasCandlestickChart(container, candles, s) {
    container.innerHTML = '';
    const canvas = document.createElement('canvas');
    container.appendChild(canvas);

    const dpr = window.devicePixelRatio || 1;
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 430;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const padLeft = 10, padRight = 80, padTop = 30, padBottom = 30;
    const plotW = w - padLeft - padRight;
    const plotH = h - padTop - padBottom;

    // Determine min/max price including entry, SL, TP
    const extraPrices = [s.stop_loss, s.entry_price, s.take_profit_1].filter(p => Number.isFinite(Number(p))).map(Number);
    let minP = Math.min(...candles.map(c => c.low), ...extraPrices);
    let maxP = Math.max(...candles.map(c => c.high), ...extraPrices);
    const range = (maxP - minP) || 1;
    minP -= range * 0.05;
    maxP += range * 0.05;

    const priceToY = (p) => padTop + (maxP - p) / (maxP - minP) * plotH;

    // Draw background
    ctx.fillStyle = '#070c18';
    ctx.fillRect(0, 0, w, h);

    // Draw price grid lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#64748b';
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.textAlign = 'left';

    const steps = 6;
    for (let i = 0; i <= steps; i++) {
        const p = minP + (maxP - minP) * (i / steps);
        const y = priceToY(p);
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(w - padRight, y);
        ctx.stroke();
        ctx.fillText(p >= 100 ? p.toFixed(2) : p.toFixed(4), w - padRight + 6, y + 3);
    }

    // Draw candlesticks
    const count = candles.length;
    const candleW = Math.max(2, Math.min(14, (plotW / count) * 0.7));
    const stepX = plotW / count;

    candles.forEach((c, i) => {
        const x = padLeft + i * stepX + stepX / 2;
        const openY = priceToY(c.open);
        const closeY = priceToY(c.close);
        const highY = priceToY(c.high);
        const lowY = priceToY(c.low);
        const isUp = c.close >= c.open;

        ctx.strokeStyle = isUp ? '#10b981' : '#ef4444';
        ctx.fillStyle = isUp ? '#10b981' : '#ef4444';

        // Wick
        ctx.beginPath();
        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);
        ctx.stroke();

        // Body
        const topY = Math.min(openY, closeY);
        const bodyH = Math.max(1, Math.abs(closeY - openY));
        ctx.fillRect(x - candleW / 2, topY, candleW, bodyH);
    });

    // ── Helper to draw level line ─────────────────────────
    function drawLevel(price, label, color, dashed = true) {
        if (!price) return;
        const y = priceToY(price);
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        if (dashed) ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(w - padRight, y);
        ctx.stroke();

        // Pill badge on right
        ctx.setLineDash([]);
        ctx.fillStyle = color;
        const tagText = `${label}: ${price}`;
        ctx.font = 'bold 10px JetBrains Mono, monospace';
        const tagW = ctx.measureText(tagText).width + 8;
        ctx.fillRect(w - padRight, y - 9, tagW, 18);
        ctx.fillStyle = '#000';
        ctx.fillText(tagText, w - padRight + 4, y + 4);
        ctx.restore();
    }

    // Draw Entry, SL, TP1 levels (single 100% auto-close TP1 target)
    drawLevel(s.entry_price, 'ENTRY', '#38bdf8', false);
    drawLevel(s.stop_loss, 'SL', '#ef4444', true);
    drawLevel(s.take_profit_1, 'TP1', '#10b981', true);

    // ── Draw Trade Execution Marker ───────────────────────
    if (s.entry_price && (s.direction === 'BUY' || s.direction === 'SELL')) {
        const lastX = padLeft + (count - 1) * stepX + stepX / 2;
        const entryY = priceToY(s.entry_price);
        const isBuy = s.direction === 'BUY';

        ctx.save();
        ctx.fillStyle = isBuy ? '#10b981' : '#ef4444';
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;

        const arrowY = isBuy ? entryY + 12 : entryY - 12;
        ctx.beginPath();
        ctx.moveTo(lastX, entryY);
        ctx.lineTo(lastX - 6, arrowY);
        ctx.lineTo(lastX + 6, arrowY);
        ctx.closePath();
        ctx.fill();

        const markerText = `${s.direction} @ ${s.entry_price}`;
        ctx.font = 'bold 11px JetBrains Mono, monospace';
        const mw = ctx.measureText(markerText).width + 10;
        const boxX = Math.min(w - padRight - mw - 5, Math.max(padLeft, lastX - mw / 2));
        const boxY = isBuy ? arrowY + 4 : arrowY - 20;

        ctx.fillStyle = isBuy ? '#10b981' : '#ef4444';
        ctx.fillRect(boxX, boxY, mw, 18);
        ctx.fillStyle = '#ffffff';
        ctx.fillText(markerText, boxX + 5, boxY + 13);
        ctx.restore();
    }
}

function renderAllEngineScoreRows(s) {
    if (!s || (s.technical_score === undefined && !s.engine_details)) return '';
    const intermarketScore = s.intermarket_score !== undefined
        ? s.intermarket_score
        : (s.engine_details?.intermarket?.score ?? 50);

    return `
        <div class="engine-scores" style="margin-top:14px">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:10px;">
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                    <h4 style="font-size:12px;text-transform:uppercase;color:var(--text-muted);margin:0;">Engine Confidence Scores</h4>
                    <span class="engine-click-hint-pill">👆 Click any engine row to open full Trade &amp; Indicator Details</span>
                </div>
                <button type="button" class="engine-expand-all-btn" id="btn-expand-all-engines" onclick="toggleAllEngineDetailPanels()">
                    📂 Expand All Trade Details
                </button>
            </div>
            ${scoreRow('📐 Technical Engine',         s.technical_score,     15, 'technical',     s)}
            ${scoreRow('💡 SMC / ICT Engine',         s.smc_score,           20, 'smc_ict',       s)}
            ${scoreRow('🕯️ Price Action Engine',     s.price_action_score,  15, 'price_action',  s)}
            ${scoreRow('🌍 Macro Environment',        s.macro_score,         15, 'macro',         s)}
            ${scoreRow('📰 News Sentiment',           s.news_score,          15, 'news',          s)}
            ${scoreRow('🏦 Institutional Flow',       s.institutional_score, 10, 'institutional', s)}
            ${scoreRow('🔗 Intermarket & Volatility', intermarketScore,       5, 'intermarket',   s)}
            ${scoreRow('🤖 AI / ML Prediction',       s.ai_ml_score,         10, 'ai_ml',         s)}
        </div>`;
}

function mapRawEngineNameToKey(rawName) {
    const n = String(rawName || '').toLowerCase().trim();
    if (n.includes('tech') || n.includes('trend') || n.includes('momentum')) return 'technical';
    if (n.includes('smc') || n.includes('ict') || n.includes('smart')) return 'smc_ict';
    if (n.includes('price') || n === 'pa') return 'price_action';
    if (n.includes('macro') || n.includes('fund')) return 'macro';
    if (n.includes('news') || n.includes('sent')) return 'news';
    if (n.includes('inst') || n.includes('cot')) return 'institutional';
    if (n.includes('inter') || n.includes('vol')) return 'intermarket';
    if (n.includes('ai') || n.includes('ml')) return 'ai_ml';
    return 'technical';
}

function renderInteractiveConfluenceSummary(summaryText, s) {
    if (!summaryText) return '';
    const lines = String(summaryText).split('\n').map(l => l.trim()).filter(Boolean);
    const ENGINE_PRETTY = {
        technical:     '📐 Technical Engine',
        smc_ict:       '💡 SMC / ICT Engine',
        price_action:  '🕯️ Price Action Engine',
        macro:         '🌍 Macro Environment',
        news:          '📰 News Sentiment',
        institutional: '🏦 Institutional Flow',
        intermarket:   '🔗 Intermarket & Volatility',
        ai_ml:         '🤖 AI / ML Prediction',
    };

    const rowsHtml = lines.map(line => {
        const m = line.match(/^\[([A-Z]+)\]\s+([a-zA-Z0-9_]+)\s+Score=(\d+(?:\.\d+)?)\s*\|\s*(.*)$/i);
        if (m) {
            const verdict = m[1].toUpperCase();
            const rawEng = m[2];
            const scoreVal = m[3];
            const bodyText = m[4];
            const engKey = mapRawEngineNameToKey(rawEng);
            const prettyName = ENGINE_PRETTY[engKey] || rawEng;
            const vCol = verdict === 'BUY' ? '#10b981' : (verdict === 'SELL' ? '#ef4444' : '#94a3b8');
            const vBg  = verdict === 'BUY' ? 'rgba(16,185,129,0.14)' : (verdict === 'SELL' ? 'rgba(239,68,68,0.14)' : 'rgba(148,163,184,0.12)');
            return `
                <div class="confluence-line-item" onclick="toggleEngineDetailPanel('${engKey}', true)" title="Click to open ${prettyName} full trade details">
                    <div class="confluence-line-left">
                        <span class="confluence-verdict-pill" style="color:${vCol};background:${vBg};border:1px solid ${vCol}44;">${verdict}</span>
                        <span class="confluence-eng-title">${prettyName}</span>
                        <span class="confluence-score-chip">Score: ${scoreVal}/100</span>
                    </div>
                    <div class="confluence-line-text">${bodyText}</div>
                    <span class="confluence-open-link">🔍 Full Details ▸</span>
                </div>`;
        }
        return `<div class="confluence-line-plain">${line}</div>`;
    }).join('');

    return `
        <div class="confluence-summary-box">
            <div class="confluence-summary-header">
                <div>
                    <strong style="color:#f8fafc;font-size:13px;">🧠 Engine Confluence Analysis</strong>
                    <span style="font-size:11px;color:#60a5fa;margin-left:8px;">(Click any line to inspect full trade &amp; indicator breakdown)</span>
                </div>
                <button type="button" class="engine-expand-all-btn" onclick="toggleAllEngineDetailPanels()">
                    📂 Open All Details
                </button>
            </div>
            <div class="confluence-lines-list">
                ${rowsHtml}
            </div>
        </div>`;
}

function scoreRow(label, score, weight, engineKey = 'technical', s = null) {
    const payload = s || currentSignalPayload || {};
    const detail = (payload.engine_details && payload.engine_details[engineKey]) || {};
    const pct = Math.min(100, parseFloat(score !== undefined ? score : detail.score) || 0);
    const dir = String(detail.direction || (pct >= 58 ? 'BUY' : (pct <= 42 ? 'SELL' : 'NEUTRAL'))).toUpperCase();
    const dirCol = dir === 'BUY' ? '#10b981' : (dir === 'SELL' ? '#ef4444' : '#94a3b8');
    const dirBg  = dir === 'BUY' ? 'rgba(16,185,129,0.14)' : (dir === 'SELL' ? 'rgba(239,68,68,0.14)' : 'rgba(148,163,184,0.12)');
    const barFillColor = dir === 'BUY'
        ? 'linear-gradient(90deg, #059669, #10b981)'
        : (dir === 'SELL' ? 'linear-gradient(90deg, #dc2626, #ef4444)' : 'linear-gradient(90deg, #3b82f6, #60a5fa)');

    return `
        <div class="engine-score-wrapper" id="engine-wrap-${engineKey}">
            <div class="score-row clickable-score-row" id="score-row-${engineKey}" onclick="toggleEngineDetailPanel('${engineKey}')" role="button" tabindex="0" aria-expanded="false">
                <div class="score-label-group">
                    <span class="score-label">${label} <span style="color:var(--text-muted);font-weight:500;">(${weight}%)</span></span>
                    <span class="engine-row-verdict" style="color:${dirCol};background:${dirBg};border:1px solid ${dirCol}40;">${dir}</span>
                </div>
                <div class="score-bar"><div class="score-bar-fill" style="width:${pct}%;background:${barFillColor}"></div></div>
                <div class="score-right-group">
                    <span class="score-num" style="color:${dirCol}">${pct.toFixed(0)}</span>
                    <span class="score-expand-pill" id="score-expand-icon-${engineKey}">🔍 Details <span class="chev">▾</span></span>
                </div>
            </div>
            <div class="engine-detail-drawer" id="engine-detail-drawer-${engineKey}">
                ${renderEngineDetailDrawer(engineKey, label, pct, weight, payload)}
            </div>
        </div>`;
}

function renderEngineDetailDrawer(engineKey, label, pct, weight, s) {
    const detail = (s?.engine_details && s.engine_details[engineKey]) || {};
    const dir = String(detail.direction || (pct >= 58 ? 'BUY' : (pct <= 42 ? 'SELL' : 'NEUTRAL'))).toUpperCase();
    const dirCol = dir === 'BUY' ? '#10b981' : (dir === 'SELL' ? '#ef4444' : '#94a3b8');
    const tradeDir = String(s?.direction || 'BUY').toUpperCase();
    const tradeCol = tradeDir === 'BUY' ? '#10b981' : (tradeDir === 'SELL' ? '#ef4444' : '#f59e0b');

    const lastCandle = (s?.candles && s.candles.length) ? s.candles[s.candles.length - 1] : null;
    const liveP = lastCandle ? lastCandle.close : (s?.live_price || s?.entry_price || 0);
    const entryP = Number(s?.entry_price || 0);
    const slP    = Number(s?.stop_loss || 0);
    const tp1P   = Number(s?.take_profit_1 || 0);

    const slDist  = (entryP && slP) ? Math.abs(entryP - slP) : 0;
    const slPct   = (entryP && slDist) ? ((slDist / entryP) * 100).toFixed(2) : '0.00';
    const tp1Dist = (entryP && tp1P) ? Math.abs(tp1P - entryP) : 0;
    const tp1Pct  = (entryP && tp1Dist) ? ((tp1Dist / entryP) * 100).toFixed(2) : '0.00';

    // Live floating distance from Entry
    let liveDiffText = '—';
    let liveDiffCol  = '#94a3b8';
    if (entryP && liveP && (tradeDir === 'BUY' || tradeDir === 'SELL')) {
        const diff = tradeDir === 'BUY' ? (liveP - entryP) : (entryP - liveP);
        const diffPct = ((diff / entryP) * 100).toFixed(2);
        const sign = diff >= 0 ? '+' : '';
        liveDiffCol = diff >= 0 ? '#10b981' : '#ef4444';
        liveDiffText = `${sign}${formatChartPrice(diff, s.symbol)} (${sign}${diffPct}%)`;
    }

    // Auto-Trade Linked Execution block
    const at = s?.auto_trade;
    const autoTradeHtml = at ? `
        <div class="engine-autotrade-banner">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
                <span style="font-size:11px;font-weight:700;color:#60a5fa;text-transform:uppercase;">🤖 Linked Auto-Trader Order Execution</span>
                <span class="badge badge-${at.status === 'OPEN' ? 'active' : (at.status === 'CLOSED_TP' ? 'buy' : 'sell')}" style="font-size:10px;">${at.status}</span>
            </div>
            <div class="engine-trade-specs-grid">
                <div class="engine-spec-cell"><span>Order Ticket</span><b>#${at.order_id || 'SIM'}</b></div>
                <div class="engine-spec-cell"><span>Trading Account</span><b>${at.account_name} (${at.broker} #${at.login_id})</b></div>
                <div class="engine-spec-cell"><span>Executed Fill Price</span><b style="color:#60a5fa">${at.executed_price ?? s.entry_price}</b></div>
                <div class="engine-spec-cell"><span>Executed Volume</span><b>${at.lot_size} Lots</b></div>
                <div class="engine-spec-cell"><span>Stop Loss / TP1 (Auto-Close)</span><b><span style="color:#ef4444">${at.stop_loss ?? s.stop_loss}</span> / <span style="color:#10b981">${at.take_profit ?? s.take_profit_1}</span></b></div>
                <div class="engine-spec-cell"><span>Realized / Order PnL</span><b style="color:${Number(at.profit_loss) >= 0 ? '#10b981' : '#ef4444'}">${Number(at.profit_loss) >= 0 ? '+' : ''}$${Number(at.profit_loss || 0).toFixed(2)}</b></div>
            </div>
        </div>
    ` : '';

    // Quantitative Metrics Grid
    const metrics = Array.isArray(detail.metrics) ? detail.metrics : [];
    const metricsHtml = metrics.length ? `
        <div class="engine-drawer-section-title">📊 ${detail.title || label} — Live Quantitative Indicators</div>
        <div class="engine-metrics-grid">
            ${metrics.map(m => {
                const st = m.status || 'neutral';
                return `
                    <div class="engine-metric-card ${st}">
                        <div class="engine-metric-label">${m.label}</div>
                        <div class="engine-metric-val">${m.value}</div>
                    </div>`;
            }).join('')}
        </div>
    ` : '';

    // Reasoning / Triggered Signals Breakdown
    const reasons = Array.isArray(detail.reasoning) && detail.reasoning.length
        ? detail.reasoning
        : ['Multi-factor confluence evaluated on current timeframe candles.'];
    const reasonsHtml = reasons.map(r => {
        const txt = String(r);
        const isBull = /bull|buy|above|support|discount|golden|oversold|positive|accumul|inflow|up/i.test(txt) && !/bear|sell|below/i.test(txt);
        const isBear = /bear|sell|below|resistance|premium|death|overbought|negative|distrib|outflow|down/i.test(txt);
        const dotCol = isBull ? '#10b981' : (isBear ? '#ef4444' : '#38bdf8');
        const icon   = isBull ? '🟢' : (isBear ? '🔴' : '🔹');
        return `
            <div class="engine-reason-item" style="border-left: 3px solid ${dotCol};">
                <span class="engine-reason-icon">${icon}</span>
                <span class="engine-reason-text">${txt}</span>
            </div>`;
    }).join('');

    const entryZone = detail.entry_zone ? formatChartPrice(detail.entry_zone, s?.symbol) : (s?.entry_price ?? 'Market');
    const slZone    = detail.sl_zone    ? formatChartPrice(detail.sl_zone, s?.symbol)    : (s?.stop_loss ?? 'Structure SL');
    const tpZone    = detail.tp_zone    ? formatChartPrice(detail.tp_zone, s?.symbol)    : (s?.take_profit_1 ? `${s.take_profit_1} (100% Auto-Close)` : 'Target TP1');

    return `
        <div class="engine-drawer-inner">
            <!-- 1. Complete Trade Execution & Position Details -->
            <div class="engine-drawer-top-bar">
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                    <span style="font-size:13px;font-weight:800;color:#f8fafc;">${detail.title || label}</span>
                    <span class="badge" style="background:${dirCol}22;color:${dirCol};border:1px solid ${dirCol}55;font-size:10.5px;">Engine Verdict: ${dir} (${pct.toFixed(1)}/100)</span>
                    <span style="font-size:11px;color:var(--text-muted);">Weight: <b>${weight}%</b></span>
                </div>
                <div style="font-size:11px;color:#94a3b8;">
                    ${detail.subtitle || 'Real-time multi-factor trade telemetry'}
                </div>
            </div>

            <div class="engine-drawer-section-title">🎯 Full Trade Execution &amp; Risk Profile (${s?.symbol || ''} · ${s?.timeframe || 'H1'})</div>
            <div class="engine-trade-specs-grid">
                <div class="engine-spec-cell">
                    <span>Instrument &amp; Timeframe</span>
                    <b>${s?.symbol || '—'} · ${s?.timeframe || 'H1'} ${s?.instrument_name ? `(${s.instrument_name})` : ''}</b>
                </div>
                <div class="engine-spec-cell">
                    <span>Trade Direction &amp; Status</span>
                    <b style="color:${tradeCol}">${tradeDir} (${s?.strength || 'STRONG'}) · ${s?.status === 'HIT_TP' ? '🎯 TP1 Auto-Closed' : (s?.status || 'ACTIVE')}</b>
                </div>
                <div class="engine-spec-cell">
                    <span>Entry Price &amp; Live Price</span>
                    <b><span style="color:#60a5fa">${s?.entry_price ?? '—'}</span> <span style="color:var(--text-muted)">→</span> <span style="color:#f8fafc">${formatChartPrice(liveP, s?.symbol)}</span></b>
                </div>
                <div class="engine-spec-cell">
                    <span>Stop Loss (SL) &amp; Risk</span>
                    <b style="color:#ef4444">${s?.stop_loss ?? '—'} ${slDist ? `(-${formatChartPrice(slDist, s?.symbol)} / ${slPct}%)` : ''}</b>
                </div>
                <div class="engine-spec-cell">
                    <span>TP1 (100% Auto-Close)</span>
                    <b style="color:#10b981">${s?.take_profit_1 ?? '—'} ${tp1Dist ? `(+${formatChartPrice(tp1Dist, s?.symbol)} / +${tp1Pct}%)` : ''}</b>
                </div>
                <div class="engine-spec-cell">
                    <span>R:R · Lot Size · Floating</span>
                    <b><span style="color:#10b981">1:${s?.risk_reward || '1.5'}</span> · ${s?.recommended_lots || '0.10'} Lots · <span style="color:${liveDiffCol}">${liveDiffText}</span></b>
                </div>
                <div class="engine-spec-cell">
                    <span>Engine Suggested Entry / SL / TP</span>
                    <b><span style="color:#60a5fa">E: ${entryZone}</span> · <span style="color:#ef4444">SL: ${slZone}</span> · <span style="color:#10b981">TP: ${tpZone}</span></b>
                </div>
                <div class="engine-spec-cell">
                    <span>Regime · Gate · Signal Time</span>
                    <b>${s?.market_regime || 'TRENDING'} · ${s?.is_trade_allowed !== false ? '✅ Allowed' : '❌ Locked'} · ${s?.generated_at ? formatTime(s.generated_at) : 'Live'}</b>
                </div>
            </div>

            ${autoTradeHtml}
            ${metricsHtml}

            <div class="engine-drawer-section-title">📋 Step-by-Step Engine Signals &amp; Confluence Reasoning (${reasons.length})</div>
            <div class="engine-reasons-list">
                ${reasonsHtml}
            </div>
        </div>`;
}

function toggleEngineDetailPanel(engineKey, scrollIntoViewIfOpen = false) {
    const drawer = document.getElementById(`engine-detail-drawer-${engineKey}`);
    const row    = document.getElementById(`score-row-${engineKey}`);
    const icon   = document.getElementById(`score-expand-icon-${engineKey}`);
    if (!drawer) return;

    const isOpening = scrollIntoViewIfOpen ? true : !drawer.classList.contains('open');
    drawer.classList.toggle('open', isOpening);
    if (row) {
        row.classList.toggle('expanded', isOpening);
        row.setAttribute('aria-expanded', isOpening ? 'true' : 'false');
    }
    if (icon) {
        icon.innerHTML = isOpening ? '🔼 Hide Details <span class="chev">▴</span>' : '🔍 Details <span class="chev">▾</span>';
    }

    if (isOpening && scrollIntoViewIfOpen) {
        const wrap = document.getElementById(`engine-wrap-${engineKey}`) || drawer;
        wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function toggleAllEngineDetailPanels() {
    const drawers = Array.from(document.querySelectorAll('.engine-detail-drawer'));
    if (!drawers.length) return;
    const anyClosed = drawers.some(d => !d.classList.contains('open'));
    const keys = ['technical', 'smc_ict', 'price_action', 'macro', 'news', 'institutional', 'intermarket', 'ai_ml'];
    keys.forEach(k => {
        const d = document.getElementById(`engine-detail-drawer-${k}`);
        const r = document.getElementById(`score-row-${k}`);
        const ic = document.getElementById(`score-expand-icon-${k}`);
        if (d) d.classList.toggle('open', anyClosed);
        if (r) {
            r.classList.toggle('expanded', anyClosed);
            r.setAttribute('aria-expanded', anyClosed ? 'true' : 'false');
        }
        if (ic) {
            ic.innerHTML = anyClosed ? '🔼 Hide Details <span class="chev">▴</span>' : '🔍 Details <span class="chev">▾</span>';
        }
    });
    const btn = document.getElementById('btn-expand-all-engines');
    if (btn) {
        btn.innerHTML = anyClosed ? '📁 Collapse All Trade Details' : '📂 Expand All Trade Details';
    }
}

function jumpToEngineFromEvidenceGroup(groupName) {
    const key = mapRawEngineNameToKey(groupName);
    toggleEngineDetailPanel(key, true);
}

async function openDashboardEngineDetail(engineKey) {
    // Open the latest active trade signal modal and immediately expand the clicked engine's trade details
    if (Array.isArray(allSignals) && allSignals.length > 0) {
        const activeTrade = allSignals.find(s => s.direction === 'BUY' || s.direction === 'SELL') || allSignals[0];
        if (activeTrade && activeTrade.id) {
            return openSignalModal(activeTrade.id, null, engineKey);
        }
    }
    try {
        const res = await fetch('/api/signals/?status=ACTIVE');
        const data = await res.json();
        const list = data.results || data || [];
        if (list.length > 0 && list[0].id) {
            return openSignalModal(list[0].id, null, engineKey);
        }
    } catch (e) {}
    return openLiveSymbolChart('XAUUSD', currentTimeframe || 'H1', engineKey);
}

function renderEvidenceGroups(groups) {
    if (!groups || Object.keys(groups).length === 0) {
        return '<span style="color:var(--text-muted);font-size:12px;grid-column:1/-1;">No independent group data</span>';
    }
    return Object.entries(groups).map(([name, dir]) => {
        const d = (dir || 'NEUTRAL').toUpperCase();
        const col = d === 'BUY' ? '#10b981' : d === 'SELL' ? '#ef4444' : '#94a3b8';
        const bg = d === 'BUY' ? 'rgba(16,185,129,0.1)' : d === 'SELL' ? 'rgba(239,68,68,0.1)' : 'rgba(255,255,255,0.04)';
        const border = d === 'BUY' ? 'rgba(16,185,129,0.3)' : d === 'SELL' ? 'rgba(239,68,68,0.3)' : 'rgba(255,255,255,0.08)';
        const safeName = String(name).replace(/'/g, "\\'");
        return `<div class="evidence-group-card" onclick="jumpToEngineFromEvidenceGroup('${safeName}')" title="Click to open ${name} full trade &amp; engine details" style="padding:8px 10px;border-radius:7px;background:${bg};border:1px solid ${border};display:flex;flex-direction:column;gap:4px;min-width:0;cursor:pointer;transition:all 0.2s ease;">
            <span style="color:var(--text-secondary);font-size:10.5px;font-weight:600;line-height:1.3;word-break:break-word;">${name}</span>
            <div style="display:flex;align-items:center;justify-content:space-between;gap:4px;">
                <span style="color:${col};font-weight:700;font-size:11px;">${d}</span>
                <span style="font-size:10px;color:#60a5fa;font-weight:600;">Details ▾</span>
            </div>
        </div>`;
    }).join('');
}

function closeModal() {
    const modal = document.getElementById('signal-modal');
    modal.classList.remove('open');
    modal.querySelector('.modal-box')?.classList.remove('modal-large');
    stopLiveChartStream();
}

// ── Pair Trade History (click on a pair score card) ────
async function openPairHistory(symbol) {
    const modal = document.getElementById('signal-modal');
    const body  = document.getElementById('modal-body');
    stopLiveChartStream();
    document.getElementById('modal-title').innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;width:100%;">
            <span>📜 ${symbol} — Trade History</span>
            <button class="chart-open-btn" onclick="openLiveSymbolChart('${symbol}', 'H1')">📊 Open Live Chart</button>
        </div>
    `;
    body.innerHTML = '<div class="empty-state" style="padding:30px;text-align:center">Loading history…</div>';
    modal.classList.add('open');

    try {
        const res  = await fetch(`/api/signals/?instrument=${encodeURIComponent(symbol)}`);
        const data = await res.json();
        const all  = (data.results || data || []).filter(s => s.instrument_symbol === symbol);
        const trades = all
            .filter(s => s.direction === 'BUY' || s.direction === 'SELL')
            .sort((a, b) => new Date(b.generated_at) - new Date(a.generated_at));

        const wins   = trades.filter(s => s.status === 'HIT_TP').length;
        const losses = trades.filter(s => s.status === 'HIT_SL').length;
        const open   = trades.filter(s => s.status === 'ACTIVE').length;
        const closed = wins + losses;
        const winRate = closed ? (wins / closed * 100).toFixed(1) + '%' : '—';

        const outcome = {
            HIT_TP:  ['🎯 TP Hit',   'var(--buy-color)'],
            HIT_SL:  ['🛑 SL Hit',   'var(--sell-color)'],
            ACTIVE:  ['⏳ Running',  'var(--accent-cyan)'],
            EXPIRED: ['⌛ Expired',  'var(--text-muted)'],
        };

        const rows = trades.map(s => {
            const [label, color] = outcome[s.status] || [s.status, 'var(--text-muted)'];
            return `<tr onclick="openSignalModal(${s.id})" style="cursor:pointer">
                <td><span class="badge badge-${s.direction.toLowerCase()}">${s.direction}</span></td>
                <td style="font-family:'JetBrains Mono',monospace;font-size:12px">${s.timeframe}</td>
                <td><span class="price-val">${s.entry_price}</span></td>
                <td><span class="price-val sl-val">${s.stop_loss}</span></td>
                <td><span class="price-val tp-val">${s.take_profit_1}</span></td>
                <td style="color:${color};font-weight:600;white-space:nowrap">${label}</td>
                <td style="color:var(--text-muted);font-size:12px;white-space:nowrap">${formatTime(s.generated_at)}</td>
            </tr>`;
        }).join('');

        body.innerHTML = `
            <div class="modal-grid">
                <div class="modal-field"><label>Total Trades</label><span>${trades.length}</span></div>
                <div class="modal-field"><label>Win Rate</label><span style="color:var(--accent-cyan)">${winRate}</span></div>
                <div class="modal-field"><label>Wins (TP)</label><span style="color:var(--buy-color)">${wins}</span></div>
                <div class="modal-field"><label>Losses (SL)</label><span style="color:var(--sell-color)">${losses}</span></div>
                <div class="modal-field"><label>Running</label><span>${open}</span></div>
            </div>
            ${trades.length ? `
            <div style="overflow-x:auto;max-height:50vh;overflow-y:auto">
                <table class="signals-table" style="width:100%">
                    <thead><tr><th>Side</th><th>TF</th><th>Entry</th><th>SL</th><th>TP1</th><th>Result</th><th>Time</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>` : '<div style="padding:24px;text-align:center;color:var(--text-muted)">No trades yet for this pair.</div>'}
        `;
    } catch (err) {
        console.error('History error:', err);
        body.innerHTML = '<div style="padding:24px;text-align:center;color:var(--sell-color)">Could not load trade history.</div>';
    }
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── Helpers ────────────────────────────────────────────
function directionIcon(dir) {
    return dir === 'BUY' ? '🟢' : dir === 'SELL' ? '🔴' : '🟡';
}

function formatTime(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('en-US', {
        month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
        timeZone: 'Asia/Karachi'
    });
}

function animateValue(elId, target, start) {
    const el       = document.getElementById(elId);
    const duration = 800;
    const startTime = performance.now();

    function update(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(start + (target - start) * eased);
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// CSS spin animation injection
const style = document.createElement('style');
style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }';
document.head.appendChild(style);

// ── Scan Markets (Run Engines) ─────────────────────────
let isScanning = false;
async function scanMarkets(silent = true) {
    if (isScanning) return;
    isScanning = true;
    const scanTf = currentTimeframe === 'ALL' ? 'H1' : currentTimeframe;
    const btn = document.getElementById('scan-btn');
    const originalText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = '<span class="refresh-icon" style="animation:spin 1s linear infinite">⚡</span> Scanning...';
        btn.disabled = true;
    }

    try {
        const res = await fetch('/api/signals/bulk-generate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                symbols: ['EURUSD', 'GBPUSD', 'XAUUSD', 'BTCUSD', 'US30'],
                timeframe: scanTf
            })
        });
        
        if (!res.ok) {
            throw new Error(`Server returned HTTP ${res.status}`);
        }
        const data = await res.json();
        console.log('Auto-scan results:', data);

        // Reload dashboard to show any new >=75% signals
        await loadDashboardData();
        
    } catch (err) {
        console.error('Scan error:', err);
    } finally {
        isScanning = false;
        if (btn) {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }
}

// ── Execute Backtest (Phase 11 Replay) ──────────────────
async function executeBacktest() {
    const symbol = document.getElementById('bt-symbol').value;
    const timeframe = document.getElementById('bt-timeframe').value;
    const btn = document.getElementById('run-bt-btn');
    const statusBox = document.getElementById('bt-status-box');

    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Simulating...';
    btn.disabled = true;
    statusBox.innerHTML = `Running historical bar replay simulation for <strong>${symbol} ${timeframe}</strong> (accounting for spread, slippage, and news blackout)...`;

    try {
        const res = await fetch('/api/signals/backtest/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, timeframe, initial_capital: 10000, spread_pips: 1.5 })
        });
        const data = await res.json();

        if (data.error) {
            statusBox.innerHTML = `⚠️ <span style="color:#ef4444">${data.error}</span>`;
            return;
        }

        document.getElementById('bt-winrate').textContent = `${data.win_rate_pct}%`;
        document.getElementById('bt-profitfactor').textContent = `${data.profit_factor}`;
        document.getElementById('bt-maxdrawdown').textContent = `${data.max_drawdown_pct}%`;
        document.getElementById('bt-expectancy').textContent = `${data.expectancy_r > 0 ? '+' : ''}${data.expectancy_r} R`;

        statusBox.innerHTML = `✅ <strong>Run Complete (${data.run_id}):</strong> ${data.total_trades} trades simulated. Wins: ${data.winning_trades}, Losses: ${data.losing_trades}. Final Capital: <strong>$${data.final_capital.toLocaleString()}</strong>.`;
    } catch (err) {
        statusBox.innerHTML = `❌ Backtest error: ${err.message}`;
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// ── Execute Walk-Forward Validation (Phase 10 ML) ──────
async function executeWalkForward() {
    const symbol = document.getElementById('bt-symbol').value;
    const timeframe = document.getElementById('bt-timeframe').value;
    const btn = document.getElementById('run-wf-btn');
    const statusBox = document.getElementById('bt-status-box');

    const originalText = btn.innerHTML;
    btn.innerHTML = '🧠 Validating...';
    btn.disabled = true;
    statusBox.innerHTML = `Running rolling time-series walk-forward out-of-sample validation for <strong>${symbol}</strong> (anti-leakage strict check)...`;

    try {
        const res = await fetch('/api/signals/walk-forward/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, timeframe, splits: 3 })
        });
        const data = await res.json();

        if (data.error) {
            statusBox.innerHTML = `⚠️ <span style="color:#ef4444">${data.error}</span>`;
            return;
        }

        statusBox.innerHTML = `🧠 <strong>Walk-Forward Result:</strong> Out-of-Sample Accuracy: <strong>${data.out_of_sample_accuracy_pct}%</strong> vs Naive Baseline: <strong>${data.baseline_accuracy_pct}%</strong> (Alpha: <strong>${data.alpha_over_baseline_pct > 0 ? '+' : ''}${data.alpha_over_baseline_pct}%</strong>). Strictly leakage-free.`;
    } catch (err) {
        statusBox.innerHTML = `❌ Walk-Forward error: ${err.message}`;
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// ── Section 17 & 1-20: Persistent Automated Trading Engine Controllers ────
let currentAutomationData = null;

async function loadAutomationStatus() {
    try {
        const res = await fetch('/api/accounts/automation-status/');
        if (!res.ok) return;
        const data = await res.json();
        currentAutomationData = data;

        const badge = document.getElementById('auto-trading-badge');
        const globalBtn = document.getElementById('btn-toggle-global-auto');
        const accountNum = document.getElementById('auto-account-num');
        const brokerName = document.getElementById('auto-broker-name');
        const riskVal = document.getElementById('auto-risk-val');
        const maxOpenRisk = document.getElementById('auto-max-open-risk');
        const openPos = document.getElementById('auto-open-positions');
        const todayPnl = document.getElementById('auto-today-pnl');
        const todayR = document.getElementById('auto-today-r');
        const dailyRisk = document.getElementById('auto-daily-risk');
        const drawdownStat = document.getElementById('auto-drawdown-stat');
        const nextSignal = document.getElementById('auto-next-signal');
        const statusText = document.getElementById('auto-status-text');

        const isRunning = data.is_active;

        if (badge) {
            if (isRunning) {
                badge.style.background = 'rgba(16, 185, 129, 0.2)';
                badge.style.color = '#10b981';
                badge.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                badge.innerHTML = '<span style="width: 8px; height: 8px; border-radius: 50%; background: #10b981;"></span> LIVE ACTIVE';
            } else if (data.emergency_stop_active) {
                badge.style.background = 'rgba(239, 68, 68, 0.25)';
                badge.style.color = '#ef4444';
                badge.style.borderColor = 'rgba(239, 68, 68, 0.5)';
                badge.innerHTML = '<span style="width: 8px; height: 8px; border-radius: 50%; background: #ef4444;"></span> EMERGENCY STOPPED';
            } else {
                badge.style.background = 'rgba(245, 158, 11, 0.2)';
                badge.style.color = '#f59e0b';
                badge.style.borderColor = 'rgba(245, 158, 11, 0.4)';
                badge.innerHTML = '<span style="width: 8px; height: 8px; border-radius: 50%; background: #f59e0b;"></span> PAUSED / OFF';
            }
        }

        if (globalBtn) {
            if (data.global_auto_trading) {
                globalBtn.textContent = 'Global Engine: ON';
                globalBtn.style.background = 'rgba(16, 185, 129, 0.2)';
                globalBtn.style.color = '#34d399';
                globalBtn.style.borderColor = 'rgba(16, 185, 129, 0.4)';
            } else {
                globalBtn.textContent = 'Global Engine: OFF';
                globalBtn.style.background = 'rgba(239, 68, 68, 0.2)';
                globalBtn.style.color = '#f87171';
                globalBtn.style.borderColor = 'rgba(239, 68, 68, 0.4)';
            }
        }

        if (data.account) {
            const acc = data.account;
            if (accountNum) accountNum.textContent = acc.account_number_masked || '—';
            if (brokerName) brokerName.textContent = `${acc.broker_name}`;

            // ── Demo / Live badge ──
            const typeBadge = document.getElementById('auto-account-type-badge');
            const isDemo = (acc.account_type || '').toLowerCase().includes('paper') || (acc.account_type || '').toLowerCase().includes('demo') || (acc.account_type || '').toLowerCase().includes('simulation');
            if (typeBadge) {
                if (isDemo) {
                    typeBadge.textContent = 'DEMO';
                    typeBadge.style.background = 'rgba(59,130,246,0.2)';
                    typeBadge.style.color = '#60a5fa';
                    typeBadge.style.border = '1px solid rgba(59,130,246,0.3)';
                } else {
                    typeBadge.textContent = 'LIVE';
                    typeBadge.style.background = 'rgba(16,185,129,0.2)';
                    typeBadge.style.color = '#34d399';
                    typeBadge.style.border = '1px solid rgba(16,185,129,0.3)';
                }
            }

            // ── Balance display ──
            const balanceDisplay = document.getElementById('auto-balance-display');
            if (balanceDisplay) {
                const bal = Number(acc.balance || 0);
                const eq = Number(acc.equity || 0);
                const currency = acc.currency || 'USD';
                balanceDisplay.style.color = isDemo ? '#60a5fa' : '#34d399';
                balanceDisplay.innerHTML = `Balance: <strong>$${bal.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</strong> &nbsp;|&nbsp; Equity: <strong>$${eq.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}</strong>`;
            }

            if (riskVal) riskVal.textContent = `${Number(acc.risk_pct).toFixed(2)}%`;
            if (maxOpenRisk) maxOpenRisk.textContent = `Max Open: ${Number(acc.max_open_risk_pct).toFixed(1)}%`;
            if (openPos) openPos.textContent = `${acc.open_positions_count}`;
            if (todayPnl) {
                const pnl = Number(acc.today_pnl_usd);
                todayPnl.textContent = `${pnl >= 0 ? '+' : '-'}$${Math.abs(pnl).toFixed(2)}`;
                todayPnl.style.color = pnl >= 0 ? '#10b981' : '#ef4444';
            }
            if (todayR) {
                const r = Number(acc.today_pnl_r);
                todayR.textContent = `${r >= 0 ? '+' : ''}${r.toFixed(2)} R realized`;
            }
            if (dailyRisk) {
                dailyRisk.textContent = `${Number(acc.daily_risk_used_pct).toFixed(2)}% / ${acc.daily_drawdown_limit_pct}%`;
            }
            if (drawdownStat) {
                drawdownStat.textContent = `DD: ${Number(acc.current_drawdown_pct).toFixed(1)}% / Max ${acc.max_drawdown_limit_pct}%`;
            }
        }

        if (nextSignal) {
            nextSignal.textContent = isRunning ? 'Monitoring live...' : 'Halted (Engine Off)';
            nextSignal.style.color = isRunning ? '#60a5fa' : '#94a3b8';
        }

        // Update Navbar Dropdown Button & Sidebar Badges
        const navPill = document.getElementById('nav-auto-pill');
        const sidebarBadge = document.getElementById('sidebar-auto-badge');
        if (navPill) {
            if (isRunning) {
                navPill.className = 'nav-auto-pill live';
                navPill.innerHTML = '<span class="pill-dot"></span> LIVE ACTIVE';
            } else if (data.emergency_stop_active) {
                navPill.className = 'nav-auto-pill stopped';
                navPill.innerHTML = '<span class="pill-dot"></span> STOPPED';
            } else {
                navPill.className = 'nav-auto-pill paused';
                navPill.innerHTML = '<span class="pill-dot"></span> PAUSED';
            }
        }
        if (sidebarBadge) {
            if (isRunning) {
                sidebarBadge.style.background = 'rgba(16, 185, 129, 0.2)';
                sidebarBadge.style.color = '#10b981';
                sidebarBadge.textContent = 'LIVE';
            } else if (data.emergency_stop_active) {
                sidebarBadge.style.background = 'rgba(239, 68, 68, 0.2)';
                sidebarBadge.style.color = '#ef4444';
                sidebarBadge.textContent = 'HALT';
            } else {
                sidebarBadge.style.background = 'rgba(245, 158, 11, 0.2)';
                sidebarBadge.style.color = '#f59e0b';
                sidebarBadge.textContent = 'OFF';
            }
        }
    } catch (e) {
        console.error('Error fetching automation status:', e);
    }
}

// Toggle Automated Trading Console via Navbar Button / Arrow
function toggleAutoTradingConsole(e) {
    if (e && e.preventDefault) e.preventDefault();
    closeMobileSidebar();
    const section = document.getElementById('auto-console-section');
    const navBtn = document.getElementById('nav-auto-trading-btn');
    if (!section) return;

    const isCollapsed = section.classList.contains('collapsed');
    if (isCollapsed) {
        section.classList.remove('collapsed');
        if (navBtn) navBtn.classList.add('active');
        localStorage.setItem('ts_auto_console_open', 'true');
        section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
        section.classList.add('collapsed');
        if (navBtn) navBtn.classList.remove('active');
        localStorage.setItem('ts_auto_console_open', 'false');
    }
}

// Global Switch Toggle (Section 10)
async function toggleGlobalAutoTrading() {
    if (!currentAutomationData) return;
    const newState = !currentAutomationData.global_auto_trading;
    try {
        const res = await fetch('/api/accounts/global-switch/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ enabled: newState })
        });
        const data = await res.json();
        if (data.success) {
            loadAutomationStatus();
        } else {
            alert('Error updating global switch: ' + (data.error || 'Unknown error'));
        }
    } catch (err) {
        alert('Failed to contact server: ' + err.message);
    }
}

// Authorize Modal (Section 1)
function openAuthorizeModal() {
    const modal = document.getElementById('authorize-modal');
    if (!modal) return;
    
    const select = document.getElementById('auth-account-select');
    if (select && currentAutomationData && currentAutomationData.all_accounts) {
        select.innerHTML = '';
        currentAutomationData.all_accounts.forEach(acc => {
            const opt = document.createElement('option');
            opt.value = acc.id;
            opt.textContent = `${acc.broker_name} (${acc.account_number_masked}) — ${acc.authorization_status}`;
            select.appendChild(opt);
        });
    }

    if (currentAutomationData && currentAutomationData.account) {
        document.getElementById('auth-risk-pct').value = currentAutomationData.account.risk_pct;
        document.getElementById('auth-max-open-risk').value = currentAutomationData.account.max_open_risk_pct;
    }

    document.getElementById('auth-explicit-confirm').checked = false;
    modal.style.display = 'flex';
    modal.classList.add('open');
}

function closeAuthorizeModal() {
    const modal = document.getElementById('authorize-modal');
    if (modal) {
        modal.classList.remove('open');
        modal.style.display = 'none';
    }
}

async function submitAuthorization() {
    const select = document.getElementById('auth-account-select');
    const riskPct = parseFloat(document.getElementById('auth-risk-pct').value);
    const maxOpenRiskPct = parseFloat(document.getElementById('auth-max-open-risk').value);
    const confirmBox = document.getElementById('auth-explicit-confirm');

    if (!confirmBox.checked) {
        alert('Please check the authorization box to explicitly confirm persistent automated trading.');
        return;
    }

    const accountId = select ? select.value : (currentAutomationData?.account?.id || 1);
    const btn = document.getElementById('btn-submit-authorization');
    const origText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = 'Arming Engine...';

    try {
        const res = await fetch('/api/accounts/authorize/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                account_id: accountId,
                risk_pct: riskPct,
                max_open_risk_pct: maxOpenRiskPct,
                is_authorized: true
            })
        });
        const data = await res.json();
        if (data.success) {
            closeAuthorizeModal();
            loadAutomationStatus();
        } else {
            alert('Authorization failed: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Server communication error: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = origText;
    }
}

// Emergency Stop Modal (Section 11)
function openEmergencyStopModal() {
    const modal = document.getElementById('emergency-stop-modal');
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('open');
    }
}

function closeEmergencyStopModal() {
    const modal = document.getElementById('emergency-stop-modal');
    if (modal) {
        modal.classList.remove('open');
        modal.style.display = 'none';
    }
}

async function executeEmergencyStop() {
    const closePositions = document.getElementById('emergency-close-positions').checked;
    try {
        const res = await fetch('/api/accounts/emergency-stop/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                close_positions: closePositions,
                reason: 'Manual Emergency Stop triggered via Dashboard Console'
            })
        });
        const data = await res.json();
        if (data.success) {
            closeEmergencyStopModal();
            loadAutomationStatus();
            alert(`🛑 EMERGENCY STOP ACTIVATED!\nAutomated trading has been completely halted.\nClosed positions: ${data.closed_positions || 0}`);
        } else {
            alert('Failed to trigger emergency stop: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

function getCsrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : '';
}

// ── Connect Broker Account Modal (Broker Dropdown -> Server Dropdown -> Login / Password) ────
const BROKER_SERVERS = {
    EXNESS: [
        'Exness-MT5Real', 'Exness-MT5Real2', 'Exness-MT5Real3', 'Exness-MT5Real4', 'Exness-MT5Real5',
        'Exness-MT5Real6', 'Exness-MT5Real7', 'Exness-MT5Real8', 'Exness-MT5Real9', 'Exness-MT5Real10',
        'Exness-MT5Real11', 'Exness-MT5Real12', 'Exness-MT5Real14', 'Exness-MT5Real15', 'Exness-MT5Real20',
        'Exness-MT5Trial', 'Exness-MT5Trial2', 'Exness-MT5Trial3', 'Exness-MT5Trial4', 'Exness-MT5Trial5',
        'Exness-MT5Trial6', 'Exness-MT5Trial7', 'Exness-MT5Trial8', 'Exness-MT5Trial9', 'Exness-MT5Trial10',
        'Exness-MT5Trial11', 'Exness-MT5Trial12', 'Exness-MT5Trial14', 'Exness-MT5Trial15', 'Exness-MT5Trial16',
        'Exness-MT5Trial17', 'Exness-MT5Trial18', 'Exness-Real', 'Exness-Trial'
    ],
    XM: [
        'XMGlobal-MT5', 'XMGlobal-MT5 2', 'XMGlobal-MT5 3', 'XMGlobal-MT5 4', 'XMGlobal-MT5 5',
        'XMGlobal-MT5 6', 'XMGlobal-MT5 7', 'XMGlobal-Real 1', 'XMGlobal-Real 2', 'XMGlobal-Demo 3'
    ],
    ICMARKETS: [
        'ICMarketsSC-MT5', 'ICMarketsSC-MT5-2', 'ICMarketsSC-MT5-3', 'ICMarketsSC-MT5-4',
        'ICMarketsSC-Demo', 'ICMarketsSC-Demo02', 'ICMarketsEU-MT5', 'ICMarketsGlobal-MT5'
    ],
    OCTAFX: [
        'OctaFX-Real', 'OctaFX-Real2', 'OctaFX-Real3', 'OctaFX-Real4', 'OctaFX-Demo', 'OctaMarkets-Real'
    ],
    FBS: [
        'FBS-Real', 'FBS-Real-2', 'FBS-Real-3', 'FBS-Demo', 'FBS-MT5-Real', 'FBS-MT5-Demo'
    ],
    HFM: [
        'HFMarketsGlobal-Live1', 'HFMarketsGlobal-Live2', 'HFMarketsGlobal-Live3', 'HFMarketsGlobal-Demo', 'HFMarketsSV-LiveServer'
    ],
    DERIV: [
        'Deriv-Server', 'Deriv-Server-02', 'Deriv-Server-03', 'Deriv-Demo', 'DerivSVG-Server', 'DerivBVI-Server'
    ],
    PEPPERSTONE: [
        'Pepperstone-MT5-Live01', 'Pepperstone-MT5-Edge01', 'Pepperstone-MT5-Edge02', 'Pepperstone-Demo01', 'PepperstoneUK-Live01'
    ],
    FPMARKETS: [
        'FPMarkets-Live', 'FPMarkets-Live2', 'FPMarkets-Demo', 'FPMarketsLLC-Live'
    ],
    VANTAGE: [
        'VantageInternational-Live', 'VantageInternational-Live 2', 'VantageInternational-Live 3', 'VantageInternational-Demo'
    ],
    TICKMILL: [
        'Tickmill-Live', 'Tickmill-Live02', 'Tickmill-Demo', 'TickmillUK-Live'
    ],
    METAQUOTES: [
        'MetaQuotes-Demo'
    ],
    BINANCE: [
        'Binance-Futures-Mainnet', 'Binance-Spot-Mainnet', 'Binance-Testnet'
    ],
    BYBIT: [
        'Bybit-Mainnet-Linear', 'Bybit-Spot-Mainnet', 'Bybit-Testnet'
    ]
};

function onBrokerSelectChange() {
    const brokerKey = document.getElementById('broker-select-input')?.value || 'EXNESS';
    const serverSelect = document.getElementById('broker-server-select');
    const customInput = document.getElementById('broker-server-custom');
    if (!serverSelect) return;

    const servers = BROKER_SERVERS[brokerKey] || ['MetaQuotes-Demo'];
    serverSelect.innerHTML = '';

    servers.forEach(srv => {
        const opt = document.createElement('option');
        opt.value = srv;
        opt.textContent = srv;
        serverSelect.appendChild(opt);
    });

    const customOpt = document.createElement('option');
    customOpt.value = '__CUSTOM__';
    customOpt.textContent = 'Other / Custom Server...';
    serverSelect.appendChild(customOpt);

    if (customInput) customInput.style.display = 'none';
}

function onServerSelectChange() {
    const serverSelect = document.getElementById('broker-server-select');
    const customInput = document.getElementById('broker-server-custom');
    if (!serverSelect || !customInput) return;

    if (serverSelect.value === '__CUSTOM__') {
        customInput.style.display = 'block';
        customInput.focus();
    } else {
        customInput.style.display = 'none';
    }
}

function openConnectBrokerModal() {
    const modal = document.getElementById('connect-broker-modal');
    if (!modal) return;

    const testBox = document.getElementById('broker-test-result');
    if (testBox) {
        testBox.style.display = 'none';
        testBox.innerHTML = '';
    }

    const serverSelect = document.getElementById('broker-server-select');
    if (serverSelect && serverSelect.options.length === 0) {
        onBrokerSelectChange();
    }

    modal.style.display = 'flex';
    modal.classList.add('open');
    setTimeout(() => document.getElementById('broker-login-input')?.focus(), 50);
}

function closeConnectBrokerModal() {
    const modal = document.getElementById('connect-broker-modal');
    if (modal) {
        modal.classList.remove('open');
        modal.style.display = 'none';
    }
}

async function submitConnectBroker() {
    const brokerSelected = document.getElementById('broker-select-input')?.value || 'EXNESS';
    const serverSelectVal = document.getElementById('broker-server-select')?.value || '';
    const customServerVal = document.getElementById('broker-server-custom')?.value.trim() || '';
    const server = (serverSelectVal === '__CUSTOM__' ? customServerVal : serverSelectVal).trim();
    const accountNumber = document.getElementById('broker-login-input')?.value.trim() || '';
    const password = document.getElementById('broker-password-input')?.value.trim() || '';
    const testBox = document.getElementById('broker-test-result');
    const btn = document.getElementById('btn-connect-broker-submit');

    if (!accountNumber || !password || !server) {
        if (testBox) {
            testBox.style.display = 'block';
            testBox.style.background = 'rgba(239, 68, 68, 0.12)';
            testBox.style.border = '1px solid rgba(239, 68, 68, 0.35)';
            testBox.style.color = '#f87171';
            testBox.innerHTML = '❌ Please select Broker & Server and enter Login & Password.';
        }
        return;
    }

    let brokerType = 'MT5';
    if (brokerSelected === 'EXNESS' || server.toUpperCase().includes('EXNESS')) {
        brokerType = 'EXNESS';
    } else if (brokerSelected === 'BINANCE' || brokerSelected === 'BYBIT') {
        brokerType = brokerSelected;
    }

    const isLive = /real|live/i.test(server);
    const isPaper = !isLive;

    const origText = btn ? btn.innerHTML : 'Login';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = 'Connecting...';
    }

    try {
        const res = await fetch('/api/accounts/linked/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({
                name: `${server} (${accountNumber})`,
                broker_type: brokerType,
                account_number: accountNumber,
                password: password,
                server: server,
                is_paper: isPaper,
                auto_trade_enabled: true,
                is_authorized: true,
                max_risk_pct: 0.5,
                max_open_risk_pct: 3.0
            })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            await fetch('/api/accounts/global-switch/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify({ enabled: true })
            });
            // Show brief success info
            if (testBox) {
                testBox.style.display = 'block';
                testBox.style.background = isLive ? 'rgba(16,185,129,0.12)' : 'rgba(59,130,246,0.12)';
                testBox.style.border = isLive ? '1px solid rgba(16,185,129,0.35)' : '1px solid rgba(59,130,246,0.35)';
                testBox.style.color = isLive ? '#34d399' : '#60a5fa';
                testBox.innerHTML = (isLive ? '✅ <strong>Live Account Auto-Connected!</strong>' : '✅ <strong>Demo Account Auto-Connected!</strong>') + ` Account <strong>${accountNumber}</strong> connected successfully.`;
            }
            setTimeout(() => {
                closeConnectBrokerModal();
            }, 1800);
            await loadAutomationStatus();
        } else {
            if (testBox) {
                testBox.style.display = 'block';
                testBox.style.background = 'rgba(239, 68, 68, 0.12)';
                testBox.style.border = '1px solid rgba(239, 68, 68, 0.35)';
                testBox.style.color = '#f87171';
                testBox.innerHTML = `❌ <strong>Error:</strong> ${data.error || 'Could not login to account.'}`;
            } else {
                alert('Error: ' + (data.error || 'Unknown error'));
            }
        }
    } catch (e) {
        alert('Failed to connect broker account: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origText;
        }
    }
}







