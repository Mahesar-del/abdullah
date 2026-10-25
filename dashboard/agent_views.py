"""Optional dashboard bridge for the standalone SignalForge project.

SignalForge remains self-contained; this endpoint only exposes a safe, cached
research snapshot to the existing dashboard and never places a trade.
"""
from __future__ import annotations
from pathlib import Path
import sys
import time
from django.http import JsonResponse
from django.views.decorators.http import require_GET

ROOT = Path(__file__).resolve().parent.parent / "SignalForge"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_cache: dict = {"at": 0.0, "data": None}

def get_copilot_context() -> dict:
    """Safe, compact context for the assistant; never exposes credentials or raw data."""
    data=_cache.get("data")
    if not data:
        return {"state":"No SignalForge run has been completed in this dashboard session."}
    return {key:data.get(key) for key in ("status","summary","data_gaps","disclaimer","cards")}

@require_GET
def agent_status(request):
    """Return transparent agent work state. Cached because validation is CPU-heavy."""
    now = time.monotonic()
    if _cache["data"] is not None and now - _cache["at"] < 60:
        return JsonResponse({**_cache["data"], "cached": True})
    try:
        from signalforge.config import Settings
        from signalforge.pipeline import run
        symbol = request.GET.get("symbol", "GOLD").upper()
        # Pipeline itself handles provider failure and labels synthetic fallback.
        report = run(Settings(symbol=symbol), offline=False)
        sig, agents = report["signal"], report["agents"]
        cards = [
            {"name": "Scout", "status": "scouting", "task": f"Collecting {symbol} candles", "progress": 100, "state": agents["collector"]["status"]},
            {"name": "Atlas", "status": "thinking", "task": f"Score {sig['score']:+.2f}: {sig['direction']}", "progress": 100, "state": agents["math"]["status"]},
            {"name": "Sage", "status": "watching", "task": f"Validation: {sig['validation_verdict']}", "progress": 100, "state": agents["validator"]["status"]},
            {"name": "Nova", "status": "briefing", "task": "Checking event and data gaps", "progress": 100, "state": "degraded" if report["data_gaps"] else "ok"},
        ]
        data = {"status": "ok", "cards": cards, "summary": f"SignalForge: {sig['direction']} · {sig['confidence']} confidence · validation {sig['validation_verdict']}", "data_gaps": report["data_gaps"], "disclaimer": report["disclaimer"]}
    except Exception as exc:
        data = {"status": "degraded", "cards": [], "summary": "SignalForge could not complete this run.", "data_gaps": [str(exc)], "disclaimer": "Research, not financial advice."}
    _cache.update(at=now, data=data)
    return JsonResponse(data)
