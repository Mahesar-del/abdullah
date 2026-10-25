"""Offline acceptance test: no network and creates JSON, Markdown, PNG."""
import os, json
from pathlib import Path
from signalforge.config import Settings
from signalforge.pipeline import run
from signalforge.viz import signal_card, markdown_report

os.environ["SIGNALFORGE_OFFLINE"]="1"
r=run(Settings(),offline=True); out=Path("outputs");out.mkdir(exist_ok=True)
public={k:v for k,v in r.items() if k!="_frames"};(out/"selftest.json").write_text(json.dumps(public,indent=2,default=str));(out/"selftest.md").write_text(markdown_report(r));signal_card(r,out/"selftest.png")
assert r["signal"]["validation_verdict"] in {"supported","weak","none"}
assert (out/"selftest.json").exists() and (out/"selftest.md").exists() and (out/"selftest.png").exists()
print("PASS: offline pipeline produced JSON, Markdown and PNG.")
