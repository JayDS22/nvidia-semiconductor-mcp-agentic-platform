"""FastMCP server exposing PLM + MES + ERP tool namespaces to LangGraph agents.

Also usable in-process (no MCP protocol) via the imported module-level functions -
LangGraph agents call these directly for lower latency in the demo.
"""
from __future__ import annotations

from .data.seed_wafers import BOM_PATH, DB_PATH, SUPPLIERS_PATH, seed_all
from .tools import erp, mes, plm


def ensure_seeded() -> None:
    """Regenerate mock data if any file is missing. Idempotent, called by app on startup."""
    if not (DB_PATH.exists() and BOM_PATH.exists() and SUPPLIERS_PATH.exists()):
        seed_all()


# ---- Direct tool dispatch table (used by LangGraph agents) ----
TOOL_REGISTRY = {
    # PLM
    "plm.get_bom": plm.get_bom,
    "plm.get_cad_metadata": plm.get_cad_metadata,
    "plm.list_suppliers_for_design": plm.list_suppliers_for_design,
    "plm.list_designs_using_supplier": plm.list_designs_using_supplier,
    # MES
    "mes.get_yield": mes.get_yield,
    "mes.get_process_steps": mes.get_process_steps,
    "mes.find_defect_patterns": mes.find_defect_patterns,
    "mes.list_lots_for_design": mes.list_lots_for_design,
    # ERP
    "erp.get_supplier": erp.get_supplier,
    "erp.check_inventory": erp.check_inventory,
    "erp.list_critical_risk_suppliers": erp.list_critical_risk_suppliers,
    "erp.get_supplier_category_alternatives": erp.get_supplier_category_alternatives,
}


def call_tool(name: str, **kwargs) -> dict:
    """Direct tool dispatch - used by agents. Returns error dict if tool unknown."""
    if name not in TOOL_REGISTRY:
        return {"error": f"unknown tool: {name}", "available": list(TOOL_REGISTRY.keys())}
    try:
        return TOOL_REGISTRY[name](**kwargs)
    except TypeError as e:
        return {"error": f"bad arguments to {name}: {e}"}


# ---- MCP protocol server (optional - for real MCP clients) ----
def build_mcp_server():
    """Build a FastMCP-compatible server exposing all tools.

    Deferred import so the app runs even without fastmcp installed.
    """
    from fastmcp import FastMCP

    mcp = FastMCP("semiconductor-manufacturing-platform")

    for tool_name, fn in TOOL_REGISTRY.items():
        # FastMCP uses the function's docstring + signature for tool schema
        mcp.tool(name=tool_name.replace(".", "_"))(fn)

    return mcp


if __name__ == "__main__":
    ensure_seeded()
    server = build_mcp_server()
    server.run()  # stdio transport by default
