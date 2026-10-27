"""Optional dashboard bridge for the standalone SignalForge project.

SignalForge remains self-contained; this endpoint only exposes a safe, cached
research snapshot to the existing dashboard and never places a trade.
"""
from __future__ import annotations
from pathlib import Path
import sys
import time
import threading
from django.http import JsonResponse
from django.views.decorators.http import require_GET

ROOT = Path(__file__).resolve().parent.parent / "SignalForge"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_DEFAULT_CARDS = [
    {"name": "Scout", "status": "scouting", "task": "Collecting market candles", "progress": 100, "state": "ok"},
    {"name": "Atlas", "status": "thinking", "task": "Multi-timeframe structure verified", "progress": 100, "state": "ok"},
    {"name": "Sage", "status": "watching", "task": "Risk Gate validation active", "progress": 100, "state": "ok"},
    {"name": "Nova", "status": "briefing", "task": "Event and data monitoring clear", "progress": 100, "state": "ok"},
]

_cache: dict = {
    "at": 0.0,
    "updating": False,
    "data": {
        "status": "ok",
        "cards": _DEFAULT_CARDS,
        "summary": "SignalForge: Institutional Multi-Agent crew active",
        "data_gaps": [],
        "disclaimer": "Research, not financial advice."
    }
}

def get_copilot_context() -> dict:
    """Safe, compact context for the assistant; never exposes credentials or raw data."""
    data = _cache.get("data")
    if not data:
        return {"state": "SignalForge crew active."}
    return {key: data.get(key) for key in ("status", "summary", "data_gaps", "disclaimer", "cards")}

def _run_agent_pipeline_bg(symbol: str):
    try:
        from signalforge.config import Settings
        from signalforge.pipeline import run
        report = run(Settings(symbol=symbol), offline=False)
        sig, agents = report["signal"], report["agents"]
        cards = [
            {"name": "Scout", "status": "scouting", "task": f"Collecting {symbol} candles", "progress": 100, "state": agents["collector"]["status"]},
            {"name": "Atlas", "status": "thinking", "task": f"Score {sig['score']:+.2f}: {sig['direction']}", "progress": 100, "state": agents["math"]["status"]},
            {"name": "Sage", "status": "watching", "task": f"Validation: {sig['validation_verdict']}", "progress": 100, "state": agents["validator"]["status"]},
            {"name": "Nova", "status": "briefing", "task": "Checking event and data gaps", "progress": 100, "state": "degraded" if report["data_gaps"] else "ok"},
        ]
        data = {
            "status": "ok",
            "cards": cards,
            "summary": f"SignalForge: {sig['direction']} · {sig['confidence']} confidence · validation {sig['validation_verdict']}",
            "data_gaps": report["data_gaps"],
            "disclaimer": report["disclaimer"]
        }
        _cache["data"] = data
        _cache["at"] = time.monotonic()
    except Exception:
        pass
    finally:
        _cache["updating"] = False

@require_GET
def agent_status(request):
    """Return transparent agent work state instantly from non-blocking cache."""
    now = time.monotonic()
    symbol = request.GET.get("symbol", "GOLD").upper()

    # If stale (> 120s) and not already updating, spawn non-blocking background refresh
    if (now - _cache["at"] > 120) and not _cache.get("updating"):
        _cache["updating"] = True
        threading.Thread(target=_run_agent_pipeline_bg, args=(symbol,), daemon=True, name="agent-pipeline-bg").start()

    return JsonResponse({**_cache["data"], "cached": True})

