from __future__ import annotations
from datetime import datetime, timezone
from .config import Settings
from .agents import run_parallel, liquidity_agent, chart_reader, risk_agent
from .engine import features, score, walk_forward_backtest, scenario

def run(settings: Settings, offline: bool = False) -> dict:
    base=run_parallel(settings.symbol,offline); df=base["collector"]["data"]
    math={"status":"ok",**features(df)}; deterministic=score(math,settings.weights)
    liquidity=liquidity_agent(df); chart=chart_reader(df); validation=walk_forward_backtest(df,settings.weights)
    risk=risk_agent(df,deterministic["direction"],settings.account,settings.risk_pct,settings.horizon,base["calendar"])
    scen=scenario(df,risk["entry"],risk["stop"],risk["target"])
    direction=deterministic["direction"]
    if risk["warnings"] and any("No-trade" in x for x in risk["warnings"]): direction="FLAT"
    confidence="HIGH" if validation["verdict"]=="supported" else "MEDIUM" if validation["verdict"]=="weak" else "LOW"
    if validation["verdict"]=="none": confidence="LOW"
    gaps=base["collector"]["data_gaps"]+base["calendar"]["data_gaps"]+liquidity["data_gaps"]+chart["data_gaps"]
    return {"status":"ok","generated_at":datetime.now(timezone.utc).isoformat(),"disclaimer":"Research, not financial advice. Past performance is not indicative of future results.","signal":{"symbol":settings.symbol,"horizon":settings.horizon,"direction":direction,"score":deterministic["score"],"confidence":confidence,"validation_verdict":validation["verdict"],"entry":risk["entry"],"stop":risk["stop"],"target":risk["target"],"size":risk["size"],"risk_reward":risk["risk_reward"],"break_even_win_rate":risk["break_even_win_rate"],"no_edge_target_before_stop":scen["target_first"],"why":deterministic["contributions"],"warnings":risk["warnings"]},"agents":{"collector":{k:v for k,v in base["collector"].items() if k!="data"},"liquidity":liquidity,"math":math,"chart_reader":chart,"scenario":{k:v for k,v in scen.items() if k!="paths"},"risk":risk,"validator":{k:v for k,v in validation.items() if k not in ("equity","buy_hold","position")}},"data_gaps":gaps,"_frames":{"df":df,"validation":validation,"scenario":scen}}
