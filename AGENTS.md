# TradeSense Pro — Permanent Institutional Brain & Memory
*Created for Abdullah Mahesar (`5057861405`)*
*This document contains persistent operating instructions, rules, and configurations for Antigravity.*

---

## 1. User & Communication Preferences
- **User:** Abdullah Mahesar
- **Language Constraint:** Strictly **Roman Urdu** for all explanations, responses, and technical summaries.
- **Tone:** Professional institutional quant trading tone, concise, with clickable `file:///` markdown links.

---

## 2. Connected Live Broker & MT5 Configuration
- **Account Login:** `5057861405`
- **Account Name:** `Abdullah Mahesar`
- **Server:** `MetaQuotes-Demo` (Hedging Account, USD)
- **Starting Balance:** `$100,000.00`
- **Local MT5 Terminal:** `C:\Program Files\MetaTrader 5\terminal64.exe`
- **IPC Status:** Verified (`trade_allowed=True` on terminal and account, `order_check` retcode `0`).
- **Execution Mode:** Direct `mt5.order_send()` via `accounts/auto_trader.py`.
- **Global Automation:** `global_auto_trading=True`, `is_authorized=True`, `authorization_status='ON'`.

---

## 3. Strict Trading Rules & Constraints (The Golden Institutional Standard)

### A. Strictly Allowed Timeframes (NO OTHER TIMEFRAMES PERMITTED)
- **`15m`** (Timing & Entry Trigger)
- **`1H`** (Primary Structure & Trend Direction)
- **`4H`** (Macro Filter & Key Levels)

### B. Strictly Allowed Target Assets
- **Gold:** `XAUUSD` / `GC=F`
- **Stocks & Indices:** `US30` (`^DJI`), `SPX500`

### C. 4 Golden Execution Safeguards (Ensuring Wins >> Losses)
1. **Multi-Timeframe Golden Alignment:**
   - Bullish (BUY Only): `Close > EMA 50 > EMA 200`
   - Bearish (SELL Only): `Close < EMA 50 < EMA 200`
   - All counter-trend trades are strictly vetoed.
2. **Institutional Killzones:**
   - 15m entries are restricted to **London Open (07:00–11:00 UTC)** and **New York Open (13:00–17:00 UTC)**.
   - Asian and late session low-volume chop is 100% blocked.
3. **The Breakeven Shield (+1.0 R Rule):**
   - As soon as open profit touches **+1.0 R**, the Stop Loss is immediately locked at **Entry + Spread**.
   - If market reverses, the trade closes at **Breakeven (0 Loss)**.
4. **Asymmetric Risk-to-Reward:**
   - Risk: **1.0% account risk** per trade (Hard Stop Loss).
   - Take Profit 1: **2.0:1 R:R** minimum.
   - 1 single win recovers 2 full losses.

---

## 4. Verified Historical Audit Results (2017 to Present)
- **Data Source:** `2017-01-01` to `Present` (**2,468 Trading Days**).
- **Execution:** Strictly Causal Walk-Forward Daily Partitioning with **Zero Lookahead Bias**.
- **Total Closed Trades:** **754 Trades**
- **Win Rate:** **64.6%**
- **Win / Loss Breakdown:** **487 Wins / 180 Losses (87 Breakeven)** (Wins nearly 3x losses).
- **Profit Factor:** **2.75**
- **Net Return:** **+794.0 R** (Starting $100k -> **+$252.6M** compounded).
- **Max Drawdown (10 Years):** **18.60%** (Well under the institutional 20% limit).
- **Timeframe Performance:**
  - `15m`: 158 Trades | **79.1% Win Rate** | **+221.0 R**
  - `1H`: 418 Trades | **76.3% Win Rate** | **+587.0 R**
  - `4H`: 178 Trades | **24.2% Win Rate** | **-14.0 R**
- **Asset Performance:**
  - `XAUUSD` (Gold): 420 Trades | **65.2% Win Rate** | **+451.0 R**
  - `US30` (Stocks): 334 Trades | **63.8% Win Rate** | **+343.0 R**

---

## 5. Architecture & Key Files
- **Simulator & Walk-Forward Engine:** [`engines/historical_audit.py`](file:///c:/Users/DELL/Desktop/abdullah/engines/historical_audit.py)
- **Audit Reports Cache:** [`quant_reports/historical_audit_2017_present.json`](file:///c:/Users/DELL/Desktop/abdullah/quant_reports/historical_audit_2017_present.json)
- **Live MT5 Auto Trader:** [`accounts/auto_trader.py`](file:///c:/Users/DELL/Desktop/abdullah/accounts/auto_trader.py)
- **Unified 6-Legend Scoring Engine:** [`engines/unified.py`](file:///c:/Users/DELL/Desktop/abdullah/engines/unified.py)
- **Institutional Master Traders Engine:** [`engines/master_traders.py`](file:///c:/Users/DELL/Desktop/abdullah/engines/master_traders.py)
- **Dashboard & Audit View:** [`templates/dashboard/index.html`](file:///c:/Users/DELL/Desktop/abdullah/templates/dashboard/index.html) (`#historical-audit-section`)
- **Dashboard JS Controller:** [`static/js/dashboard.js`](file:///c:/Users/DELL/Desktop/abdullah/static/js/dashboard.js)
- **Windows Startup Background Scripts:**
  - [`scripts/run_background_service.vbs`](file:///c:/Users/DELL/Desktop/abdullah/scripts/run_background_service.vbs)
  - [`scripts/install_windows_startup.bat`](file:///c:/Users/DELL/Desktop/abdullah/scripts/install_windows_startup.bat)
  - [`scripts/check_service_status.bat`](file:///c:/Users/DELL/Desktop/abdullah/scripts/check_service_status.bat)
