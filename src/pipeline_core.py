"""
Core investigation logic — Food Manufacturing Master Data Case Study
=====================================================================
Pure functions for loading raw data, resolving versioned supplier-code
mappings, and flagging data-quality exceptions. No I/O side effects beyond
reading CSVs; all outputs are returned as DataFrames for the caller to
persist.

Key design rules:
  - Versioned mappings: a supplier item code may map to different SKUs or
    pack sizes over time. Resolution is by (supplier, supplier_item_code,
    receipt_date) falling inside [effective_from, effective_to].
  - No silent guessing: ambiguous, missing, or expired mappings are routed
    to the review queue, never auto-resolved.
  - Duplicate receipts: same (supplier, supplier_item_code, batch_ref) —
    earliest receipt_id kept, later ones flagged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"


@dataclass
class InvestigationResult:
    """Container for all pipeline outputs."""
    cleansed_receipts: pd.DataFrame = field(default_factory=pd.DataFrame)
    review_queue: pd.DataFrame = field(default_factory=pd.DataFrame)
    quality_summary: dict = field(default_factory=dict)
    approved_changes: pd.DataFrame = field(default_factory=pd.DataFrame)


# ---------------------------------------------------------------------------
# 1. Load raw data
# ---------------------------------------------------------------------------
def load_raw_data(raw_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    """Load all raw CSV files with explicit dtypes; parse date columns."""
    raw_dir = raw_dir or RAW_DIR
    specs = {
        "products": ("products.csv",
                    ["sku", "product_name", "category", "base_uom",
                     "pack_size_pieces_per_case", "data_owner"]),
        "mapping": ("supplier_mapping.csv",
                    ["mapping_id", "supplier", "supplier_item_code", "sku",
                     "effective_from", "effective_to", "supplier_uom",
                     "pack_size_pieces_per_case"]),
        "receipts": ("goods_received.csv",
                     ["receipt_id", "receipt_date", "supplier",
                      "supplier_item_code", "qty_received", "batch_ref",
                      "source_note"]),
        "inventory": ("inventory.csv",
                      ["sku", "snapshot_date", "qty_on_hand_pieces", "uom"]),
        "change_requests": ("change_requests.csv",
                            ["cr_id", "supplier", "supplier_item_code",
                             "proposed_sku", "cr_type", "reason",
                             "requested_by", "requested_date"]),
    }
    date_cols = {"effective_from", "effective_to", "receipt_date",
                 "snapshot_date", "requested_date"}
    raw: dict[str, pd.DataFrame] = {}
    for key, (fname, cols) in specs.items():
        df = pd.read_csv(raw_dir / fname, dtype=str)
        for col in cols:
            if col in df.columns and col in date_cols:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
            elif col in ("qty_received", "qty_on_hand_pieces",
                         "pack_size_pieces_per_case"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
        raw[key] = df
    return raw


# ---------------------------------------------------------------------------
# 2. Duplicate detection
# ---------------------------------------------------------------------------
def detect_duplicate_receipts(receipts: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Returns (receipts_with_flag, duplicate_ids).
    A duplicate shares (supplier, supplier_item_code, batch_ref) with an
    earlier receipt_id. The earliest is canonical; later ones are flagged.
    """
    if receipts.empty:
        return receipts.copy(), []
    df = receipts.copy()
    dup_mask = df.duplicated(
        subset=["supplier", "supplier_item_code", "batch_ref"], keep="first"
    )
    duplicate_ids = df.loc[dup_mask, "receipt_id"].tolist()
    df["is_duplicate"] = dup_mask
    return df, duplicate_ids


# ---------------------------------------------------------------------------
# 3. Versioned mapping resolution
# ---------------------------------------------------------------------------
def resolve_mappings(
    receipts: pd.DataFrame,
    mappings: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Resolve each receipt to an internal SKU using versioned mappings.

    Returns (resolved, review_rows):
      resolved    — receipts with exactly one matching mapping version
      review_rows — receipts that are missing / expired / ambiguous,
                    routed to manual review (never silently resolved)
    """
    resolved_rows: list[dict] = []
    review_rows: list[dict] = []

    for _, r in receipts.iterrows():
        rdate: date = r["receipt_date"]
        cand = mappings[
            (mappings["supplier"] == r["supplier"])
            & (mappings["supplier_item_code"] == r["supplier_item_code"])
            & (mappings["effective_from"] <= rdate)
            & (mappings["effective_to"] >= rdate)
        ]
        row = r.to_dict()
        if len(cand) == 1:
            m = cand.iloc[0]
            row.update({
                "resolved_sku": m["sku"],
                "mapping_id": m["mapping_id"],
                "supplier_uom": m["supplier_uom"],
                "pack_size_pieces_per_case": m["pack_size_pieces_per_case"],
                "mapping_status": "resolved",
                "qty_internal_pieces": r["qty_received"],
            })
            resolved_rows.append(row)
        elif len(cand) == 0:
            # Check whether any mapping exists at all (expired vs. never existed)
            any_match = mappings[
                (mappings["supplier"] == r["supplier"])
                & (mappings["supplier_item_code"] == r["supplier_item_code"])
            ]
            reason = ("expired_mapping" if not any_match.empty
                      else "missing_mapping")
            row.update({
                "resolved_sku": None,
                "mapping_id": None,
                "pack_size_pieces_per_case": None,
                "mapping_status": reason,
                "qty_internal_pieces": None,
            })
            review_rows.append(row)
        else:
            row.update({
                "resolved_sku": None,
                "mapping_id": None,
                "pack_size_pieces_per_case": None,
                "mapping_status": "ambiguous_mapping",
                "qty_internal_pieces": None,
            })
            review_rows.append(row)

    resolved = pd.DataFrame(resolved_rows)
    review = pd.DataFrame(review_rows)
    return resolved, review
