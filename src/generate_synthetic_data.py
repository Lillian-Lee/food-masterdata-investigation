"""
Synthetic Data Generator — Food Manufacturing Master Data Case Study
====================================================================
Generates deterministic (fixed-seed) CSV fixtures for the product-code and
unit-of-measure discrepancy investigation project.

All data is SYNTHETIC. Any resemblance to real companies is coincidental.
No real PII or proprietary data is used.

Scope: one warehouse, 8 fictional products, one month (2026-09-01 .. 2026-09-30).

Outputs (written to data/raw/):
    products.csv              — internal product master
    supplier_mapping.csv      — versioned supplier-code → SKU mappings with effective dates
    goods_received.csv        — receiving records keyed by supplier item code
    inventory.csv             — daily inventory snapshots keyed by internal SKU
    change_requests.csv       — submitted mapping/unit change requests (pre-decision)

Run:  python src/generate_synthetic_data.py
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np

SEED = 20261017
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(SEED)

MONTH_START = date(2026, 9, 1)
DAYS = 30


def _d(day_offset: int) -> date:
    return MONTH_START + timedelta(days=day_offset)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Product master (8 fictional products)
# ---------------------------------------------------------------------------
PRODUCTS = [
    # sku, name, category, base_uom, pack_size_pieces_per_case
    ("SKU-FZN-BER-001", "Frozen Blueberries 10kg",  "Frozen Fruit", "kg", 10),
    ("SKU-FZN-MAN-002", "Frozen Mango Chunks 5kg",  "Frozen Fruit", "kg", 5),
    ("SKU-APL-JCE-003", "Apple Juice Concentrate", "Beverage",     "L",  20),
    ("SKU-PLS-TOM-004", "Tomato Passata 3kg",       "Canned Goods","kg", 3),
    ("SKU-OIL-SUN-005", "Sunflower Oil 20L",        "Oils",         "L",  20),
    ("SKU-FLU-WHT-006", "Wheat Flour 25kg",         "Bakery",       "kg", 25),
    ("SKU-SGR-WHT-007", "White Sugar 1kg Pack",     "Dry Staples",  "kg", 1),
    ("SKU-CHS-SAU-008","Cheese Sauce Base 4kg",     "Dairy Prep",   "kg", 4),
]


def generate_products() -> None:
    rows = [
        {
            "sku": sku,
            "product_name": name,
            "category": cat,
            "base_uom": uom,
            "pack_size_pieces_per_case": pack,
            "data_owner": "master-data-team@example.com",
        }
        for sku, name, cat, uom, pack in PRODUCTS
    ]
    _write_csv(RAW_DIR / "products.csv",
               ["sku", "product_name", "category", "base_uom",
                "pack_size_pieces_per_case", "data_owner"], rows)


# ---------------------------------------------------------------------------
# Versioned supplier-code → SKU mapping
# ---------------------------------------------------------------------------
# Each mapping row has an effective_from / effective_to window.
# Multiple versions per supplier code model re-packaging over time.
MAPPING_VERSIONS = [
    # (supplier, supplier_item_code, sku, eff_from, eff_to, supplier_uom, cases_per_shipment)
    ("SUP-NORTHFROST", "NF-BER-10",      "SKU-FZN-BER-001", date(2026, 1, 1),  date(2026, 8, 31), "kg",  10),
    ("SUP-NORTHFROST", "NF-BER-10",      "SKU-FZN-BER-001", date(2026, 9, 1),  date(2099, 12, 31), "kg", 12),  # re-pack: 10kg→12kg
    ("SUP-NORTHFROST", "NF-MAN-5",       "SKU-FZN-MAN-002", date(2026, 1, 1),  date(2099, 12, 31), "kg",  5),
    ("SUNCOAST-BEV",   "SC-JCE-20L",     "SKU-APL-JCE-003", date(2026, 1, 1),  date(2099, 12, 31), "L",   20),
    ("SUNCOAST-BEV",   "SC-PAS-3KG",     "SKU-PLS-TOM-004", date(2026, 1, 1),  date(2099, 12, 31), "kg",  3),
    ("SUP-NORTHFROST", "NF-OIL-20L",     "SKU-OIL-SUN-005", date(2026, 1, 1),  date(2099, 12, 31), "L",   20),
    ("MILLERS-DIRECT", "MD-FLU-25",      "SKU-FLU-WHT-006", date(2026, 1, 1),  date(2099, 12, 31), "kg",  25),
    ("MILLERS-DIRECT", "MD-SGR-1K",      "SKU-SGR-WHT-007", date(2026, 1, 1),  date(2099, 12, 31), "kg",  1),
    ("DAIRYLAND",      "DL-SAU-4K",      "SKU-CHS-SAU-008", date(2026, 1, 1),  date(2099, 12, 31), "kg",  4),
    # Duplicate-key trap: same supplier item code maps to TWO SKUs (conflict — must NOT auto-resolve)
    ("SUP-NORTHFROST", "NF-AMB-01",      "SKU-FZN-BER-001", date(2026, 6, 1),  date(2099, 12, 31), "kg",  10),
    ("SUP-NORTHFROST", "NF-AMB-01",      "SKU-FLU-WHT-006", date(2026, 6, 1),  date(2099, 12, 31), "kg",  25),
    # Legacy obsolete mapping (still referenced by a late-arriving receipt)
    ("LEGACY-FROST",   "LF-BER-OLD",     "SKU-FZN-BER-001", date(2025, 1, 1),  date(2026, 7, 31), "kg",  10),
]


def generate_supplier_mapping() -> None:
    rows = []
    for i, (sup, code, sku, eff_from, eff_to, uom, pack) in enumerate(MAPPING_VERSIONS, start=1):
        rows.append({
            "mapping_id": f"MAP-{i:03d}",
            "supplier": sup,
            "supplier_item_code": code,
            "sku": sku,
            "effective_from": eff_from.isoformat(),
            "effective_to": eff_to.isoformat(),
            "supplier_uom": uom,
            "pack_size_pieces_per_case": pack,
        })
    _write_csv(RAW_DIR / "supplier_mapping.csv",
               ["mapping_id", "supplier", "supplier_item_code", "sku",
                "effective_from", "effective_to", "supplier_uom",
                "pack_size_pieces_per_case"], rows)


# ---------------------------------------------------------------------------
# Goods received (keyed by supplier item code)
# ---------------------------------------------------------------------------
# Hand-crafted rows cover the 12 labeled scenarios (see docs/labeled_cases.csv).
RECEIPTS = [
    # receipt_id, date, supplier, supplier_item_code, qty_supplier_uom, batch, note
    ("RCV-0001", _d(2),  "SUP-NORTHFROST", "NF-BER-10",  120, "B-0901", "normal — old pack"),
    ("RCV-0002", _d(4),  "SUNCOAST-BEV",   "SC-JCE-20L",  50, "B-0903", "normal"),
    ("RCV-0003", _d(6),  "MILLERS-DIRECT", "MD-FLU-25",    80, "B-0905", "normal"),
    ("RCV-0004", _d(0),  "SUP-NORTHFROST", "NF-BER-10",  144, "B-0907", "post-repack effective boundary (12kg/case)"),
    ("RCV-0005", _d(10), "SUNCOAST-BEV",   "SC-PAS-3KG",  100, "B-0909", "normal"),
    ("RCV-0006", _d(12), "SUP-NORTHFROST", "NF-OIL-20L",  30, "B-0911", "normal"),
    ("RCV-0007", _d(14), "MILLERS-DIRECT", "MD-SGR-1K",  400, "B-0913", "normal — high volume"),
    ("RCV-0008", _d(16), "DAIRYLAND",      "DL-SAU-4K",   45, "B-0915", "normal"),
    ("RCV-0009", _d(18), "SUP-NORTHFROST", "NF-MAN-5",    60, "B-0917", "normal"),
    ("RCV-0010", _d(20), "SUP-NORTHFROST", "NF-BER-10",  130, "B-0919", "post-repack, qty mismatch candidate"),
    ("RCV-0011", _d(22), "SUNCOAST-BEV",   "SC-JCE-20L",  55, "B-0921", "normal"),
    ("RCV-0012", _d(24), "SUP-NORTHFROST", "NF-AMB-01",   25, "B-0923", "AMBIGUOUS — two SKUs claim this code"),
    ("RCV-0013", _d(26), "MILLERS-DIRECT", "MD-FLU-25",    90, "B-0925", "normal"),
    ("RCV-0014", _d(28), "LEGACY-FROST",   "LF-BER-OLD",  40, "B-0927", "late arrival — mapping expired 2026-07-31"),
    ("RCV-0015", _d(15), "SUNCOAST-BEV",   "SC-JCE-20L",  60, "B-0914", "back-dated receipt (received after posting cut-off)"),
    ("RCV-0016", _d(10), "SUP-NORTHFROST", "NF-BER-10",  150, "B-0907", "DUPLICATE — same supplier/code/batch_ref as RCV-0004"),
    ("RCV-0017", _d(5),  "SUP-NORTHFROST", "NF-MAN-5",    55, "B-0904", "normal"),
    ("RCV-0018", _d(9),  "MILLERS-DIRECT", "MD-SGR-1K",  380, "B-0908", "normal"),
    ("RCV-0019", _d(11), "DAIRYLAND",      "DL-SAU-4K",   42, "B-0910", "normal"),
    ("RCV-0020", _d(21), "SUNCOAST-BEV",   "SC-PAS-3KG",  95, "B-0920", "normal"),
]


def generate_goods_received() -> None:
    rows = [
        {
            "receipt_id": rid,
            "receipt_date": rdate.isoformat(),
            "supplier": sup,
            "supplier_item_code": code,
            "qty_received": qty,
            "batch_ref": batch,
            "source_note": note,
        }
        for rid, rdate, sup, code, qty, batch, note in RECEIPTS
    ]
    _write_csv(RAW_DIR / "goods_received.csv",
               ["receipt_id", "receipt_date", "supplier", "supplier_item_code",
                "qty_received", "batch_ref", "source_note"], rows)


# ---------------------------------------------------------------------------
# Inventory snapshots (keyed by internal SKU, daily)
# ---------------------------------------------------------------------------
def generate_inventory() -> None:
    rows = []
    for sku, name, cat, uom, pack in PRODUCTS:
        # pseudo-random but deterministic daily balances
        base = int(rng.integers(200, 800))
        drift = int(rng.integers(-5, 6))
        for d_off in range(DAYS):
            qty = base + drift * d_off + int(rng.integers(-20, 21))
            rows.append({
                "sku": sku,
                "snapshot_date": _d(d_off).isoformat(),
                "qty_on_hand_pieces": max(qty, 0),
                "uom": uom,
            })
    _write_csv(RAW_DIR / "inventory.csv",
               ["sku", "snapshot_date", "qty_on_hand_pieces", "uom"], rows)


# ---------------------------------------------------------------------------
# Change requests (pre-decision queue)
# ---------------------------------------------------------------------------
CHANGE_REQUESTS = [
    ("CR-001", "SUP-NORTHFROST", "NF-BER-10", "SKU-FZN-BER-001",
     "repack", "supplier confirmed 12kg case from 2026-09-01",
     "procurement@example.com", "2026-08-20"),
    ("CR-002", "LEGACY-FROST", "LF-BER-OLD", "SKU-FZN-BER-001",
     "retire_mapping", "legacy supplier contract ended 2026-07-31",
     "procurement@example.com", "2026-07-25"),
    ("CR-003", "SUP-NORTHFROST", "NF-AMB-01", "SKU-FZN-BER-001",
     "resolve_ambiguity", "supplier says code is for blueberries; flour team disputes",
     "master-data-team@example.com", "2026-09-10"),
    ("CR-004", "SUNCOAST-BEV", "SC-JCE-20L", "SKU-APL-JCE-003",
     "unit_change", "supplier now ships in L instead of kg — needs UoM conversion",
     "warehouse@example.com", "2026-09-05"),
]


def generate_change_requests() -> None:
    rows = [
        {
            "cr_id": cr_id,
            "supplier": sup,
            "supplier_item_code": code,
            "proposed_sku": sku,
            "cr_type": cr_type,
            "reason": reason,
            "requested_by": req_by,
            "requested_date": req_date,
        }
        for cr_id, sup, code, sku, cr_type, reason, req_by, req_date in CHANGE_REQUESTS
    ]
    _write_csv(RAW_DIR / "change_requests.csv",
               ["cr_id", "supplier", "supplier_item_code", "proposed_sku",
                "cr_type", "reason", "requested_by", "requested_date"], rows)


def main() -> None:
    generate_products()
    generate_supplier_mapping()
    generate_goods_received()
    generate_inventory()
    generate_change_requests()
    print(f"Synthetic data written to {RAW_DIR} (seed={SEED})")


if __name__ == "__main__":
    main()
