"""
Unit-of-Measure (UoM) validation — Food Manufacturing Master Data Case Study
=============================================================================
Detects mismatches between supplier shipping unit and internal base unit,
and between pack sizes declared on the mapping vs. the product master.

Rules:
  - supplier_uom vs. products.base_uom: informational flag (e.g. supplier
    ships litres, internal tracks kg — requires conversion factor approval).
  - mapping pack_size vs. product pack_size: a re-pack event; flagged as
    "pack_size_changed" so reporting can pick the correct effective version.
"""

from __future__ import annotations

import pandas as pd


def check_uom_consistency(
    resolved: pd.DataFrame,
    products: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add columns to resolved receipts:
      uom_match          — True/False: supplier_uom == base_uom
      uom_note           — human-readable explanation
      pack_size_changed  — True if mapping pack_size differs from product master
    """
    if resolved.empty:
        return resolved
    df = resolved.copy()
    prod = products.set_index("sku")
    df["base_uom"] = df["resolved_sku"].map(prod["base_uom"])
    df["product_pack_size"] = df["resolved_sku"].map(
        prod["pack_size_pieces_per_case"]
    )
    df["uom_match"] = df["supplier_uom"] == df["base_uom"]
    df["uom_note"] = df["uom_match"].map(
        {True: "UoM consistent",
         False: f"supplier ships in {df['supplier_uom']}, "
                f"internal tracks {df['base_uom']}"}
    )
    df["pack_size_changed"] = (
        df["pack_size_pieces_per_case"] != df["product_pack_size"]
    )
    return df


def flag_effective_boundary(
    resolved: pd.DataFrame,
    mappings: pd.DataFrame,
) -> pd.DataFrame:
    """
    Flag receipts whose receipt_date falls within +/- 2 days of a mapping
    version boundary. These are highest-risk for mis-allocation.
    """
    if resolved.empty:
        return resolved
    df = resolved.copy()
    df["days_to_boundary"] = None
    df["near_boundary"] = False
    for _, m in mappings.iterrows():
        boundary = pd.Timestamp(m["effective_from"])
        mask = (
            (df["supplier"] == m["supplier"])
            & (df["supplier_item_code"] == m["supplier_item_code"])
        )
        if mask.any():
            delta = (pd.to_datetime(df.loc[mask, "receipt_date"]) - boundary).dt.days
            df.loc[mask, "days_to_boundary"] = delta
            df.loc[mask, "near_boundary"] = delta.abs() <= 2
    return df
