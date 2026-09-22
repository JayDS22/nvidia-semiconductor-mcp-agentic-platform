# Enterprise Agentic AI Platform for Semiconductor Manufacturing

**A working PoC of an MCP-based multi-agent system for wafer yield analysis, BOM verification, and supplier risk.** Built as a reference architecture for enterprise IT teams shipping agentic AI into fab operations.

**Live demo:** _(deployed on Hugging Face Spaces — link at top of the repo)_

**Stack:** Python 3.11 · LangGraph-shape supervisor · MCP server (FastMCP) · NVIDIA Nemotron via NIM (with Claude fallback) · SQLite + JSON mock data · Streamlit UI

---

## Why this exists

Modern semiconductor fabs run on three enterprise systems that don't talk to each other well:
- **PLM** (Windchill / Teamcenter) — CAD + Bill of Materials
- **MES** — yield and process-step data per wafer lot
- **ERP** (SAP) — supplier records + inventory + risk

An engineer investigating a yield drop today has to open three tools. An agentic AI copilot with tool access to all three collapses the loop into one query.

This PoC demonstrates that pattern with realistic mock data (60 wafer lots × 8 process steps × 15 suppliers × 5 wafer designs), a 4-agent LangGraph-shape supervisor, and an MCP server exposing three tool namespaces.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Streamlit UI  (chat + yield dashboard + agent trace)       │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Supervisor  (routes to specialized agents)                 │
│  ┌──────────────┬──────────────┬──────────────┬───────────┐│
│  │ Yield        │ BOM          │ Root Cause   │ Recommend ││
│  │ Analyst      │ Verifier     │ Analyst      │ Agent     ││
│  └──────────────┴──────────────┴──────────────┴───────────┘│
└─────────────────────────────────────────────────────────────┘
                          │  (MCP protocol)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  MCP Server (FastMCP, 12 tools across 3 namespaces)         │
│  ┌────────────────┬────────────────┬────────────────────┐  │
│  │ PLM (4 tools)  │ MES (4 tools)  │ ERP (4 tools)      │  │
│  │  get_bom       │  get_yield     │  get_supplier      │  │
│  │  cad_metadata  │  process_steps │  check_inventory   │  │
│  │  suppliers_for │  defect_patts  │  critical_risk     │  │
│  │  designs_using │  lots_for_dsgn │  category_alts     │  │
│  └────────────────┴────────────────┴────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  Mock data (seeded, deterministic)                          │
│  wafer_lots.db · bom.json · suppliers.json                  │
└─────────────────────────────────────────────────────────────┘
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the deeper technical writeup.

---

## Quick start (local)

```bash
git clone https://github.com/JayDS22/nvidia-semiconductor-mcp-agentic-platform
cd nvidia-semiconductor-mcp-agentic-platform
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set at least one LLM key (free tier available for both)
cp .env.example .env
# edit .env: set NVIDIA_API_KEY (from build.nvidia.com) OR ANTHROPIC_API_KEY

streamlit run app/streamlit_app.py
# opens http://localhost:8501
```

Without an API key, the app runs on the mock LLM backend — tool routing works via keyword match, but synthesized prose is placeholder text.

---

## Deploy to Hugging Face Spaces (free tier, no cold-start)

```bash
# One-time: install HF CLI + log in
pip install huggingface_hub
huggingface-cli login

# Create + push
huggingface-cli repo create nvidia-semiconductor-mcp-agentic-platform --type space --space_sdk streamlit
git remote add hf https://huggingface.co/spaces/<your-username>/nvidia-semiconductor-mcp-agentic-platform
git push hf main

# In HF Space settings: add NVIDIA_API_KEY (or ANTHROPIC_API_KEY) as a Secret.
```

Live URL: `https://huggingface.co/spaces/<your-username>/nvidia-semiconductor-mcp-agentic-platform`

---

## 10 canonical queries (recruiter-facing demo)

Every query is pre-loaded in the sidebar — click and go.

1. Why did yield drop on lot W-2026-0142?
2. Which supplier lot has the highest risk this month?
3. For die design D-4471, list all BOM parts and their current supplier lots.
4. What defect pattern appears most in Q3?
5. If supplier SUP-013 fails, what wafer designs are impacted?
6. Recommend BOM changes to improve yield on D-4471.
7. Show me the process-step correlation with defect rate for lot W-2026-0142.
8. Which suppliers are on my critical-risk list right now?
9. Draft an RCA note for the W-2026-0142 incident.
10. What is the yield trend for design D-5023?

---

## Repo layout

```
nvidia-semiconductor-mcp-agentic-platform/
├── README.md
├── ARCHITECTURE.md
├── requirements.txt
├── .env.example
├── mcp_server/
│   ├── server.py                     # FastMCP server + in-process tool dispatch
│   ├── tools/
│   │   ├── plm.py                    # 4 PLM tools
│   │   ├── mes.py                    # 4 MES tools
│   │   └── erp.py                    # 4 ERP tools
│   └── data/
│       ├── seed_wafers.py            # deterministic mock data generator
│       ├── wafer_lots.db             # (generated on first run)
│       ├── bom.json                  # (generated)
│       └── suppliers.json            # (generated)
├── agents/
│   ├── supervisor.py                 # LangGraph-shape supervisor + routing
│   ├── llm.py                        # NVIDIA / Anthropic / mock backend
│   └── __init__.py                   # 4 specialized agent prompts
└── app/
    └── streamlit_app.py              # chat + dashboard + agent trace
```

---

## Author

**Jay Guwalani** · [LinkedIn](https://linkedin.com/in/j-guwalani) · [GitHub](https://github.com/JayDS22) · [Portfolio](https://jayds22.github.io/)

Built as a reference implementation for Enterprise IT teams evaluating agentic AI platforms for manufacturing operations. Extends the [`replit-agent-bench`](https://github.com/JayDS22/replit-agent-bench) methodology to production-shape multi-agent MCP systems.
