"""MES (Manufacturing Execution System) tool namespace.

Yield metrics, process-step data, defect pattern queries on the wafer_lots.db SQLite store.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "wafer_lots.db"


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def get_yield(lot_id: str) -> dict[str, Any]:
    """Return final and per-step yield for a wafer lot.

    Args:
        lot_id: e.g. "W-2026-0142"
    """
    con = _con()
    lot = con.execute("SELECT * FROM wafer_lots WHERE lot_id = ?", (lot_id,)).fetchone()
    if not lot:
        return {"error": f"lot_id {lot_id} not found"}
    steps = con.execute(
        "SELECT step_order, step_name, step_yield, duration_hrs, defect_code, defect_count "
        "FROM process_step_yield WHERE lot_id = ? ORDER BY step_order",
        (lot_id,),
    ).fetchall()
    con.close()
    return {
        "lot_id": lot_id,
        "design_id": lot["design_id"],
        "start_date": lot["start_date"],
        "complete_date": lot["complete_date"],
        "wafer_count": lot["wafer_count"],
        "final_yield": lot["final_yield"],
        "status": lot["status"],
        "step_yields": [dict(s) for s in steps],
    }


def get_process_steps(lot_id: str) -> dict[str, Any]:
    """Return the full process trace for a lot, including which step had the lowest yield.

    Args:
        lot_id: e.g. "W-2026-0142"
    """
    y = get_yield(lot_id)
    if "error" in y:
        return y
    worst = min(y["step_yields"], key=lambda s: s["step_yield"])
    return {
        "lot_id": lot_id,
        "steps": y["step_yields"],
        "worst_step": worst,
        "step_count": len(y["step_yields"]),
    }


def find_defect_patterns(date_range: tuple[str, str] | None = None, top_n: int = 5) -> dict[str, Any]:
    """Aggregate defect codes across lots in a date range.

    Args:
        date_range: optional (start_iso, end_iso), inclusive of lot start_date. Default: all-time.
        top_n: return the top N defect codes.
    """
    con = _con()
    if date_range:
        rows = con.execute(
            """SELECT p.defect_code, p.defect_count, p.step_name, w.design_id
               FROM process_step_yield p JOIN wafer_lots w ON p.lot_id = w.lot_id
               WHERE p.defect_code IS NOT NULL AND w.start_date BETWEEN ? AND ?""",
            date_range,
        ).fetchall()
    else:
        rows = con.execute(
            """SELECT p.defect_code, p.defect_count, p.step_name, w.design_id
               FROM process_step_yield p JOIN wafer_lots w ON p.lot_id = w.lot_id
               WHERE p.defect_code IS NOT NULL"""
        ).fetchall()
    con.close()

    counter: Counter[str] = Counter()
    total_by_code: Counter[str] = Counter()
    by_step: dict[str, Counter[str]] = {}
    for r in rows:
        counter[r["defect_code"]] += 1
        total_by_code[r["defect_code"]] += r["defect_count"] or 0
        by_step.setdefault(r["defect_code"], Counter())[r["step_name"]] += 1

    top = counter.most_common(top_n)
    return {
        "date_range": date_range or "all-time",
        "top_defects": [
            {
                "defect_code": code,
                "occurrences": count,
                "total_defect_units": total_by_code[code],
                "primary_process_step": by_step[code].most_common(1)[0][0],
            }
            for code, count in top
        ],
    }


def list_lots_for_design(design_id: str, min_yield: float | None = None) -> dict[str, Any]:
    """Return all wafer lots produced against a design, optionally filtered by final yield.

    Args:
        design_id: e.g. "D-4471"
        min_yield: optional lower bound on final_yield.
    """
    con = _con()
    if min_yield is not None:
        rows = con.execute(
            "SELECT lot_id, start_date, complete_date, final_yield, status FROM wafer_lots WHERE design_id = ? AND final_yield >= ? ORDER BY start_date",
            (design_id, min_yield),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT lot_id, start_date, complete_date, final_yield, status FROM wafer_lots WHERE design_id = ? ORDER BY start_date",
            (design_id,),
        ).fetchall()
    con.close()
    return {"design_id": design_id, "lots": [dict(r) for r in rows], "count": len(rows)}
