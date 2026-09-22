"""ERP tool namespace (SAP-shaped supplier + inventory + risk data)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent.parent / "data"
SUPPLIERS_PATH = DATA_DIR / "suppliers.json"


def _load_suppliers() -> dict[str, Any]:
    return json.loads(SUPPLIERS_PATH.read_text())


def get_supplier(supplier_id: str) -> dict[str, Any]:
    """Return the full supplier record from the ERP: category, quality, risk, inventory, certs.

    Args:
        supplier_id: e.g. "SUP-013"
    """
    suppliers = _load_suppliers()
    if supplier_id not in suppliers:
        return {"error": f"supplier_id {supplier_id} not found", "available": list(suppliers.keys())}
    return suppliers[supplier_id]


def check_inventory(supplier_id: str) -> dict[str, Any]:
    """Return inventory-days-on-hand + shortage risk flag for a supplier.

    Args:
        supplier_id: e.g. "SUP-006"
    """
    s = get_supplier(supplier_id)
    if "error" in s:
        return s
    days = s["inventory_days_on_hand"]
    return {
        "supplier_id": supplier_id,
        "name": s["name"],
        "inventory_days_on_hand": days,
        "shortage_risk": days < 14,
        "reorder_urgency": "critical" if days < 7 else "high" if days < 14 else "normal",
    }


def list_critical_risk_suppliers() -> dict[str, Any]:
    """Return every supplier flagged critical_risk_flag=True (lot_risk_score > 0.25)."""
    suppliers = _load_suppliers()
    critical = [s for s in suppliers.values() if s["critical_risk_flag"]]
    critical.sort(key=lambda x: -x["lot_risk_score"])
    return {"critical_suppliers": critical, "count": len(critical)}


def get_supplier_category_alternatives(category: str) -> dict[str, Any]:
    """Given a supplier category (e.g. 'photoresist'), list every supplier in that category ranked by quality.

    Args:
        category: e.g. "photoresist", "etchant", "cmp_slurry", "sputter_target"
    """
    suppliers = _load_suppliers()
    matches = [s for s in suppliers.values() if s["category"] == category]
    matches.sort(key=lambda x: -x["quality_score"])
    return {"category": category, "alternatives": matches, "count": len(matches)}
