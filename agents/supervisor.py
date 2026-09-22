"""LangGraph-style supervisor that routes each user query through a sequence of
specialized agents, collects their tool observations, and returns a final synthesized answer.

Deliberately simple state machine (no LangGraph dependency at runtime — LangGraph
is a design pattern here; the demo runs stateless per query). The four agents each
expose (a) the tools they own and (b) an LLM prompt that decides which tools to fire.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from mcp_server.server import call_tool
from . import llm


# ---------------------------------------------------------------------------
# Tool schemas (fed to the LLM so it knows what's callable)
# ---------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "name": "mes_get_yield",
        "description": "Get final and per-step yield for a wafer lot. Input: lot_id like 'W-2026-0142'.",
        "parameters": {"type": "object", "properties": {"lot_id": {"type": "string"}}, "required": ["lot_id"]},
    },
    {
        "name": "mes_get_process_steps",
        "description": "Full process-step trace for a lot including which step had the lowest yield.",
        "parameters": {"type": "object", "properties": {"lot_id": {"type": "string"}}, "required": ["lot_id"]},
    },
    {
        "name": "mes_find_defect_patterns",
        "description": "Aggregate defect codes across lots (all-time by default). Returns top defects, primary process step, total defect units.",
        "parameters": {"type": "object", "properties": {"top_n": {"type": "integer", "default": 5}}},
    },
    {
        "name": "mes_list_lots_for_design",
        "description": "List all lots produced against a design, optionally filtered by min final yield.",
        "parameters": {"type": "object", "properties": {"design_id": {"type": "string"}, "min_yield": {"type": "number"}}, "required": ["design_id"]},
    },
    {
        "name": "plm_get_bom",
        "description": "Full Bill of Materials for a wafer design. Input: design_id like 'D-4471'.",
        "parameters": {"type": "object", "properties": {"design_id": {"type": "string"}}, "required": ["design_id"]},
    },
    {
        "name": "plm_get_cad_metadata",
        "description": "CAD-level metadata: revision, process node (nm), die size, layer count.",
        "parameters": {"type": "object", "properties": {"design_id": {"type": "string"}}, "required": ["design_id"]},
    },
    {
        "name": "plm_list_suppliers_for_design",
        "description": "Unique suppliers referenced by a design's BOM.",
        "parameters": {"type": "object", "properties": {"design_id": {"type": "string"}}, "required": ["design_id"]},
    },
    {
        "name": "plm_list_designs_using_supplier",
        "description": "Reverse lookup: which wafer designs depend on this supplier?",
        "parameters": {"type": "object", "properties": {"supplier_id": {"type": "string"}}, "required": ["supplier_id"]},
    },
    {
        "name": "erp_get_supplier",
        "description": "Full ERP record for a supplier: category, quality, risk, inventory, certifications.",
        "parameters": {"type": "object", "properties": {"supplier_id": {"type": "string"}}, "required": ["supplier_id"]},
    },
    {
        "name": "erp_check_inventory",
        "description": "Inventory-days-on-hand + shortage risk for a supplier.",
        "parameters": {"type": "object", "properties": {"supplier_id": {"type": "string"}}, "required": ["supplier_id"]},
    },
    {
        "name": "erp_list_critical_risk_suppliers",
        "description": "Every supplier flagged critical_risk (lot_risk > 0.25), sorted worst-first.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "erp_get_supplier_category_alternatives",
        "description": "Suppliers in a category ranked by quality (e.g. category='photoresist').",
        "parameters": {"type": "object", "properties": {"category": {"type": "string"}}, "required": ["category"]},
    },
]

# Tool name -> internal registry key
_TOOL_MAP = {s["name"]: s["name"].replace("_", ".", 1) for s in TOOL_SCHEMAS}


AGENT_SYSTEM_PROMPTS = {
    "yield_analyst": """You are the Yield Analyst agent for a semiconductor fab's Enterprise Agentic AI Platform.
You OWN the MES tools: mes_get_yield, mes_get_process_steps, mes_find_defect_patterns, mes_list_lots_for_design.
Given a user query, call the RIGHT MES tool(s) to gather yield / defect / process-step data. Do NOT call PLM or ERP tools — those belong to other agents.
If the query is not about yield/defects/process steps, respond with no tool calls.""",

    "bom_verifier": """You are the BOM Verifier agent for a semiconductor fab's Enterprise Agentic AI Platform.
You OWN the PLM tools: plm_get_bom, plm_get_cad_metadata, plm_list_suppliers_for_design, plm_list_designs_using_supplier.
Given a user query, call the RIGHT PLM tool(s) to gather BOM / CAD / supplier-mapping data. Do NOT call MES or ERP tools.
If the query is not about BOM/CAD/supplier-mapping, respond with no tool calls.""",

    "root_cause_analyst": """You are the Root Cause Analyst agent for a semiconductor fab's Enterprise Agentic AI Platform.
You have access to ALL tools (MES, PLM, ERP). Your job: given a yield-drop or defect observation, chain 2-3 tool calls to trace the root cause.
Typical chain: mes_get_process_steps(lot) -> identify worst step -> plm_get_bom(design) -> find supplier for that step -> erp_get_supplier(supplier) -> report risk profile.
Return the tool calls. The synthesizer will write the final RCA text.""",

    "recommender": """You are the Recommender agent for a semiconductor fab's Enterprise Agentic AI Platform.
You have access to ALL tools. Your job: given a root cause OR a user question about improving yield / reducing risk, propose concrete actions.
For supplier problems, call erp_get_supplier_category_alternatives to find better options in the same category.
Return tool calls that support your recommendation.""",
}


@dataclass
class AgentTrace:
    agent: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)


@dataclass
class RunResult:
    query: str
    trace: list[AgentTrace] = field(default_factory=list)
    final_answer: str = ""
    backend: str = ""


# ---------------------------------------------------------------------------
# Supervisor routing (simple keyword-based for the demo — LLM-based routing works too but adds latency)
# ---------------------------------------------------------------------------
def _pick_agents(query: str) -> list[str]:
    q = query.lower()

    # Root-cause queries: yield drop + investigate
    if any(k in q for k in ["why", "root cause", "drop", "diagnos"]) and "lot" in q:
        return ["root_cause_analyst"]

    # Recommendation queries
    if any(k in q for k in ["recommend", "improve", "propose", "should i", "which supplier", "alternative"]):
        return ["recommender"]

    # If-fails / impact queries
    if "if" in q and "fail" in q:
        return ["bom_verifier"]  # reverse-lookup via PLM

    # BOM / design queries
    if any(k in q for k in ["bom", "cad", "design", "revision", "layer"]):
        return ["bom_verifier"]

    # Yield / defect queries
    if any(k in q for k in ["yield", "defect", "pattern", "trend"]):
        return ["yield_analyst"]

    # Critical risk queries
    if "critical" in q or ("supplier" in q and "risk" in q):
        return ["yield_analyst", "bom_verifier"]  # combined view

    # Default fallback: root cause (broadest tool access)
    return ["root_cause_analyst"]


def _run_agent(agent_name: str, query: str) -> AgentTrace:
    system = AGENT_SYSTEM_PROMPTS[agent_name]
    resp = llm.chat(system=system, user=query, tools=TOOL_SCHEMAS, temperature=0.1)

    trace = AgentTrace(agent=agent_name, tool_calls=resp["tool_calls"])
    for tc in resp["tool_calls"]:
        internal_name = _TOOL_MAP.get(tc["name"], tc["name"])
        result = call_tool(internal_name, **tc["args"])
        trace.tool_results.append({"tool": tc["name"], "args": tc["args"], "result": result})
    return trace


def _synthesize(query: str, traces: list[AgentTrace]) -> str:
    """Feed all agent observations back to the LLM for a final human-readable answer."""
    context_parts = []
    for t in traces:
        for tr in t.tool_results:
            context_parts.append(f"[{t.agent} -> {tr['tool']}({json.dumps(tr['args'])})] -> {json.dumps(tr['result'], indent=2)}")
    context = "\n\n".join(context_parts) or "No tool observations."

    system = """You are the Synthesizer for the Enterprise Agentic AI Platform.
Given the user's query and the observations gathered by specialized agents, produce a concise, PM-readable answer.
- Cite specific numbers from the observations (yields, defect counts, supplier scores).
- If a root cause is evident, name it AND the process step + supplier.
- End with a one-line recommended action if appropriate.
- No markdown headers. Plain prose."""

    user = f"USER QUERY: {query}\n\nAGENT OBSERVATIONS:\n{context}"
    resp = llm.chat(system=system, user=user, tools=None, temperature=0.3)
    return resp["content"]


def run(query: str) -> RunResult:
    """End-to-end: pick agents -> run them -> synthesize final answer."""
    agents = _pick_agents(query)
    traces = [_run_agent(a, query) for a in agents]

    # If the initial agents' tool_results include a lot with a worst step, chain to Root Cause automatically
    if agents == ["yield_analyst"]:
        for t in traces:
            for tr in t.tool_results:
                r = tr["result"]
                if isinstance(r, dict) and r.get("step_yields"):
                    worst = min(r["step_yields"], key=lambda s: s["step_yield"])
                    if worst["step_yield"] < 0.94:
                        # chain into root cause
                        follow_up = f"Yield dropped at step '{worst['step_name']}' on lot {r['lot_id']} (design {r.get('design_id','?')}). Trace root cause via BOM + supplier."
                        traces.append(_run_agent("root_cause_analyst", follow_up))
                        break

    final = _synthesize(query, traces)
    return RunResult(query=query, trace=traces, final_answer=final, backend=llm.backend_name())
