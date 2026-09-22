"""
Seed realistic-shaped mock enterprise data for the demo:
- wafer_lots.db (SQLite): 60 lots x 8 process steps x yield + defect codes
- bom.json: 5 wafer designs, each with 8-12 BOM parts + supplier mappings
- suppliers.json: 15 suppliers with risk scores + lot-quality history

Deterministic (seeded), regenerable on every server start.
"""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
DATA_DIR = Path(__file__).parent
DB_PATH = DATA_DIR / "wafer_lots.db"
BOM_PATH = DATA_DIR / "bom.json"
SUPPLIERS_PATH = DATA_DIR / "suppliers.json"

PROCESS_STEPS = [
    "photolithography",
    "etching",
    "deposition_cvd",
    "ion_implantation",
    "annealing",
    "cmp_planarization",
    "metallization",
    "final_test",
]

DEFECT_CODES = [
    ("D001", "particle_contamination"),
    ("D002", "photoresist_uniformity"),
    ("D003", "overlay_misalignment"),
    ("D004", "etch_undercut"),
    ("D005", "metal_line_short"),
    ("D006", "via_open_circuit"),
    ("D007", "gate_oxide_breakdown"),
    ("D008", "cmp_scratch"),
]

WAFER_DESIGNS = ["D-4471", "D-5023", "D-5188", "D-6104", "D-6289"]

SUPPLIER_NAMES = [
    ("SUP-001", "ACME-Photoresist", "photoresist", 0.92),
    ("SUP-002", "TitanEtch-Chemicals", "etchant", 0.88),
    ("SUP-003", "PureGas-Deposition", "cvd_precursor", 0.95),
    ("SUP-004", "IonBeam-Systems", "implant_source", 0.91),
    ("SUP-005", "ThermoAnneal-Corp", "annealing_furnace_parts", 0.89),
    ("SUP-006", "SlurryMaster-CMP", "cmp_slurry", 0.72),  # low quality
    ("SUP-007", "MetalDep-Precision", "sputter_target", 0.94),
    ("SUP-008", "QualiTest-Probes", "test_probes", 0.90),
    ("SUP-009", "WaferSource-Prime", "silicon_wafers", 0.97),
    ("SUP-010", "OptiMask-Systems", "photomask", 0.93),
    ("SUP-011", "ChemPure-Solvents", "cleaning_solvents", 0.85),
    ("SUP-012", "GasFlow-Ultra", "process_gases", 0.91),
    ("SUP-013", "PhotoChem-Alt", "photoresist", 0.68),  # backup, poor
    ("SUP-014", "EtchPro-Systems", "etchant", 0.87),
    ("SUP-015", "MetalTarget-Discount", "sputter_target", 0.74),  # low quality
]


def _init_rng() -> random.Random:
    return random.Random(SEED)


# ---------------------------------------------------------------------------
# wafer_lots.db
# ---------------------------------------------------------------------------
def seed_wafer_lots() -> None:
    rng = _init_rng()
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE wafer_lots (
            lot_id TEXT PRIMARY KEY,
            design_id TEXT NOT NULL,
            start_date TEXT NOT NULL,
            complete_date TEXT NOT NULL,
            wafer_count INTEGER NOT NULL,
            final_yield REAL NOT NULL,
            status TEXT NOT NULL,
            photoresist_supplier TEXT,
            etchant_supplier TEXT,
            slurry_supplier TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE process_step_yield (
            lot_id TEXT NOT NULL,
            step_order INTEGER NOT NULL,
            step_name TEXT NOT NULL,
            step_yield REAL NOT NULL,
            duration_hrs REAL NOT NULL,
            defect_code TEXT,
            defect_count INTEGER,
            FOREIGN KEY (lot_id) REFERENCES wafer_lots(lot_id)
        )
    """)

    base_date = datetime(2026, 7, 1)
    lots = []
    steps_rows = []

    # 60 lots spread across Jul-Sep 2026
    for i in range(60):
        lot_id = f"W-2026-{i + 100:04d}"
        design = rng.choice(WAFER_DESIGNS)
        start = base_date + timedelta(days=rng.randint(0, 85))
        complete = start + timedelta(days=rng.randint(3, 6))
        wafers = rng.choice([25, 25, 25, 50])

        # supplier assignments (some lots use the low-quality suppliers)
        pr_sup = rng.choices(
            ["SUP-001", "SUP-013"], weights=[0.85, 0.15], k=1
        )[0]
        et_sup = rng.choices(
            ["SUP-002", "SUP-014"], weights=[0.70, 0.30], k=1
        )[0]
        sl_sup = rng.choices(
            ["SUP-006"], weights=[1.0], k=1
        )[0]  # CMP slurry mostly from SUP-006

        # generate step yields with realistic distribution
        cumulative_yield = 1.0
        lot_steps = []
        for order, step in enumerate(PROCESS_STEPS, start=1):
            base_step_yield = rng.uniform(0.97, 0.995)

            # Bias: SUP-013 (bad photoresist) hurts step 1
            if step == "photolithography" and pr_sup == "SUP-013":
                base_step_yield = rng.uniform(0.82, 0.90)
            # SUP-006 slurry sometimes hurts CMP
            if step == "cmp_planarization" and rng.random() < 0.15:
                base_step_yield = rng.uniform(0.88, 0.94)
            # SUP-014 etchant sometimes hurts etching
            if step == "etching" and et_sup == "SUP-014" and rng.random() < 0.35:
                base_step_yield = rng.uniform(0.86, 0.93)

            duration = rng.uniform(3.0, 12.0)

            # inject defects when step_yield is poor
            defect_code = None
            defect_count = 0
            if base_step_yield < 0.94:
                step_defects = {
                    "photolithography": "D002",
                    "etching": "D004",
                    "cmp_planarization": "D008",
                    "deposition_cvd": "D001",
                    "ion_implantation": "D003",
                    "annealing": "D007",
                    "metallization": "D005",
                    "final_test": "D006",
                }
                defect_code = step_defects.get(step, "D001")
                defect_count = int((1 - base_step_yield) * wafers * 10)

            cumulative_yield *= base_step_yield
            lot_steps.append((lot_id, order, step, round(base_step_yield, 4), round(duration, 2), defect_code, defect_count))

        final_yield = round(cumulative_yield, 4)
        status = "complete" if complete < datetime(2026, 9, 30) else "in_progress"

        lots.append((lot_id, design, start.date().isoformat(), complete.date().isoformat(), wafers, final_yield, status, pr_sup, et_sup, sl_sup))
        steps_rows.extend(lot_steps)

    cur.executemany("INSERT INTO wafer_lots VALUES (?,?,?,?,?,?,?,?,?,?)", lots)
    cur.executemany("INSERT INTO process_step_yield VALUES (?,?,?,?,?,?,?)", steps_rows)
    con.commit()
    con.close()
    print(f"seeded {len(lots)} lots, {len(steps_rows)} process-step rows -> {DB_PATH}")


# ---------------------------------------------------------------------------
# bom.json  (Bill of Materials per wafer design)
# ---------------------------------------------------------------------------
def seed_bom() -> None:
    rng = _init_rng()
    bom = {}
    part_types_per_design = [
        ("silicon_wafer_substrate", "SUP-009", 1),
        ("photomask_set", "SUP-010", 6),
        ("photoresist_positive", ["SUP-001", "SUP-013"], 2),
        ("etchant_primary", ["SUP-002", "SUP-014"], 4),
        ("cvd_precursor_tetraethyl", "SUP-003", 3),
        ("dopant_arsenic", "SUP-004", 1),
        ("annealing_ambient_gas", "SUP-005", 2),
        ("cmp_slurry_oxide", "SUP-006", 3),
        ("sputter_target_aluminum", ["SUP-007", "SUP-015"], 2),
        ("test_probe_card", "SUP-008", 1),
        ("cleaning_solvent_ipa", "SUP-011", 5),
        ("process_gas_argon", "SUP-012", 8),
    ]

    for design in WAFER_DESIGNS:
        parts = []
        # every design uses 8-12 parts (subset)
        n_parts = rng.randint(8, 12)
        sampled = rng.sample(part_types_per_design, n_parts)
        for part_type, sup, qty in sampled:
            supplier = rng.choice(sup) if isinstance(sup, list) else sup
            parts.append({
                "part_id": f"P-{design[-4:]}-{part_type[:4].upper()}-{rng.randint(100, 999)}",
                "part_name": part_type,
                "supplier_id": supplier,
                "quantity_per_wafer": qty,
                "cad_layer": rng.randint(1, 30),
            })
        bom[design] = {
            "design_id": design,
            "revision": f"rev.{rng.randint(2, 8)}.{rng.randint(0, 9)}",
            "process_node_nm": rng.choice([5, 7, 10, 14, 28]),
            "die_size_mm2": round(rng.uniform(65.0, 220.0), 1),
            "bom_parts": parts,
        }

    BOM_PATH.write_text(json.dumps(bom, indent=2))
    print(f"seeded {len(bom)} wafer designs -> {BOM_PATH}")


# ---------------------------------------------------------------------------
# suppliers.json
# ---------------------------------------------------------------------------
def seed_suppliers() -> None:
    rng = _init_rng()
    suppliers = {}
    for sup_id, name, category, quality in SUPPLIER_NAMES:
        # lot risk = inverse of quality with some noise
        lot_risk = round((1.0 - quality) + rng.uniform(-0.03, 0.03), 3)
        lot_risk = max(0.01, min(0.99, lot_risk))
        inv_days = rng.randint(7, 45) if quality > 0.8 else rng.randint(2, 12)
        suppliers[sup_id] = {
            "supplier_id": sup_id,
            "name": name,
            "category": category,
            "quality_score": quality,
            "lot_risk_score": lot_risk,
            "inventory_days_on_hand": inv_days,
            "certifications": rng.sample(["ISO9001", "IATF16949", "SEMI-S2", "SEMI-S8", "AS9100"], k=rng.randint(1, 3)),
            "last_audit_date": (datetime(2026, 9, 21) - timedelta(days=rng.randint(30, 400))).date().isoformat(),
            "critical_risk_flag": lot_risk > 0.25,
        }
    SUPPLIERS_PATH.write_text(json.dumps(suppliers, indent=2))
    print(f"seeded {len(suppliers)} suppliers -> {SUPPLIERS_PATH}")


def seed_all() -> None:
    seed_wafer_lots()
    seed_bom()
    seed_suppliers()


if __name__ == "__main__":
    seed_all()
