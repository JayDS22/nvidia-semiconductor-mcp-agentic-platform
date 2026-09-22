"""Streamlit UI for the Semiconductor Manufacturing MCP + Agentic Platform PoC.

Layout:
- Sidebar:   backend indicator, wafer lot picker, yield trend chart, 10 canonical demo queries.
- Main:      chat interface (user query -> agent trace -> synthesized answer).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Ensure repo root importable when Streamlit runs from arbitrary CWD
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from agents import llm, supervisor  # noqa: E402
from mcp_server.server import ensure_seeded  # noqa: E402
from mcp_server.data.seed_wafers import DB_PATH  # noqa: E402

ensure_seeded()

st.set_page_config(
    page_title="Semiconductor Manufacturing Agentic AI Platform",
    page_icon="🔬",
    layout="wide",
)

CANONICAL_QUERIES = [
    "Why did yield drop on lot W-2026-0142?",
    "Which supplier lot has the highest risk this month?",
    "For die design D-4471, list all BOM parts and their current supplier lots.",
    "What defect pattern appears most in Q3?",
    "If supplier SUP-013 (backup photoresist) fails, what wafer designs are impacted?",
    "Recommend BOM changes to improve yield on D-4471.",
    "Show me the process-step correlation with defect rate for lot W-2026-0142.",
    "Which suppliers are on my critical-risk list right now?",
    "Draft an RCA note for the W-2026-0142 incident.",
    "What is the yield trend for design D-5023?",
]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🔬 Fab Ops Console")

    backend = llm.backend_name()
    backend_emoji = {"nvidia": "🟢", "anthropic": "🟢", "mock": "🟡"}[backend]
    st.caption(f"{backend_emoji} LLM backend: **{backend}**")
    if backend == "mock":
        st.warning("Set `NVIDIA_API_KEY` or `ANTHROPIC_API_KEY` in `.env` for real reasoning.")

    st.divider()

    st.subheader("Yield Dashboard")
    con = sqlite3.connect(DB_PATH)
    lots_df = pd.read_sql(
        "SELECT lot_id, design_id, start_date, final_yield, status FROM wafer_lots ORDER BY start_date",
        con,
    )
    con.close()

    design = st.selectbox("Filter by design", ["(all)"] + sorted(lots_df["design_id"].unique().tolist()))
    filt = lots_df if design == "(all)" else lots_df[lots_df["design_id"] == design]

    fig = px.line(
        filt.assign(start_date=pd.to_datetime(filt["start_date"])),
        x="start_date", y="final_yield", color="design_id",
        title="Final yield over time",
        markers=True,
    )
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10), showlegend=(design == "(all)"))
    fig.update_yaxes(range=[0.6, 1.0], tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

    st.caption(f"{len(filt)} lots in view · median yield {filt['final_yield'].median():.1%}")

    st.divider()
    st.subheader("Try a canonical query")
    for i, q in enumerate(CANONICAL_QUERIES, 1):
        if st.button(f"Q{i}. {q[:52] + '…' if len(q) > 52 else q}", key=f"cq{i}", use_container_width=True):
            st.session_state.pending_query = q


# ---------------------------------------------------------------------------
# Main pane
# ---------------------------------------------------------------------------
st.title("Enterprise Agentic AI Platform for Semiconductor Manufacturing")
st.caption("MCP-based multi-agent PoC · Yield analysis · BOM verification · Root cause · Recommendations")

with st.expander("What this is", expanded=False):
    st.markdown(
        """
**A 4-agent LangGraph system fronting an MCP server** with three enterprise tool namespaces:

- **PLM** (Windchill-shape): CAD/BOM metadata + supplier mappings per wafer design
- **MES**: yield + process-step data + defect patterns across wafer lots
- **ERP** (SAP-shape): supplier records, inventory-days-on-hand, risk scores

**Agents:** *Yield Analyst · BOM Verifier · Root Cause Analyst · Recommender.*
The Supervisor routes each query to the right agent, tools are called via MCP,
observations are synthesized into a PM-readable answer.

**Data:** 60 wafer lots × 8 process steps × 15 suppliers × 5 wafer designs, generated deterministically (seed=42) on server start.
        """
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("trace"):
            with st.expander("🔍 Agent trace"):
                for t in msg["trace"]:
                    st.markdown(f"**{t['agent']}** → called {len(t['tool_results'])} tool(s)")
                    for tr in t["tool_results"]:
                        with st.container():
                            st.code(f"{tr['tool']}({json.dumps(tr['args'])})", language="python")
                            st.json(tr["result"], expanded=False)

query = st.chat_input("Ask about yield, BOM, suppliers, defects…")
if not query and "pending_query" in st.session_state:
    query = st.session_state.pop("pending_query")

if query:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("Agents reasoning…"):
            try:
                result = supervisor.run(query)
                answer = result.final_answer or "_(no synthesized answer)_"
                trace_serial = [
                    {"agent": t.agent, "tool_calls": t.tool_calls, "tool_results": t.tool_results}
                    for t in result.trace
                ]
                st.markdown(answer)
                if trace_serial:
                    with st.expander("🔍 Agent trace"):
                        for t in trace_serial:
                            st.markdown(f"**{t['agent']}** → called {len(t['tool_results'])} tool(s)")
                            for tr in t["tool_results"]:
                                st.code(f"{tr['tool']}({json.dumps(tr['args'])})", language="python")
                                st.json(tr["result"], expanded=False)
                st.session_state.messages.append({"role": "assistant", "content": answer, "trace": trace_serial})
            except Exception as e:
                err = f"⚠️ Error: `{type(e).__name__}: {e}`"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err, "trace": []})
