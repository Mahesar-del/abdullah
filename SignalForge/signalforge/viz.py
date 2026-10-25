from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt

def signal_card(result: dict, path: Path) -> None:
    df=result["_frames"]["df"]; sig=result["signal"]; valid=result["_frames"]["validation"]; scenario=result["_frames"]["scenario"]
    fig, axes=plt.subplots(2,2,figsize=(13,8),gridspec_kw={"height_ratios":[2,1]}); ax=axes[0,0]
    tail=df.tail(180); ax.plot(tail.index,tail.close,label="price",color="#dbeafe"); ax.plot(tail.index,tail.close.ewm(span=20).mean(),label="EMA20",color="#38bdf8"); ax.plot(tail.index,tail.close.ewm(span=100).mean(),label="EMA100",color="#fbbf24")
    for key,col in [("entry","white"),("stop","#ef4444"),("target","#22c55e")]: ax.axhline(sig[key],color=col,ls="--",label=key)
    ax.legend(fontsize=8);ax.set_title(f"{sig['symbol']} — {sig['direction']} ({sig['confidence']})")
    ax=axes[0,1]; paths=scenario["paths"]; ax.plot(paths.T,color="#818cf8",alpha=.1);ax.axhline(sig["entry"],color="white",ls="--");ax.set_title("Bootstrap scenarios — not forecasts")
    ax=axes[1,0]; c=sig["why"];ax.bar(c.keys(),c.values(),color=["#38bdf8" if x>=0 else "#fb7185" for x in c.values()]);ax.axhline(0,color="white",lw=.5);ax.set_title("Deterministic component contributions")
    ax=axes[1,1];ax.plot(valid["equity"].to_numpy(),label="strategy");ax.plot(valid["buy_hold"].to_numpy(),label="buy & hold");ax.legend();ax.set_title(f"OOS validation: {sig['validation_verdict']}")
    fig.tight_layout();fig.savefig(path,dpi=150,facecolor="#111827");plt.close(fig)

def markdown_report(r:dict)->str:
    s=r["signal"]; v=r["agents"]["validator"]
    return f"# SignalForge report — {s['symbol']}\n\n**{s['direction']}** | Score `{s['score']:.3f}` | Confidence **{s['confidence']}** | Validation **{s['validation_verdict']}**\n\n- Entry / stop / target: `{s['entry']:.2f}` / `{s['stop']:.2f}` / `{s['target']:.2f}`\n- Position size: `{s['size']:.3f}`; R:R `{s['risk_reward']:.2f}`\n- Break-even win rate: `{s['break_even_win_rate']:.1%}`; no-edge target-before-stop bootstrap: `{s['no_edge_target_before_stop']:.1%}`\n- OOS Sharpe: `{v['oos_sharpe']:.2f}`; permutation p: `{v['permutation_p_value']:.3f}`; trades: `{v['trade_count']}`\n\n## Warnings\n"+"\n".join(f"- {x}" for x in s["warnings"]+r["data_gaps"])+f"\n\n{r['disclaimer']}\n"
