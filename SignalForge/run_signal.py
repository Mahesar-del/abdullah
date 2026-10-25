from __future__ import annotations
import argparse, json, os, time
from pathlib import Path
from signalforge.config import Settings
from signalforge.pipeline import run
from signalforge.viz import signal_card, markdown_report

def save(result: dict) -> Path:
    out=Path("outputs");out.mkdir(exist_ok=True); stamp=time.strftime("%Y%m%d_%H%M%S"); stem=out/f"signal_{stamp}"
    public={k:v for k,v in result.items() if k!="_frames"}; (stem.with_suffix(".json")).write_text(json.dumps(public,indent=2,default=str),encoding="utf-8")
    (stem.with_suffix(".md")).write_text(markdown_report(result),encoding="utf-8"); signal_card(result,stem.with_suffix(".png")); return stem

def main() -> None:
    p=argparse.ArgumentParser(description="SignalForge — deterministic research, not financial advice")
    p.add_argument("symbol",nargs="?",default="GOLD");p.add_argument("--horizon",choices=["scalp","intraday","swing"],default="swing");p.add_argument("--account",type=float,default=5000);p.add_argument("--risk",type=float,default=1);p.add_argument("--watch",type=int);p.add_argument("--no-llm",action="store_true");p.add_argument("--no-chart",action="store_true");p.add_argument("--offline",action="store_true")
    a=p.parse_args(); previous=None
    while True:
        r=run(Settings(a.symbol.upper(),a.horizon,a.account,a.risk),a.offline); compact={k:r["signal"][k] for k in ("direction","score","confidence","validation_verdict")}
        if compact!=previous: print(json.dumps(compact,indent=2)); print("Saved:",save(r)); previous=compact
        if not a.watch: break
        time.sleep(max(1,a.watch))
if __name__=="__main__": main()
