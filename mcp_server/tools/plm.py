"""PLM (Product Lifecycle Management) tool namespace.

Shape mirrors a Windchill / Teamcenter-style API: CAD/BOM metadata + supplier mapping per wafer design.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent.parent / "data"
BOM_PATH = DATA_DIR / "bom.json"


def _load_bom() -> dict[str, Any]:
    return json.loads(BOM_PATH.read_text())


def get_bom(design_id: str) -> dict[str, Any]:
    """Return the full Bill of Materials for a wafer design.

    Args:
        design_id: e.g. "D-4471"

    Returns:
        dict with keys: design_id, revision, process_node_nm, die_size_mm2, bom_parts (list).
    """
    bom = _load_bom()
    if design_id not in bom:
        return {"error": f"design_id {design_id} not found", "available": list(bom.keys())}
    return bom[design_id]


def get_cad_metadata(design_id: str) -> dict[str, Any]:
    """Return CAD-level metadata (revision, process node, die size, layer count).

    Args:
        design_id: e.g. "D-4471"
    """
    bom = _load_bom()
    if design_id not in bom:
        return {"error": f"design_id {design_id} not found"}
    d = bom[design_id]
    layers = max((p["cad_layer"] for p in d["bom_parts"]), default=0)
    return {
        "design_id": design_id,
        "revision": d["revision"],
        "process_node_nm": d["process_node_nm"],
        "die_size_mm2": d["die_size_mm2"],
        "layer_count": layers,
        "part_count": len(d["bom_parts"]),
    }


def list_suppliers_for_design(design_id: str) -> dict[str, Any]:
    """Return unique suppliers referenced by a design's BOM.

    Args:
        design_id: e.g. "D-4471"
    """
    bom = _load_bom()
    if design_id not in bom:
        return {"error": f"design_id {design_id} not found"}
    suppliers = sorted({p["supplier_id"] for p in bom[design_id]["bom_parts"]})
    return {"design_id": design_id, "supplier_ids": suppliers, "count": len(suppliers)}


def list_designs_using_supplier(supplier_id: str) -> dict[str, Any]:
    """Reverse lookup: given a supplier, which wafer designs depend on them?

    Args:
        supplier_id: e.g. "SUP-013"
    """
    bom = _load_bom()
    impacted = []
    for design_id, d in bom.items():
        parts = [p for p in d["bom_parts"] if p["supplier_id"] == supplier_id]
        if parts:
            impacted.append({
                "design_id": design_id,
                "parts_from_supplier": [p["part_name"] for p in parts],
            })
    return {"supplier_id": supplier_id, "impacted_designs": impacted, "count": len(impacted)}
