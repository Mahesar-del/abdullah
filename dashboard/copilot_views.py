"""Grounded Claude assistant for explaining the SignalForge dashboard.

The model can explain supplied system state but cannot trade, alter scoring,
or invent market facts. No request is sent to Claude until a configured key is
present.
"""
from __future__ import annotations
import json
import os
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from . import agent_views

SYSTEM = """You are SignalForge Copilot, a fast and careful assistant inside a market-research dashboard.
Answer questions about the system, its agents, signal fields, data gaps, and current research state in simple English; add a short Roman-Urdu summary when useful.
Use only the supplied context for live facts. If context is missing, say so. Never promise profit, give personalised investment advice, invent prices, or change the deterministic signal direction. Clearly label research limitations and say 'research, not financial advice' for market guidance. Be concise."""

def free_system_reply(question: str, context: dict) -> str:
    """No-cost, grounded fallback that never pretends to be an LLM."""
    q = question.lower()
    summary = context.get("summary", "No SignalForge run has completed yet.")
    gaps = context.get("data_gaps", [])
    gap_text = "; ".join(gaps[:2]) or "No data gaps reported."
    cards = context.get("cards", [])
    agents = ", ".join(f"{c.get('name')}: {c.get('task')}" for c in cards) or "Agents have not reported in yet."
    if any(word in q for word in ("agent", "bot", "working", "doing", "kaam")):
        answer = f"Current agent work: {agents}. The agents are research helpers; they do not place trades."
    elif any(word in q for word in ("signal", "long", "short", "score", "trade")):
        answer = f"Current deterministic research state: {summary}. Direction is produced by the scoring engine, not this assistant. Research, not financial advice."
    elif any(word in q for word in ("valid", "backtest", "weak", "confidence")):
        answer = f"Validation status: {summary}. A weak or none verdict means the system should reduce confidence; no validation claim is invented."
    elif any(word in q for word in ("data", "gap", "error", "missing")):
        answer = f"Current data gaps: {gap_text}. The system reports gaps rather than guessing."
    else:
        answer = f"I am the free local SignalForge Guide. {summary} Ask about agents, validation, data gaps, score, or how the dashboard works."
    return answer + " Roman Urdu: yeh research system hai, profit ki guarantee nahi."

@require_POST
@csrf_protect
def copilot_chat(request):
    try:
        body=json.loads(request.body.decode("utf-8")); question=str(body.get("message", "")).strip(); history=body.get("history", [])[-8:]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error":"Invalid request."},status=400)
    if not question or len(question)>3000:
        return JsonResponse({"error":"Please send a question under 3,000 characters."},status=400)
    if not os.getenv("ANTHROPIC_API_KEY"):
        return JsonResponse({"status":"free_local","provider":"SignalForge Guide (free)","answer":free_system_reply(question, agent_views.get_copilot_context())})
    try:
        from anthropic import Anthropic
        context=agent_views.get_copilot_context()
        messages=[]
        for item in history:
            role=item.get("role"); content=str(item.get("content", ""))[:3000]
            if role in ("user","assistant") and content: messages.append({"role":role,"content":content})
        messages.append({"role":"user","content":f"<system_context>{json.dumps(context,default=str)}</system_context>\n\nQuestion: {question}"})
        client=Anthropic(); response=client.messages.create(model=os.getenv("CLAUDE_MODEL","claude-sonnet-4-5-20250929"),max_tokens=700,system=SYSTEM,messages=messages)
        answer="".join(block.text for block in response.content if block.type=="text")
        return JsonResponse({"status":"ok","answer":answer,"provider":"Claude"})
    except Exception as exc:
        return JsonResponse({"status":"degraded","answer":"Claude could not answer right now. Check the API key, model access, and connection; no market information was invented.","detail":str(exc)[:240]})
