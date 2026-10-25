"""Agents return serialisable dictionaries and never let an LLM choose direction."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from .data import collect_candles, event_calendar
from .engine import features, score, walk_forward_backtest, scenario

def collector(symbol: str, offline: bool) -> dict:
    return collect_candles(symbol, offline=offline)

def liquidity_agent(df) -> dict:
    f=features(df)
    return {"status":"ok","pressure":f["liquidity"],"r_squared":f["r_squared"],"data_gaps":["DXY/yield/VIX regressors are unavailable in deterministic fallback.","FRED net-liquidity is optional and not loaded."]}

def chart_reader(df) -> dict:
    f=features(df); close=df.close
    return {"status":"ok","physics":{"volatility":f["volatility"],"energy":"high" if f["volatility"]>.008 else "normal"},"math":{"hurst":f["hurst"],"trend_r_squared":f["r_squared"]},"geology":{"support":float(close.tail(60).quantile(.15)),"resistance":float(close.tail(60).quantile(.85))},"history":{"lookalike":"Not loaded: requires long daily archive."},"data_gaps":["No screenshot supplied; visual chart claims cannot be verified."]}

def risk_agent(df, direction: str, account: float, risk_pct: float, horizon: str, event: dict) -> dict:
    f=features(df); entry=float(df.close.iloc[-1]); a=f["atr"]
    if direction=="LONG": stop, target=entry-1.5*a, entry+2.5*a
    elif direction=="SHORT": stop, target=entry+1.5*a, entry-2.5*a
    else: stop=target=entry
    risk_per_unit=abs(entry-stop); size=(account*risk_pct/100/max(risk_per_unit,1e-9)) if direction!="FLAT" else 0
    rr=abs(target-entry)/max(risk_per_unit,1e-9) if direction!="FLAT" else 0
    warnings=[]
    if f["volatility"]>.02: warnings.append("No-trade: extreme volatility percentile proxy.")
    if event.get("events"): warnings.append("No-trade: high-impact event window must be checked.")
    if horizon in ("scalp","intraday"): warnings.append("UNVALIDATED: intraday timing needs 3/4 multi-timeframe alignment.")
    return {"status":"ok","entry":entry,"stop":float(stop),"target":float(target),"size":float(size),"atr":a,"risk_reward":rr,"break_even_win_rate":float(1/(1+rr)) if rr else 1.,"warnings":warnings}

def run_parallel(symbol: str, offline: bool) -> dict:
    with ThreadPoolExecutor(max_workers=2) as pool:
        collect_future=pool.submit(collector,symbol,offline); calendar_future=pool.submit(event_calendar)
        collected, calendar=collect_future.result(),calendar_future.result()
    return {"collector":collected,"calendar":calendar}
