"""
Main pipeline entry point — Food Manufacturing Master Data Case Study
=======================================================================
Orchestrates the full investigation:
  1. Load raw synthetic data
  2. Detect duplicate receipts
  3. Resolve versioned supplier-code mappings
  4. Flag UoM mismatches and effective-date boundary risks
  5. Build review queue (unresolvable items only)
  6. Compute quality summary statistics
  7. Write processed outputs to data/processed/

Run:  python src/run_investigation.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipeline_core import (
    InvestigationResult,
    PROCESSED_DIR,
    detect_duplicate_receipts,
    load_raw_data,
    resolve_mappings,
)
from uom_checks import check_uom_consistency, flag_effective_boundary

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def build_quality_summary(
    raw_receipts: pd.DataFrame,
    flagged: pd.DataFrame,
    resolved: pd.DataFrame,
    review: pd.DataFrame,
) -> dict:
    """Compute summary statistics for reporting and test validation."""
    total = len(raw_receipts)
    n_dup = int(flagged["is_duplicate"].sum())
    n_resolved = len(resolved)
    n_review = len(review)
    n_ambiguous = int((review["mapping_status"] == "ambiguous_mapping").sum())
    n_missing = int((review["mapping_status"] == "missing_mapping").sum())
    n_expired = int((review["mapping_status"] == "expired_mapping").sum())
    n_uom_mismatch = int((~resolved["uom_match"]).sum()) if not resolved.empty else 0
    n_boundary = int(resolved["near_boundary"].sum()) if not resolved.empty else 0
    n_pack_changed = int(resolved["pack_size_changed"].sum()) if not resolved.empty else 0
    clean = n_resolved - n_dup - n_review
    return {
        "total_receipts": total,
        "resolved": n_resolved,
        "duplicates_flagged": n_dup,
        "routed_to_review": n_review,
        "ambiguous_mappings": n_ambiguous,
        "missing_mappings": n_missing,
        "expired_mappings": n_expired,
        "uom_mismatches": n_uom_mismatch,
        "near_boundary": n_boundary,
        "pack_size_changes": n_pack_changed,
        "clean_resolvable": clean,
    }


def run() -> InvestigationResult:
    raw = load_raw_data()
    receipts = raw["receipts"]

    flagged, dup_ids = detect_duplicate_receipts(receipts)
    resolved, review = resolve_mappings(flagged, raw["mapping"])
    resolved = check_uom_consistency(resolved, raw["products"])
    resolved = flag_effective_boundary(resolved, raw["mapping"])

    # Exclude duplicates from clean reporting slice
    clean_resolved = resolved[~resolved.get("is_duplicate", False)].copy()

    summary = build_quality_summary(raw["receipts"], flagged, resolved, review)

    result = InvestigationResult(
        cleansed_receipts=clean_resolved,
        review_queue=review,
        quality_summary=summary,
        approved_changes=raw["change_requests"],
    )

    result.cleansed_receipts.to_csv(
        PROCESSED_DIR / "cleansed_receipts.csv", index=False)
    result.review_queue.to_csv(
        PROCESSED_DIR / "review_queue.csv", index=False)
    with (PROCESSED_DIR / "quality_summary.json").open("w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"Pipeline complete: {summary}")
    return result


if __name__ == "__main__":
    run()
