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

// ── Signal Modal ───────────────────────────────────────
// ── Signal Chart & Modal ────────────────────────────────
let currentChartInstance = null;

async function openSignalModal(id) {
    const modal = document.getElementById('signal-modal');
    const modalBox = modal.querySelector('.modal-box');
    const body  = document.getElementById('modal-body');
    
    modalBox.classList.add('modal-large');
    document.getElementById('modal-title').textContent = 'Loading Chart & Signal Details…';
    body.innerHTML = '<div class="empty-state" style="padding:40px;text-align:center"><div class="empty-icon" style="animation:spin 1s linear infinite">⏳</div><div>Loading live chart data…</div></div>';
    modal.classList.add('open');

    try {
        const res  = await fetch(`/api/signals/${id}/chart/`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const s    = await res.json();

        const dirColor = s.direction === 'BUY' ? 'var(--buy-color)' : 'var(--sell-color)';
        const dirBadge = s.direction.toLowerCase();
        
        document.getElementById('modal-title').innerHTML = `
            <span>${directionIcon(s.direction)} ${s.symbol} <span style="color:var(--text-muted);font-weight:400">·</span> ${s.timeframe}</span>
            <span class="badge badge-${dirBadge}" style="margin-left:10px">${s.direction}</span>
            <span class="badge badge-${(s.status||'').toLowerCase()}" style="margin-left:6px">${s.status}</span>
        `;

        body.innerHTML = `
            <!-- Trade Levels Banner -->
            <div class="modal-grid" style="grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); margin-bottom: 14px;">
                <div class="modal-field"><label>Entry Price</label><span class="price-val" style="color:#60a5fa;font-size:16px;">${s.entry_price}</span></div>
                <div class="modal-field"><label>Stop Loss (SL)</label><span class="price-val sl-val" style="font-size:16px;">${s.stop_loss}</span></div>
                <div class="modal-field"><label>Take Profit 1 (TP1)</label><span class="price-val tp-val" style="font-size:16px;">${s.take_profit_1} (1.5R)</span></div>
                ${s.take_profit_2 ? `<div class="modal-field"><label>Take Profit 2</label><span class="price-val tp-val">${s.take_profit_2} (2.5R)</span></div>` : ''}
                <div class="modal-field"><label>Risk : Reward</label><span class="rr-val" style="color:#10b981;font-weight:700">${s.risk_reward}:1</span></div>
                <div class="modal-field"><label>Confidence</label><span style="color:var(--accent-cyan)">${s.confidence_score}%</span></div>
            </div>

            <!-- Version 2.0 Architectural Gates & Regime Bar -->
            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px;padding:10px 14px;background:rgba(255,255,255,0.03);border-radius:8px;border:1px solid rgba(255,255,255,0.08);align-items:center;justify-content:space-between;">
                <div style="display:flex;gap:12px;align-items:center;">
                    <span style="font-size:12px;color:var(--text-muted)">Decision Class:</span>
                    <span class="badge badge-${(s.decision_class||'strong').toLowerCase()}" style="font-size:11px">${s.decision_class || 'STRONG'}</span>
                    <span style="font-size:12px;color:var(--text-muted)">Regime:</span>
                    <span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--accent-cyan);background:rgba(56,189,248,0.1);padding:2px 8px;border-radius:4px">${s.market_regime || 'TRENDING'}</span>
                </div>
                <div style="display:flex;gap:12px;align-items:center;">
                    <span style="font-size:12px;color:var(--text-muted)">Execution Gate:</span>
                    <span style="font-size:12px;font-weight:600;color:${s.is_trade_allowed ? '#10b981' : '#ef4444'}">${s.is_trade_allowed ? '✅ Eligible' : '❌ Rejection Filtered'}</span>
                    <span style="font-size:12px;color:var(--text-muted)">Position:</span>
                    <span style="font-family:'JetBrains Mono',monospace;font-size:12px;color:#fff">${s.recommended_lots || '0.10'} Lots</span>
                </div>
            </div>

            <!-- Section 5: Independent Evidence Groups Matrix -->
            <div style="margin-bottom:14px;padding:12px 14px;background:var(--bg-surface);border:1px solid rgba(255,255,255,0.06);border-radius:8px;">
                <div style="font-size:11px;text-transform:uppercase;color:var(--text-muted);font-weight:700;margin-bottom:8px">
                    🏛️ Section 5 Independent Evidence Groups (3+ Required)
                </div>
                <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(110px, 1fr));gap:6px;">
                    ${renderEvidenceGroups(s.independent_groups || {})}
                </div>
            </div>

            <!-- Candlestick Chart with Trade Points -->
            <div class="chart-card-wrap">
                <div class="chart-card-header">
                    <div style="font-size:13px;font-weight:600;display:flex;align-items:center;gap:8px;">
                        <span>📊 Live Price Action &amp; Trade Placement</span>
                    </div>
                    <div class="chart-levels-legend">
                        <span class="chart-lvl-tag entry">🔵 Entry: ${s.entry_price}</span>
                        <span class="chart-lvl-tag sl">🔴 SL: ${s.stop_loss}</span>
                        <span class="chart-lvl-tag tp">🟢 TP1: ${s.take_profit_1}</span>
                        ${s.take_profit_2 ? `<span class="chart-lvl-tag tp">🟢 TP2: ${s.take_profit_2}</span>` : ''}
                    </div>
                </div>
                <div id="signal-chart-viewport" class="chart-viewport"></div>
            </div>

            ${s.analysis_summary ? `<div style="padding:14px;background:var(--bg-surface);border:1px solid rgba(255,255,255,0.06);border-radius:10px;font-size:13px;color:var(--text-secondary);margin-bottom:16px;line-height:1.5;"><strong>Engine Confluence Analysis:</strong><br>${s.analysis_summary}</div>` : ''}
            ${s.warnings?.length ? `<div style="padding:10px 14px;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);border-radius:8px;font-size:12px;color:var(--wait-color);margin-bottom:16px">⚠️ ${s.warnings.join(' | ')}</div>` : ''}
            
            <div class="engine-scores" style="margin-top:14px">
                <h4 style="font-size:12px;text-transform:uppercase;color:var(--text-muted);margin-bottom:10px">Engine Confidence Scores</h4>
                ${scoreRow('📐 Technical Engine',     s.technical_score,     15)}
                ${scoreRow('💡 SMC / ICT Engine',     s.smc_score,           20)}
                ${scoreRow('🕯️ Price Action Engine', s.price_action_score,  15)}
                ${scoreRow('🌍 Macro Environment',    s.macro_score,         15)}
                ${scoreRow('📰 News Sentiment',       s.news_score,          15)}
                ${scoreRow('🏦 Institutional Flow',   s.institutional_score, 10)}
                ${scoreRow('🤖 AI / ML Prediction',   s.ai_ml_score,         10)}
            </div>
        `;

        // Render candlestick chart with points marked
        renderSignalCandleChart(s);

    } catch (err) {
        console.error('Modal error:', err);
        body.innerHTML = `<div style="padding:30px;text-align:center;color:var(--sell-color)">Failed to load chart: ${err.message}</div>`;
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
                time: c.time,
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close
            });
        }
    }

    // If Lightweight Charts is available
    if (window.LightweightCharts) {
        try {
            const chart = LightweightCharts.createChart(container, {
                width: container.clientWidth,
                height: 380,
                layout: {
                    background: { color: '#070c18' },
                    textColor: '#94a3b8',
                },
                grid: {
                    vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
                    horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
                },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal,
                },
                rightPriceScale: {
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    scaleMargins: { top: 0.12, bottom: 0.12 },
                },
                timeScale: {
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    timeVisible: true,
                    secondsVisible: false,
                },
            });

            const candleSeries = chart.addCandlestickSeries({
                upColor: '#10b981',
                downColor: '#ef4444',
                borderVisible: false,
                wickUpColor: '#10b981',
                wickDownColor: '#ef4444',
            });

            candleSeries.setData(candleData);

            // ── Trade Points & Levels ──────────────────────
            // 1. Entry Price Line
            candleSeries.createPriceLine({
                price: s.entry_price,
                color: '#38bdf8',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Solid,
                axisLabelVisible: true,
                title: `ENTRY: ${s.entry_price}`,
            });

            // 2. Stop Loss Line
            candleSeries.createPriceLine({
                price: s.stop_loss,
                color: '#ef4444',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `SL: ${s.stop_loss}`,
            });

            // 3. Take Profit 1 Line
            candleSeries.createPriceLine({
                price: s.take_profit_1,
                color: '#10b981',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `TP1: ${s.take_profit_1}`,
            });

            // 4. TP2 (if exists)
            if (s.take_profit_2) {
                candleSeries.createPriceLine({
                    price: s.take_profit_2,
                    color: '#059669',
                    lineWidth: 1,
                    lineStyle: LightweightCharts.LineStyle.Dotted,
                    axisLabelVisible: true,
                    title: `TP2: ${s.take_profit_2}`,
                });
            }

            // ── Trade Marker at Signal Point ────────────────
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

            chart.timeScale().fitContent();
            currentChartInstance = chart;

            // Handle resize
            const ro = new ResizeObserver(() => {
                if (currentChartInstance && container) {
                    currentChartInstance.applyOptions({ width: container.clientWidth });
                }
            });
            ro.observe(container);

            return;
        } catch (e) {
            console.warn('LightweightCharts error, falling back to canvas:', e);
        }
    }

    // ── Self-Contained Canvas Fallback (Works 100% offline) ──
    renderCanvasCandlestickChart(container, candleData, s);
}

// ── Built-in Canvas Candlestick Chart ───────────────────
function renderCanvasCandlestickChart(container, candles, s) {
    container.innerHTML = '';
    const canvas = document.createElement('canvas');
    container.appendChild(canvas);

    const dpr = window.devicePixelRatio || 1;
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 380;
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
    let minP = Math.min(...candles.map(c => c.low), s.stop_loss, s.entry_price, s.take_profit_1);
    let maxP = Math.max(...candles.map(c => c.high), s.stop_loss, s.entry_price, s.take_profit_1);
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

    // Draw Entry, SL, TP levels
    drawLevel(s.entry_price, 'ENTRY', '#38bdf8', false);
    drawLevel(s.stop_loss, 'SL', '#ef4444', true);
    drawLevel(s.take_profit_1, 'TP1', '#10b981', true);
    if (s.take_profit_2) drawLevel(s.take_profit_2, 'TP2', '#059669', true);

    // ── Draw Trade Execution Marker ───────────────────────
    const lastX = padLeft + (count - 1) * stepX + stepX / 2;
    const entryY = priceToY(s.entry_price);
    const isBuy = s.direction === 'BUY';

    ctx.save();
    ctx.fillStyle = isBuy ? '#10b981' : '#ef4444';
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1;

    // Arrow pointer
    const arrowY = isBuy ? entryY + 12 : entryY - 12;
    ctx.beginPath();
    ctx.moveTo(lastX, entryY);
    ctx.lineTo(lastX - 6, arrowY);
    ctx.lineTo(lastX + 6, arrowY);
    ctx.closePath();
    ctx.fill();

    // Marker text box
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

function scoreRow(label, score, weight) {
    const pct = Math.min(100, parseFloat(score) || 0);
    return `
        <div class="score-row">
            <span class="score-label">${label} (${weight}%)</span>
            <div class="score-bar"><div class="score-bar-fill" style="width:${pct}%"></div></div>
            <span class="score-num">${pct.toFixed(0)}</span>
        </div>`;
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
        return `<div style="padding:7px 10px;border-radius:6px;background:${bg};border:1px solid ${border};display:flex;flex-direction:column;gap:3px;min-width:0;">
            <span style="color:var(--text-secondary);font-size:10.5px;font-weight:600;line-height:1.3;word-break:break-word;" title="${name}">${name}</span>
            <span style="color:${col};font-weight:700;font-size:11px;">${d}</span>
        </div>`;
    }).join('');
}

function closeModal() {
    const modal = document.getElementById('signal-modal');
    modal.classList.remove('open');
    modal.querySelector('.modal-box')?.classList.remove('modal-large');
    if (currentChartInstance) {
        try { currentChartInstance.remove(); } catch(e) {}
        currentChartInstance = null;
    }
}

// ── Pair Trade History (click on a pair score card) ────
async function openPairHistory(symbol) {
    const modal = document.getElementById('signal-modal');
    const body  = document.getElementById('modal-body');
    document.getElementById('modal-title').textContent = `📜 ${symbol} — Trade History`;
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
            if (brokerName) brokerName.textContent = `${acc.broker_name} (${acc.account_type})`;
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
                balance: 10000,
                is_paper: false,
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
            closeConnectBrokerModal();
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





