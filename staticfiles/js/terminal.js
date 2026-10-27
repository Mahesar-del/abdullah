/* TradeSense Pro — Terminal Ticker Tape & Real-Time Streaming Single TradingView Chart */
(function () {
    const SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'BTCUSD', 'ETHUSD', 'US30', 'NAS100', 'USOIL'];
    const REFRESH_MS = 15000;
    const state = {};
    const track = document.getElementById('ticker-track');
    if (!track) return;

    function fmt(sym, v) {
        if (v == null || isNaN(v)) return '—';
        if (sym.endsWith('JPY')) return v.toFixed(3);
        if (v >= 1000) return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (v >= 10) return v.toFixed(3);
        return v.toFixed(5);
    }

    function itemHTML(sym) {
        const s = state[sym];
        if (!s) return `<span class="ticker-item" style="cursor:pointer" onclick="window.selectTradingViewSymbol && window.selectTradingViewSymbol('${sym}', true)"><span class="ticker-sym">${sym}</span><span class="ticker-px">…</span></span>`;
        const dir = s.pct > 0.005 ? 'up' : s.pct < -0.005 ? 'down' : 'flat';
        const arrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : '■';
        const pct = s.pct == null ? '' : `${s.pct >= 0 ? '+' : ''}${s.pct.toFixed(2)}%`;
        return `<span class="ticker-item" style="cursor:pointer" title="Click to view ${sym} on TradingView chart" onclick="window.selectTradingViewSymbol && window.selectTradingViewSymbol('${sym}', true)"><span class="ticker-sym">${sym}</span>` +
               `<span class="ticker-px">${fmt(sym, s.price)}</span>` +
               `<span class="ticker-chg ${dir}">${arrow} ${pct}</span></span>`;
    }

    function render() {
        const html = SYMBOLS.map(itemHTML).join('');
        track.innerHTML = html + html;
    }

    async function fetchOne(sym) {
        try {
            const res = await fetch(`/api/market/live-tick/?symbol=${sym}&tf=D1`);
            if (!res.ok) return;
            const d = await res.json();
            const candles = d.recent_candles || [];
            const price = d.live_price;
            const prev = candles.length >= 2 ? candles[candles.length - 2].close : null;
            state[sym] = { price, pct: prev ? ((price - prev) / prev) * 100 : null };
            render();
        } catch (e) { /* keep last value */ }
    }

    async function cycle() {
        for (const sym of SYMBOLS) await fetchOne(sym);
    }

    track.innerHTML = '<span class="ticker-msg">LOADING MARKET DATA…</span>';
    cycle();
    setInterval(cycle, REFRESH_MS);
})();

/* ── Single Live-Streaming TradingView Chart (Bottom of UI) ── */
(function () {
    const TV_SYMBOLS = {
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
        US30:   'FOREXCOM:DJI',
        NAS100: 'FOREXCOM:NSXUSD',
        SPX500: 'FOREXCOM:SPXUSD',
        USOIL:  'TVC:USOIL',
        UKOIL:  'TVC:UKOIL',
    };

    const BINANCE_WS = {
        BTCUSD: 'btcusdt',
        ETHUSD: 'ethusdt',
        BNBUSD: 'bnbusdt',
        SOLUSD: 'solusdt',
        XRPUSD: 'xrpusdt',
        XAUUSD: 'paxgusdt',
        EURUSD: 'eurusdt',
        GBPUSD: 'gbpusdt',
    };

    const INT_TO_TF = {
        '1': 'M1', '5': 'M5', '15': 'M15', '30': 'M30',
        '60': 'H1', '120': 'H2', '240': 'H4', 'D': 'D1',
    };

    const TF_TO_INT = {
        M1: '1', M5: '5', M15: '15', M30: '30',
        H1: '60', H2: '120', H4: '240', D1: 'D',
    };

    const INT_LABELS = {
        '1': '1m', '5': '5m', '15': '15m', '30': '30m',
        '60': '1H', '120': '2H', '240': '4H', 'D': '1D',
    };

    const TF_SECONDS = {
        M1: 60, M5: 300, M15: 900, M30: 1800,
        H1: 3600, H2: 7200, H4: 14400, D1: 86400,
    };

    const box = document.getElementById('tv-chart-container');
    const sel = document.getElementById('tv-symbol-select');
    const tfWrap = document.getElementById('tv-chart-tf');
    const quickWrap = document.getElementById('tv-quick-symbols');
    const engineWrap = document.getElementById('btm-tv-engine-mode');
    const activePill = document.getElementById('tv-active-symbol-pill');
    const priceBox = document.getElementById('btm-tv-price-box');
    const priceValEl = document.getElementById('btm-tv-price-val');
    const priceArrEl = document.getElementById('btm-tv-price-arrow');
    const clockEl = document.getElementById('btm-tv-clock');
    const countdownEl = document.getElementById('btm-tv-countdown');
    const ohlcOverlay = document.getElementById('btm-tv-ohlc-overlay');
    const ohlcRow1 = document.getElementById('btm-tv-ohlc-row1');
    const ohlcRow2 = document.getElementById('btm-tv-ohlc-row2');

    if (!box) return;

    // Local timezone offset in seconds so LightweightCharts renders local clock time on the X-axis & crosshair
    const TZ_OFFSET_SEC = -new Date().getTimezoneOffset() * 60;

    let symbol = localStorage.getItem('ts_tv_symbol') || 'XAUUSD';
    let interval = localStorage.getItem('ts_tv_interval') || '60';
    let engineMode = 'LIVE'; // 'LIVE' (LightweightCharts real-time stream) | 'WIDGET' (TradingView iframe)

    if (!TV_SYMBOLS[symbol]) symbol = 'XAUUSD';
    if (!INT_LABELS[interval]) interval = '60';

    let btmChart = null;
    let btmSeries = null;
    let btmCandles = [];
    let btmResizeObs = null;
    let btmWs = null;
    let btmPollTimer = null;
    let btmHeartbeatTimer = null;
    let btmWsInitPrice = null;
    let btmAnchorPrice = null;
    let btmLastPrice = null;
    let btmHovering = false;
    let btmLivePriceLine = null;
    let btmCurrentMarkers = [];
    let btmChartStats = { avgVolume: 100, avgRange: 1 };

    function computeCandleAverages(candles) {
        if (!candles || candles.length === 0) return { avgVolume: 100, avgRange: 1 };
        let totalVol = 0;
        let totalRange = 0;
        let count = 0;
        for (let i = 0; i < candles.length; i++) {
            const c = candles[i];
            const v = Number(c.volume) || 0;
            const r = Math.max(0, (Number(c.high) || 0) - (Number(c.low) || 0));
            if (v > 0) {
                totalVol += v;
                count++;
            }
            totalRange += r;
        }
        const avgVol = count > 0 ? (totalVol / count) : 100;
        const avgRange = candles.length > 0 ? (totalRange / candles.length) : 1;
        return { avgVolume: avgVol, avgRange: avgRange };
    }

    function classifyCandleLiquidity(c, avgVolume, avgRange) {
        if (!c) return { label: '🎯 Retailers', isBank: false, text: 'Retailers' };
        const vol = Number(c.volume) || 0;
        const high = Number(c.high) || 0;
        const low = Number(c.low) || 0;
        const open = Number(c.open) || 0;
        const close = Number(c.close) || 0;
        const range = Math.max(0, high - low);
        const body = Math.abs(close - open);

        const rvol = (avgVolume && avgVolume > 0) ? (vol / avgVolume) : 1.0;
        const rRange = (avgRange && avgRange > 0) ? (range / avgRange) : 1.0;

        // Institutional Bank Footprint:
        // 1. High Relative Volume (rvol >= 1.25)
        // 2. High Displacement / Expansion with volume (rRange >= 1.30 && rvol >= 0.95)
        // 3. Strong directional body (> 65% of range) with elevated volume (rvol >= 1.10)
        const isBank = (rvol >= 1.25) || (rRange >= 1.30 && rvol >= 0.95) || (range > 0 && (body / range) > 0.65 && rvol >= 1.10);

        return {
            isBank: isBank,
            label: isBank ? '🏦 Banks' : '🎯 Retailers',
            badge: isBank ? 'Banks' : 'Retailers',
            color: isBank ? (close >= open ? '#2ebd85' : '#f6465d') : '#94a3b8',
            overlayText: isBank ? '🏦 Banks (Institutional Flow)' : '🎯 Retailers (Chop / Traps)',
        };
    }

    function drawBtmVerticalPillBadge(ctx, text, isBank, x, wickY, isAbove) {
        ctx.save();
        ctx.font = 'bold 9px "JetBrains Mono", Inter, monospace';
        const textWidth = ctx.measureText(text).width;
        const pillHeight = Math.ceil(textWidth + 8);
        const pillWidth = 14;
        const stemLength = 8;

        let pillTopY;
        if (isAbove) {
            ctx.beginPath();
            ctx.strokeStyle = isBank ? 'rgba(46, 189, 133, 0.7)' : 'rgba(148, 163, 184, 0.4)';
            ctx.lineWidth = 1;
            ctx.setLineDash([2, 2]);
            ctx.moveTo(x, wickY - 1);
            ctx.lineTo(x, wickY - stemLength);
            ctx.stroke();

            pillTopY = wickY - stemLength - pillHeight;
            if (pillTopY < 6) pillTopY = 6;
        } else {
            ctx.beginPath();
            ctx.strokeStyle = isBank ? 'rgba(46, 189, 133, 0.7)' : 'rgba(148, 163, 184, 0.4)';
            ctx.lineWidth = 1;
            ctx.setLineDash([2, 2]);
            ctx.moveTo(x, wickY + 1);
            ctx.lineTo(x, wickY + stemLength);
            ctx.stroke();

            pillTopY = wickY + stemLength;
            const maxBottom = 550;
            if (pillTopY + pillHeight > maxBottom) pillTopY = maxBottom - pillHeight;
        }

        const pillX = Math.round(x - pillWidth / 2);
        ctx.setLineDash([]);
        ctx.beginPath();
        if (ctx.roundRect) {
            ctx.roundRect(pillX, pillTopY, pillWidth, pillHeight, 3);
        } else {
            ctx.rect(pillX, pillTopY, pillWidth, pillHeight);
        }
        ctx.fillStyle = isBank ? 'rgba(6, 78, 59, 0.92)' : 'rgba(15, 23, 42, 0.92)';
        ctx.fill();
        ctx.strokeStyle = isBank ? 'rgba(46, 189, 133, 0.85)' : 'rgba(148, 163, 184, 0.45)';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.save();
        ctx.translate(x, pillTopY + pillHeight - 4);
        ctx.rotate(-Math.PI / 2);
        ctx.fillStyle = isBank ? '#2ebd85' : '#cbd5e1';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, 0, 0);
        ctx.restore();

        ctx.restore();
    }

    function renderBtmVerticalLiquidityOverlay() {
        if (!btmChart || !btmSeries?.candleSeries || !btmCandles || !btmCandles.length) return;
        const box = document.getElementById('tv_main_single_chart');
        if (!box) return;

        let overlay = document.getElementById('terminal-chart-liq-overlay');
        if (!overlay) {
            overlay = document.createElement('canvas');
            overlay.id = 'terminal-chart-liq-overlay';
            overlay.style.position = 'absolute';
            overlay.style.top = '0';
            overlay.style.left = '0';
            overlay.style.width = '100%';
            overlay.style.height = '100%';
            overlay.style.pointerEvents = 'none';
            overlay.style.zIndex = '2';
            box.style.position = 'relative';
            box.appendChild(overlay);
        }

        const dpr = window.devicePixelRatio || 1;
        const w = box.clientWidth || 960;
        const h = box.clientHeight || 560;
        if (w <= 0 || h <= 0) return;

        if (overlay.width !== Math.floor(w * dpr) || overlay.height !== Math.floor(h * dpr)) {
            overlay.width = Math.floor(w * dpr);
            overlay.height = Math.floor(h * dpr);
        }
        const ctx = overlay.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);

        const timeScale = btmChart.timeScale();
        const candleSeries = btmSeries.candleSeries;
        const stats = btmChartStats || { avgVolume: 100, avgRange: 1 };

        let lastRetailerX = -999;
        let lastBankX = -999;

        for (let i = 0; i < btmCandles.length; i++) {
            const c = btmCandles[i];
            const x = timeScale.timeToCoordinate(c.time);
            if (x === null || x < 15 || x > w - 15) continue;

            const highY = candleSeries.priceToCoordinate(c.high);
            const lowY = candleSeries.priceToCoordinate(c.low);
            if (highY === null || lowY === null) continue;

            const liq = classifyCandleLiquidity(c, stats.avgVolume, stats.avgRange);
            const isLive = (i === btmCandles.length - 1);

            if (isLive) {
                drawBtmVerticalPillBadge(ctx, `● LIVE [${liq.badge}]`, liq.isBank, x, highY, true);
            } else if (liq.isBank) {
                if (x - lastBankX >= 15) {
                    drawBtmVerticalPillBadge(ctx, '🏦 Banks', true, x, highY, true);
                    lastBankX = x;
                }
            } else {
                if (x - lastRetailerX >= 22) {
                    drawBtmVerticalPillBadge(ctx, '🎯 Retailers', false, x, lowY, false);
                    lastRetailerX = x;
                }
            }
        }
    }

    function fmtPrice(val, sym) {
        const num = Number(val);
        if (!Number.isFinite(num)) return '—';
        if ((sym || '').includes('JPY')) return num.toFixed(3);
        if (num >= 1000) return num.toFixed(2);
        if (num >= 10) return num.toFixed(3);
        return num.toFixed(5);
    }

    function fmtLocalBarTime(utcSec, isLiveBar = false) {
        if (!utcSec) return '';
        const d = new Date(Number(utcSec) * 1000);
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const day = String(d.getDate()).padStart(2, '0');
        const mon = months[d.getMonth()];
        const hh = String(d.getHours()).padStart(2, '0');
        const mm = String(d.getMinutes()).padStart(2, '0');
        if (isLiveBar) {
            const now = new Date();
            const ss = String(now.getSeconds()).padStart(2, '0');
            return `${day} ${mon} · ${hh}:${mm}:${ss}`;
        }
        return `${day} ${mon} · ${hh}:${mm}`;
    }

    function calcEMA(candles, period) {
        if (!candles || !candles.length) return [];
        const k = 2 / (period + 1);
        const out = [];
        let ema = candles[0].close;
        for (let i = 0; i < candles.length; i++) {
            ema = i === 0 ? candles[i].close : candles[i].close * k + ema * (1 - k);
            out.push({ time: candles[i].time, value: ema });
        }
        return out;
    }

    function stopBtmStream() {
        if (btmPollTimer) { clearInterval(btmPollTimer); btmPollTimer = null; }
        if (btmHeartbeatTimer) { clearInterval(btmHeartbeatTimer); btmHeartbeatTimer = null; }
        if (btmWs) {
            try { btmWs.onclose = btmWs.onerror = btmWs.onmessage = null; btmWs.close(); } catch (e) {}
            btmWs = null;
        }
        if (btmResizeObs) {
            try { btmResizeObs.disconnect(); } catch (e) {}
            btmResizeObs = null;
        }
        if (btmChart) {
            try { btmChart.remove(); } catch (e) {}
            btmChart = null;
        }
        const oldOverlay = document.getElementById('terminal-chart-liq-overlay');
        if (oldOverlay) {
            try { oldOverlay.remove(); } catch (e) {}
        }
        btmSeries = null;
    }

    function syncControlsUI() {
        if (sel) sel.value = symbol;
        if (tfWrap) {
            tfWrap.querySelectorAll('button[data-int]').forEach(b =>
                b.classList.toggle('active', b.dataset.int === interval)
            );
        }
        if (quickWrap) {
            quickWrap.querySelectorAll('button[data-sym]').forEach(b =>
                b.classList.toggle('active', b.dataset.sym === symbol)
            );
        }
        if (engineWrap) {
            engineWrap.querySelectorAll('button[data-engine]').forEach(b =>
                b.classList.toggle('active', b.dataset.engine === engineMode)
            );
        }
        document.querySelectorAll('.sidebar-sym-btn').forEach(b =>
            b.classList.toggle('active', b.dataset.tvSym === symbol)
        );
        if (activePill) {
            activePill.textContent = `${symbol} · ${INT_LABELS[interval] || interval}`;
        }
        if (ohlcOverlay) {
            ohlcOverlay.style.display = engineMode === 'LIVE' ? 'block' : 'none';
        }
    }

    function updateHeaderAndLegend(bar, prevClose, e20Val, e50Val, isLiveBar = true) {
        if (!bar) return;
        const diff = bar.close - (prevClose ?? bar.open);
        const pct = prevClose ? (diff / prevClose) * 100 : 0;
        const sign = diff >= 0 ? '+' : '';
        const isUp = bar.close >= bar.open;
        const col = isUp ? '#2ebd85' : '#f6465d';
        const timeLabel = fmtLocalBarTime(bar.time, isLiveBar && !btmHovering);

        if (!btmHovering && priceValEl && priceBox && priceArrEl) {
            const wentUp = btmLastPrice === null ? true : bar.close >= btmLastPrice;
            btmLastPrice = bar.close;
            priceValEl.textContent = fmtPrice(bar.close, symbol);
            priceArrEl.textContent = wentUp ? '▲' : '▼';
            priceBox.style.color = wentUp ? '#2ebd85' : '#f6465d';
            priceBox.style.background = wentUp ? 'rgba(46,189,133,0.15)' : 'rgba(246,70,93,0.15)';
            priceBox.style.borderColor = wentUp ? 'rgba(46,189,133,0.4)' : 'rgba(246,70,93,0.4)';
        }

        if (ohlcRow1) {
            ohlcRow1.innerHTML = `
                <span style="color:#f5a524;font-weight:700">${symbol} · ${INT_LABELS[interval] || interval}</span>
                <span style="color:#38bdf8;background:rgba(56,189,248,0.12);padding:1px 6px;border-radius:2px;font-weight:700">🕒 ${timeLabel}</span>
                <span>O <b style="color:${col}">${fmtPrice(bar.open, symbol)}</b></span>
                <span>H <b style="color:${col}">${fmtPrice(bar.high, symbol)}</b></span>
                <span>L <b style="color:${col}">${fmtPrice(bar.low, symbol)}</b></span>
                <span>C <b style="color:${col}">${fmtPrice(bar.close, symbol)}</b></span>
                <span style="color:${col};font-weight:700">${sign}${fmtPrice(diff, symbol)} (${sign}${pct.toFixed(2)}%)</span>
            `;
        }
        if (ohlcRow2) {
            const stats = btmChartStats || { avgVolume: 100, avgRange: 1 };
            const liq = classifyCandleLiquidity(bar, stats.avgVolume, stats.avgRange);
            const flowTag = liq.isBank
                ? `<span style="color:#38bdf8;font-weight:700">💧 Liquidity: <b>🏦 Banks (Institutional Flow)</b></span>`
                : `<span style="color:#94a3b8;font-weight:700">💧 Liquidity: <b>🎯 Retailers (Chop / Traps)</b></span>`;

            ohlcRow2.innerHTML = `
                <span style="color:#3b82f6">EMA 20: <b>${e20Val ? fmtPrice(e20Val, symbol) : '—'}</b></span>
                <span style="color:#f59e0b">EMA 50: <b>${e50Val ? fmtPrice(e50Val, symbol) : '—'}</b></span>
                ${flowTag}
                <span style="color:#8b95a7">Volume: <b>${Math.round(bar.volume || 0).toLocaleString()}</b></span>
            `;
        }
    }

    function isMarketOpen(sym) {
        const s = (sym || '').toUpperCase().replace('/', '');
        const isCrypto = s.includes('BTC') || s.includes('ETH') || s.includes('SOL') ||
                         s.includes('BNB') || s.includes('XRP') || s.includes('DOGE') || s.includes('ADA');
        if (isCrypto) {
            return { isOpen: true, label: 'Market Open 24/7', reopens: null };
        }
        const now = new Date();
        const day = now.getUTCDay(); // 0 = Sun, 5 = Fri, 6 = Sat
        const hour = now.getUTCHours();
        if ((day === 5 && hour >= 21) || (day === 6) || (day === 0 && hour < 21)) {
            return {
                isOpen: false,
                label: 'Market Closed (Weekend)',
                reopens: 'Sun 5:00 PM EST (21:00 UTC)'
            };
        }
        return { isOpen: true, label: 'Market Open', reopens: null };
    }

    function updateCountdown(tfSec) {
        const now = new Date();
        if (clockEl) {
            const hh = String(now.getHours()).padStart(2, '0');
            const mm = String(now.getMinutes()).padStart(2, '0');
            const ss = String(now.getSeconds()).padStart(2, '0');
            clockEl.textContent = `🕒 ${hh}:${mm}:${ss}`;
        }
        if (!countdownEl) return;

        const mkt = isMarketOpen(symbol);
        if (!mkt.isOpen) {
            countdownEl.style.background = 'rgba(239, 68, 68, 0.16)';
            countdownEl.style.color = '#f87171';
            countdownEl.style.borderColor = 'rgba(239, 68, 68, 0.35)';
            countdownEl.textContent = `🔴 MARKET CLOSED (Weekend) · Opens ${mkt.reopens}`;
            return;
        } else {
            countdownEl.style.background = '';
            countdownEl.style.color = '';
            countdownEl.style.borderColor = '';
        }

        const nowSec = Math.floor(now.getTime() / 1000);
        const rem = Math.max(0, tfSec - (nowSec % tfSec));
        const h = Math.floor(rem / 3600);
        const m = Math.floor((rem % 3600) / 60);
        const s = rem % 60;
        const txt = h > 0
            ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
            : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        countdownEl.textContent = `⏱ Next Bar: ${txt}`;
    }

    function applyTickToBtmChart(rawPrice, tfSec, addedVol = 0) {
        if (!btmSeries || !btmCandles.length) return;
        const mkt = isMarketOpen(symbol);
        if (!mkt.isOpen) return; // Freeze: Market closed on weekend for non-crypto
        const { candleSeries, volumeSeries, ema20Series, ema50Series } = btmSeries;

        const isLowP = rawPrice < 10;
        const decimals = symbol.includes('JPY') ? 3 : (isLowP ? 5 : 2);
        const price = Number(rawPrice.toFixed(decimals));

        let lastBar = btmCandles[btmCandles.length - 1];
        const nowUtcSec = Math.floor(Date.now() / 1000);
        const currentBucket = Math.floor(nowUtcSec / tfSec) * tfSec;

        // Roll over to a new bar ONLY when the real clock advances into the very next timeframe bucket
        // and the gap is reasonable (within 2 bars, avoiding generating artificial bars across weekends/halts)
        if (currentBucket > lastBar.time && (currentBucket - lastBar.time) <= tfSec * 2) {
            const newBar = {
                time: currentBucket,
                open: lastBar.close,
                high: Math.max(lastBar.close, price),
                low: Math.min(lastBar.close, price),
                close: price,
                volume: addedVol > 0 ? addedVol : Math.max(1, (lastBar.volume || 100) * 0.02),
            };
            btmCandles.push(newBar);

            lastBar = newBar;
            candleSeries.update(newBar);
            volumeSeries.update({
                time: newBar.time,
                value: newBar.volume,
                color: newBar.close >= newBar.open ? 'rgba(46, 189, 133, 0.28)' : 'rgba(246, 70, 93, 0.28)',
            });
            if (btmLivePriceLine) {
                btmLivePriceLine.applyOptions({
                    price: price,
                    color: '#2ebd85',
                    title: `● LIVE: ${fmtPrice(price, symbol)}`,
                });
            }
            renderBtmVerticalLiquidityOverlay();
        } else {
            lastBar.close = price;
            if (price > lastBar.high) lastBar.high = price;
            if (price < lastBar.low) lastBar.low = price;
            lastBar.volume = (lastBar.volume || 0) + (addedVol > 0 ? addedVol : Math.max(0.2, (lastBar.volume || 50) * 0.003));

            const isBull = lastBar.close >= lastBar.open;
            candleSeries.applyOptions({ priceLineColor: isBull ? '#2ebd85' : '#f6465d' });
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
                color: isBull ? 'rgba(46, 189, 133, 0.28)' : 'rgba(246, 70, 93, 0.28)',
            });

            // ── Real-Time LIVE Price Line (Moves live with each tick) ──
            if (btmLivePriceLine) {
                btmLivePriceLine.applyOptions({
                    price: price,
                    color: isBull ? '#2ebd85' : '#f6465d',
                    title: `● LIVE: ${fmtPrice(price, symbol)}`,
                });
            }

            renderBtmVerticalLiquidityOverlay();
        }

        const e20 = calcEMA(btmCandles, 20).at(-1);
        const e50 = calcEMA(btmCandles, 50).at(-1);
        if (e20) ema20Series.update(e20);
        if (e50) ema50Series.update(e50);

        if (!btmHovering) {
            const prevBar = btmCandles.length > 1 ? btmCandles[btmCandles.length - 2] : lastBar;
            updateHeaderAndLegend(lastBar, prevBar.close, e20?.value, e50?.value, true);
        }
    }

    async function drawLiveLightweightChart() {
        stopBtmStream();
        syncControlsUI();

        const tfCode = INT_TO_TF[interval] || 'H1';
        const tfSec = TF_SECONDS[tfCode] || 3600;
        box.innerHTML = '';

        try {
            const res = await fetch(`/api/market/live-chart/?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(tfCode)}&limit=800&fast=1`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const payload = await res.json();

            const raw = payload.candles || [];
            if (!raw.length || !window.LightweightCharts) {
                return drawExternalTradingViewWidget();
            }

            // Deduplicate candles and ensure ascending pure UTC timestamps
            const sorted = [...raw].sort((a, b) => a.time - b.time);
            const seenTimes = new Set();
            const candleData = [];
            for (const c of sorted) {
                const t = Math.floor(Number(c.time));
                if (!seenTimes.has(t)) {
                    seenTimes.add(t);
                    candleData.push({
                        time: t,
                        open: Number(c.open),
                        high: Number(c.high),
                        low: Number(c.low),
                        close: Number(c.close),
                        volume: Number(c.volume || 0),
                    });
                }
            }
            btmCandles = candleData;

            const lastClose = btmCandles[btmCandles.length - 1].close;
            const precision = symbol.includes('JPY') ? 3 : (lastClose < 10 ? 5 : 2);
            const minMove = Number((1 / Math.pow(10, precision)).toFixed(precision));

            const chart = window.LightweightCharts.createChart(box, {
                width: box.clientWidth || 960,
                height: box.clientHeight || 560,
                layout: {
                    background: { color: '#0b0e13' },
                    textColor: '#8b95a7',
                    fontFamily: "'JetBrains Mono', 'Inter', monospace",
                    fontSize: 11,
                },
                grid: {
                    vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
                    horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
                },
                crosshair: {
                    mode: window.LightweightCharts.CrosshairMode.Normal,
                    vertLine: { color: 'rgba(245, 165, 36, 0.45)', width: 1, style: window.LightweightCharts.LineStyle.Dashed, labelBackgroundColor: '#1a212c' },
                    horzLine: { color: 'rgba(245, 165, 36, 0.45)', width: 1, style: window.LightweightCharts.LineStyle.Dashed, labelBackgroundColor: '#1a212c' },
                },
                rightPriceScale: {
                    borderColor: '#212935',
                    scaleMargins: { top: 0.08, bottom: 0.2 },
                    autoScale: true,
                },
                timeScale: {
                    borderColor: '#212935',
                    timeVisible: true,
                    secondsVisible: tfCode === 'M1' || tfCode === 'M5',
                    rightOffset: 7,
                    barSpacing: 8,
                    minBarSpacing: 1.5,
                },
                handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
                handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
            });

            const volumeSeries = chart.addHistogramSeries({
                priceFormat: { type: 'volume' },
                priceScaleId: '',
            });
            volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
            volumeSeries.setData(btmCandles.map(c => ({
                time: c.time,
                value: c.volume || 0,
                color: c.close >= c.open ? 'rgba(46, 189, 133, 0.25)' : 'rgba(246, 70, 93, 0.25)',
            })));

            const ema20Series = chart.addLineSeries({
                color: '#3b82f6',
                lineWidth: 1.5,
                priceLineVisible: false,
                lastValueVisible: false,
                crosshairMarkerVisible: false,
            });
            const ema50Series = chart.addLineSeries({
                color: '#f59e0b',
                lineWidth: 1.5,
                priceLineVisible: false,
                lastValueVisible: false,
                crosshairMarkerVisible: false,
            });
            const ema20Data = calcEMA(btmCandles, 20);
            const ema50Data = calcEMA(btmCandles, 50);
            ema20Series.setData(ema20Data);
            ema50Series.setData(ema50Data);

            const candleSeries = chart.addCandlestickSeries({
                upColor: '#089981',
                downColor: '#f23645',
                borderUpColor: '#2ebd85',
                borderDownColor: '#f6465d',
                wickUpColor: '#2ebd85',
                wickDownColor: '#f6465d',
                priceLineVisible: true,
                priceLineWidth: 1,
                priceLineStyle: window.LightweightCharts.LineStyle.Dotted,
                lastValueVisible: true,
                priceFormat: { type: 'price', precision: precision, minMove: minMove },
            });
            candleSeries.setData(btmCandles);

            // Draw active signal Entry / SL / TP1 lines if present
            if (payload.direction === 'BUY' || payload.direction === 'SELL') {
                if (payload.entry_price) {
                    candleSeries.createPriceLine({
                        price: Number(payload.entry_price),
                        color: '#38bdf8',
                        lineWidth: 2,
                        lineStyle: window.LightweightCharts.LineStyle.Solid,
                        axisLabelVisible: true,
                        title: `${payload.direction} ENTRY: ${payload.entry_price}`,
                    });
                }
                if (payload.stop_loss) {
                    candleSeries.createPriceLine({
                        price: Number(payload.stop_loss),
                        color: '#f6465d',
                        lineWidth: 2,
                        lineStyle: window.LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: `SL: ${payload.stop_loss}`,
                    });
                }
                if (payload.take_profit_1) {
                    candleSeries.createPriceLine({
                        price: Number(payload.take_profit_1),
                        color: '#2ebd85',
                        lineWidth: 2,
                        lineStyle: window.LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: `TP1: ${payload.take_profit_1}`,
                    });
                }
            }

            // ── Prominent LIVE Price Line (Bottom Chart) ──
            const lastBar = btmCandles[btmCandles.length - 1];
            const prevBar = btmCandles.length > 1 ? btmCandles[btmCandles.length - 2] : lastBar;
            const initBull = lastBar.close >= prevBar.close;
            btmLivePriceLine = candleSeries.createPriceLine({
                price: lastBar.close,
                color: initBull ? '#2ebd85' : '#f6465d',
                lineWidth: 2,
                lineStyle: window.LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `● LIVE: ${fmtPrice(lastBar.close, symbol)}`,
            });

            // ── Institutional Liquidity Classification on ALL Candles (Banks vs Retailers) ──
            const { avgVolume: btmAvgVol, avgRange: btmAvgRange } = computeCandleAverages(btmCandles);
            btmChartStats = { avgVolume: btmAvgVol, avgRange: btmAvgRange };

            // ── Clean Series Markers: Signal Entry Point Only (No horizontal text clutter on candles) ──
            const btmMarkers = [];
            const lastCandle = btmCandles[btmCandles.length - 1];
            if (payload && (payload.direction === 'BUY' || payload.direction === 'SELL') && payload.entry_price) {
                btmMarkers.push({
                    time: lastCandle.time,
                    position: payload.direction === 'BUY' ? 'belowBar' : 'aboveBar',
                    color: payload.direction === 'BUY' ? '#2ebd85' : '#f6465d',
                    shape: payload.direction === 'BUY' ? 'arrowUp' : 'arrowDown',
                    size: 1.2,
                    text: `${payload.direction} @ ${fmtPrice(payload.entry_price, symbol)}`,
                });
            }
            btmCurrentMarkers = btmMarkers;
            candleSeries.setMarkers(btmMarkers);

            // Show ~110 candles initially while keeping all 800+ past candles scrollable/zoomable to the left
            const visibleCount = Math.min(110, btmCandles.length);
            chart.timeScale().setVisibleLogicalRange({
                from: Math.max(0, btmCandles.length - visibleCount),
                to: btmCandles.length + 6,
            });

            // Hook up visible range listeners for real-time vertical overlay rendering
            chart.timeScale().subscribeVisibleLogicalRangeChange(() => renderBtmVerticalLiquidityOverlay());
            chart.timeScale().subscribeVisibleTimeRangeChange(() => renderBtmVerticalLiquidityOverlay());
            setTimeout(renderBtmVerticalLiquidityOverlay, 60);
            setTimeout(renderBtmVerticalLiquidityOverlay, 250);

            btmChart = chart;
            btmSeries = { candleSeries, volumeSeries, ema20Series, ema50Series };
            btmAnchorPrice = lastBar.close;
            btmWsInitPrice = null;
            updateHeaderAndLegend(lastBar, prevBar.close, ema20Data.at(-1)?.value, ema50Data.at(-1)?.value, true);
            updateCountdown(tfSec);

            chart.subscribeCrosshairMove(param => {
                if (!param || !param.time || !param.seriesData) {
                    btmHovering = false;
                    const latest = btmCandles[btmCandles.length - 1];
                    const prev = btmCandles.length > 1 ? btmCandles[btmCandles.length - 2] : latest;
                    if (latest) {
                        updateHeaderAndLegend(
                            latest,
                            prev.close,
                            calcEMA(btmCandles, 20).at(-1)?.value,
                            calcEMA(btmCandles, 50).at(-1)?.value,
                            true
                        );
                    }
                    return;
                }
                const bar = param.seriesData.get(candleSeries);
                if (!bar) return;
                btmHovering = true;
                const e20 = param.seriesData.get(ema20Series)?.value;
                const e50 = param.seriesData.get(ema50Series)?.value;
                const idx = btmCandles.findIndex(c => c.time === bar.time);
                const prevClose = idx > 0 ? btmCandles[idx - 1].close : bar.open;
                const vol = idx >= 0 ? btmCandles[idx].volume : 0;
                const isLast = idx === btmCandles.length - 1;
                updateHeaderAndLegend({ ...bar, volume: vol }, prevClose, e20, e50, isLast);
            });

            btmResizeObs = new ResizeObserver(() => {
                if (btmChart && box.clientWidth > 0) {
                    btmChart.applyOptions({
                        width: box.clientWidth,
                        height: box.clientHeight || 560,
                    });
                }
            });
            btmResizeObs.observe(box);

            // 1. Sub-Second Binance WebSocket Stream
            const wsSym = BINANCE_WS[symbol];
            if (wsSym && window.WebSocket) {
                try {
                    const ws = new WebSocket(`wss://data-stream.binance.vision/ws/${wsSym}@aggTrade`);
                    btmWs = ws;
                    ws.onmessage = evt => {
                        if (!btmChart || !btmSeries || !btmCandles.length) return;
                        try {
                            const msg = JSON.parse(evt.data);
                            const tradePrice = parseFloat(msg.p);
                            if (!Number.isFinite(tradePrice)) return;
                            if (btmWsInitPrice === null) {
                                btmWsInitPrice = tradePrice;
                                btmAnchorPrice = btmCandles[btmCandles.length - 1].close;
                                return;
                            }
                            const pctMove = (tradePrice - btmWsInitPrice) / btmWsInitPrice;
                            const nextP = btmAnchorPrice * (1 + pctMove);
                            applyTickToBtmChart(nextP, tfSec, parseFloat(msg.q) || 0);
                        } catch (e) {}
                    };
                } catch (e) {}
            }

            // 2. Backend 2.5s Live-Tick Poll
            btmPollTimer = setInterval(async () => {
                if (!btmChart || engineMode !== 'LIVE') return;
                try {
                    const r = await fetch(`/api/market/live-tick/?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(tfCode)}`);
                    if (!r.ok) return;
                    const tick = await r.json();
                    if (tick && tick.candle) {
                        btmAnchorPrice = Number(tick.candle.close);
                        btmWsInitPrice = null;
                        if (tick.recent_candles && tick.recent_candles.length) {
                            const latestSrv = tick.recent_candles[tick.recent_candles.length - 1];
                            const srvT = Math.floor(Number(latestSrv.time));
                            const lastLocal = btmCandles[btmCandles.length - 1];
                            if (srvT > lastLocal.time) {
                                const newBar = {
                                    time: srvT,
                                    open: Number(latestSrv.open),
                                    high: Number(latestSrv.high),
                                    low: Number(latestSrv.low),
                                    close: Number(latestSrv.close),
                                    volume: Number(latestSrv.volume || 0),
                                };
                                btmCandles.push(newBar);
                                btmSeries.candleSeries.update(newBar);
                                btmSeries.volumeSeries.update({
                                    time: newBar.time,
                                    value: newBar.volume,
                                    color: newBar.close >= newBar.open ? 'rgba(46, 189, 133, 0.28)' : 'rgba(246, 70, 93, 0.28)',
                                });
                                return;
                            }
                        }
                        applyTickToBtmChart(btmAnchorPrice, tfSec, 0);
                    }
                } catch (e) {}
            }, 2500);

            // 3. 800ms Real-Time Sub-Tick Heartbeat (keeps clock, candle & price line visibly ticking every second)
            btmHeartbeatTimer = setInterval(() => {
                if (!btmChart || !btmCandles.length || engineMode !== 'LIVE') return;
                updateCountdown(tfSec);
                const mkt = isMarketOpen(symbol);
                if (!mkt.isOpen) return; // Freeze on weekend for non-crypto symbols!
                const cur = btmCandles[btmCandles.length - 1];
                const prv = btmCandles.length > 1 ? btmCandles[btmCandles.length - 2] : cur;
                const range = Math.max(
                    Math.abs(cur.high - cur.low),
                    Math.abs(prv.high - prv.low),
                    cur.close * 0.00022
                );
                const anchor = btmAnchorPrice || cur.close;
                const drift = (anchor - cur.close) * 0.35;
                const jitter = (Math.random() - 0.495) * (range * 0.09);
                applyTickToBtmChart(cur.close + drift + jitter, tfSec, 0);
            }, 800);

        } catch (err) {
            console.warn('Live chart fallback to TradingView widget:', err);
            drawExternalTradingViewWidget();
        }
    }

    window.btmChartFitHistory = function () {
        if (btmChart) {
            btmChart.timeScale().fitContent();
        }
    };

    window.btmChartScrollLive = function () {
        if (btmChart && btmCandles.length) {
            const visibleCount = Math.min(100, btmCandles.length);
            btmChart.timeScale().setVisibleLogicalRange({
                from: Math.max(0, btmCandles.length - visibleCount),
                to: btmCandles.length + 6,
            });
        }
    };

    let tvAttempts = 0;
    function drawExternalTradingViewWidget() {
        stopBtmStream();
        syncControlsUI();
        if (ohlcOverlay) ohlcOverlay.style.display = 'none';

        if (!window.TradingView) {
            if (tvAttempts++ < 60) return setTimeout(drawExternalTradingViewWidget, 400);
            box.innerHTML = '<div class="tv-chart-error">TradingView failed to load — check your internet connection.</div>';
            return;
        }

        box.innerHTML = '<div id="tv_main_single_chart" style="width:100%;height:100%;"></div>';
        new window.TradingView.widget({
            autosize: true,
            symbol: TV_SYMBOLS[symbol] || symbol,
            interval: interval,
            timezone: 'Asia/Karachi',
            theme: 'dark',
            style: '1',
            locale: 'en',
            toolbar_bg: '#0b0e13',
            backgroundColor: '#0b0e13',
            gridColor: 'rgba(255,255,255,0.04)',
            enable_publishing: false,
            allow_symbol_change: true,
            hide_side_toolbar: false,
            hide_top_toolbar: false,
            save_image: true,
            withdateranges: true,
            studies: ['MASimple@tv-basicstudies', 'RSI@tv-basicstudies'],
            container_id: 'tv_main_single_chart',
        });
    }

    function drawChart() {
        if (engineMode === 'WIDGET') {
            drawExternalTradingViewWidget();
        } else {
            drawLiveLightweightChart();
        }
    }

    if (sel) {
        sel.addEventListener('change', () => {
            symbol = sel.value;
            localStorage.setItem('ts_tv_symbol', symbol);
            drawChart();
        });
    }
    if (tfWrap) {
        tfWrap.addEventListener('click', e => {
            const b = e.target.closest('button[data-int]');
            if (!b) return;
            interval = b.dataset.int;
            localStorage.setItem('ts_tv_interval', interval);
            drawChart();
        });
    }
    if (quickWrap) {
        quickWrap.addEventListener('click', e => {
            const b = e.target.closest('button[data-sym]');
            if (!b) return;
            symbol = b.dataset.sym;
            localStorage.setItem('ts_tv_symbol', symbol);
            drawChart();
        });
    }
    if (engineWrap) {
        engineWrap.addEventListener('click', e => {
            const b = e.target.closest('button[data-engine]');
            if (!b) return;
            engineMode = b.dataset.engine;
            drawChart();
        });
    }

    window.selectTradingViewSymbol = function (sym, scrollToSection = false) {
        if (!TV_SYMBOLS[sym]) sym = 'XAUUSD';
        symbol = sym;
        localStorage.setItem('ts_tv_symbol', symbol);
        drawChart();
        if (typeof closeMobileSidebar === 'function') closeMobileSidebar();
        if (scrollToSection) {
            const sec = document.getElementById('tv-chart-section');
            if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    };

    window.setTradingViewIntervalFromTf = function (tfCode) {
        const mapped = TF_TO_INT[tfCode];
        if (!mapped) return;
        interval = mapped;
        localStorage.setItem('ts_tv_interval', interval);
        drawChart();
    };

    window.toggleTvFullscreen = function () {
        const sec = document.getElementById('tv-chart-section');
        if (!sec) return;
        sec.classList.toggle('tv-fullscreen');
        setTimeout(drawChart, 100);
    };

    drawChart();
})();
