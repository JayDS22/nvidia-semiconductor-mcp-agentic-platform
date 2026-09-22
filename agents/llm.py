"""LLM backend abstraction - routes to NVIDIA Nemotron, Anthropic Claude, or mock.

The `LLM_BACKEND` env var picks the backend (default: auto-detect from available API keys).
"""
from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

BACKEND = (os.getenv("LLM_BACKEND") or "auto").lower()
NVIDIA_KEY = os.getenv("NVIDIA_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def _pick_backend() -> str:
    if BACKEND != "auto":
        return BACKEND
    if NVIDIA_KEY:
        return "nvidia"
    if ANTHROPIC_KEY:
        return "anthropic"
    return "mock"


def chat(system: str, user: str, tools: list[dict] | None = None, temperature: float = 0.2) -> dict[str, Any]:
    """Unified chat interface returning {content: str, tool_calls: list[{name, args}]}."""
    backend = _pick_backend()
    if backend == "nvidia":
        return _nvidia_chat(system, user, tools, temperature)
    if backend == "anthropic":
        return _anthropic_chat(system, user, tools, temperature)
    return _mock_chat(system, user, tools)


# ---------------------------------------------------------------------------
# NVIDIA NIM (Nemotron)
# ---------------------------------------------------------------------------
def _nvidia_chat(system: str, user: str, tools: list[dict] | None, temperature: float) -> dict[str, Any]:
    import requests

    headers = {"Authorization": f"Bearer {NVIDIA_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": 2048,
    }
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]
        payload["tool_choice"] = "auto"

    r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
    if r.status_code == 404:
        raise RuntimeError(
            f"NVIDIA NIM returned 404 for model '{NVIDIA_MODEL}'. "
            f"That model slug isn't live on NIM. Try one of: "
            f"'meta/llama-3.3-70b-instruct' (recommended default), "
            f"'nvidia/llama-3.1-nemotron-70b-instruct', "
            f"'mistralai/mixtral-8x7b-instruct-v0.1'. "
            f"Set NVIDIA_MODEL env var to override."
        )
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        tool_calls.append({"name": tc["function"]["name"], "args": json.loads(tc["function"]["arguments"] or "{}")})
    return {"content": msg.get("content") or "", "tool_calls": tool_calls}


# ---------------------------------------------------------------------------
# Anthropic Claude (dev fallback - validated the code end-to-end during scaffold)
# ---------------------------------------------------------------------------
def _anthropic_chat(system: str, user: str, tools: list[dict] | None, temperature: float) -> dict[str, Any]:
    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_KEY)
    kwargs: dict[str, Any] = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2048,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if tools:
        kwargs["tools"] = [
            {"name": t["name"], "description": t.get("description", ""), "input_schema": t.get("parameters", {"type": "object", "properties": {}})}
            for t in tools
        ]

    resp = client.messages.create(**kwargs)
    content_text = ""
    tool_calls = []
    for block in resp.content:
        if block.type == "text":
            content_text += block.text
        elif block.type == "tool_use":
            tool_calls.append({"name": block.name, "args": dict(block.input) if block.input else {}})
    return {"content": content_text, "tool_calls": tool_calls}


# ---------------------------------------------------------------------------
# Mock backend (no API key set) - deterministic for local testing / CI
# ---------------------------------------------------------------------------
def _mock_chat(system: str, user: str, tools: list[dict] | None) -> dict[str, Any]:
    """Rough heuristic router - good enough to demo the flow without any API key."""
    u = user.lower()
    tool_calls: list[dict] = []

    # naive lot_id / design_id / supplier_id extraction
    import re
    lot_match = re.search(r"w-\d{4}-\d{4}", u)
    design_match = re.search(r"d-\d{4}", u)
    supplier_match = re.search(r"sup-\d{3}", u)

    if "yield" in u and lot_match:
        tool_calls.append({"name": "mes_get_yield", "args": {"lot_id": lot_match.group().upper()}})
    if ("root cause" in u or "why" in u or "drop" in u) and lot_match:
        tool_calls.append({"name": "mes_get_process_steps", "args": {"lot_id": lot_match.group().upper()}})
    if "bom" in u and design_match:
        tool_calls.append({"name": "plm_get_bom", "args": {"design_id": design_match.group().upper()}})
    if "supplier" in u and supplier_match:
        tool_calls.append({"name": "erp_get_supplier", "args": {"supplier_id": supplier_match.group().upper()}})
    if "critical" in u and "risk" in u:
        tool_calls.append({"name": "erp_list_critical_risk_suppliers", "args": {}})
    if "defect" in u and "pattern" in u:
        tool_calls.append({"name": "mes_find_defect_patterns", "args": {}})
    if "impacted" in u or ("if" in u and "fails" in u) and supplier_match:
        tool_calls.append({"name": "plm_list_designs_using_supplier", "args": {"supplier_id": supplier_match.group().upper()}})

    content = "[mock-LLM] Set NVIDIA_API_KEY or ANTHROPIC_API_KEY for real reasoning. Routing to tool(s) based on keyword match." if tool_calls else "[mock-LLM] No tool matched. Try mentioning a lot_id (W-2026-0142), design_id (D-4471), or supplier_id (SUP-013)."
    return {"content": content, "tool_calls": tool_calls}


def backend_name() -> str:
    return _pick_backend()
