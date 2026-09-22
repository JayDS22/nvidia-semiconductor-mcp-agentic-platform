"""LangGraph agentic layer: supervisor + 4 specialized agents.

- YieldAnalyst  — queries MES for yield/defect data
- BOMVerifier   — queries PLM for BOM/CAD/supplier mapping
- RootCauseAnalyst — chains MES + PLM + ERP to correlate yield drop -> root cause
- Recommender   — synthesizes a fix + writes stakeholder-facing summary
"""
