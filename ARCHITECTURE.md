# Architecture

## Design goals

1. **MCP as the tool boundary.** Every enterprise system (PLM, MES, ERP) is wrapped as an MCP tool namespace. Agents don't call SQL - they call `mes.get_process_steps(lot_id)`. This keeps agents deployable against any real ERP/MES/PLM backend by swapping the tool implementations.
2. **Agent = domain expertise + tool ownership.** Each agent owns a namespace and knows when to fire which tool. Supervisor routes; agents execute; synthesizer writes the answer.
3. **Deterministic mock data.** Every wafer lot / BOM / supplier is generated from `seed=42`. Same repo, same demo, every time - recruiter clicks and sees identical results.
4. **LLM-backend-agnostic.** Runs on NVIDIA NIM (Nemotron), Anthropic Claude, or a mock router. Zero code changes to swap.

## Agent-to-tool ownership

| Agent | Namespace | Tools |
|---|---|---|
| **Yield Analyst** | MES | `get_yield`, `get_process_steps`, `find_defect_patterns`, `list_lots_for_design` |
| **BOM Verifier** | PLM | `get_bom`, `get_cad_metadata`, `list_suppliers_for_design`, `list_designs_using_supplier` |
| **Root Cause Analyst** | MES + PLM + ERP | all 12 |
| **Recommender** | ERP + PLM | `get_supplier_category_alternatives`, `check_inventory`, all PLM |

Rationale: **narrow ownership prevents tool-call explosion**. Yield Analyst won't accidentally query the ERP; Root Cause has cross-namespace power because that's inherent to RCA.

## Query flow (root-cause example)

Query: *"Why did yield drop on lot W-2026-0142?"*

```
Supervisor
  └─ picks: [root_cause_analyst]
       └─ LLM decides tool sequence:
            1. mes.get_process_steps(lot='W-2026-0142')
               → returns worst_step: 'cmp_planarization' @ 88.2%
            2. mes.get_yield(lot='W-2026-0142')
               → returns supplier assignment: slurry=SUP-006
            3. erp.get_supplier(supplier='SUP-006')
               → returns SlurryMaster-CMP, quality=0.72, risk=0.28
       └─ synthesizer writes:
            "Lot W-2026-0142 (design D-5023) had a final yield of 78.4%
             driven by a CMP planarization drop to 88.2%. Root cause:
             SlurryMaster-CMP (SUP-006) has a lot-risk score of 0.28
             (above the 0.25 critical threshold). Recommend requalifying
             the slurry lot before releasing wafers."
```

## Data schema

**wafer_lots** (SQLite)
- `lot_id, design_id, start_date, complete_date, wafer_count, final_yield, status, photoresist_supplier, etchant_supplier, slurry_supplier`

**process_step_yield** (SQLite)
- `lot_id, step_order, step_name, step_yield, duration_hrs, defect_code, defect_count`

**bom.json** (per design)
- `design_id, revision, process_node_nm, die_size_mm2, bom_parts[{part_id, part_name, supplier_id, quantity_per_wafer, cad_layer}]`

**suppliers.json** (per supplier)
- `supplier_id, name, category, quality_score, lot_risk_score, inventory_days_on_hand, certifications, last_audit_date, critical_risk_flag`

Deliberate correlations in the seeded data:
- SUP-013 (backup photoresist) hurts photolithography step yield when used
- SUP-006 (CMP slurry) occasionally hurts CMP step
- SUP-014 (backup etchant) occasionally hurts etching step
- 3 suppliers exceed the 0.25 critical-risk threshold: SUP-006, SUP-013, SUP-015

These correlations let the demo queries produce non-trivial, real-shaped answers.

## MCP protocol vs in-process

The `TOOL_REGISTRY` in `mcp_server/server.py` supports **both**:

- **In-process dispatch** (default in the Streamlit app) - agents call `call_tool(name, **kwargs)` directly, no network round-trip. Faster demo, no MCP client setup.
- **MCP protocol** (via `python -m mcp_server.server`) - spins up a real FastMCP stdio server, callable from any MCP client (Claude Desktop, Cursor, etc.).

The second mode is what NVIDIA IT would deploy in production - the MCP server runs as a service, and every agent framework (LangGraph, AutoGen, Microsoft Agent Framework, MCP-native tools) can call the same tool surface.

## Extending to production

To swap mock data for a real fab:

1. Replace `mcp_server/tools/plm.py` with calls to your PLM's REST API (Windchill REST, Teamcenter Active Workspace).
2. Replace `mcp_server/tools/mes.py` with your MES query interface (typically Camstar, SAP ME, or a custom SQL warehouse).
3. Replace `mcp_server/tools/erp.py` with SAP BAPI/OData or your ERP's supplier module API.
4. Keep the agent + supervisor code unchanged.
5. Add auth (mTLS + OAuth on the MCP server) and audit logging on every tool call.

## Limitations

- No memory across queries - each query is stateless.
- LLM cost is not tracked in the UI (add `usage.input_tokens * price` per turn for production).
- The supervisor's routing is keyword-based for demo speed; a real deployment would use an LLM-based router with a routing schema.
- Tool schemas are hand-written; a real MCP server auto-generates them from Python function signatures + docstrings via FastMCP.
