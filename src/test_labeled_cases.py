"""
Test Validation — Labeled Case Verification
============================================
Runs the investigation pipeline and validates every labeled test case
in docs/labeled_cases.csv against actual pipeline output.

Design goal: every case must match its expected outcome, and normal
cases (TC-01, TC-08, TC-09, TC-10, TC-11, TC-12) must NOT be flagged
as discrepancies — guards against over-triggering.

Run:  python src/test_labeled_cases.py
Exit code 0 = all pass, 1 = at least one failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from pipeline_core import PROCESSED_DIR, load_raw_data
from run_investigation import investigate
from approval_workflow import apply_approvals

BASE_DIR = Path(__file__).resolve().parents[1]


def validate() -> tuple[int, int, list[str]]:
    """Run pipeline, check all labeled cases. Returns (passed, total, failures)."""
    raw = load_raw_data()
    mapping, _ = apply_approvals(raw)
    result = investigate(raw, mapping)
    summary = result.quality_summary

    cases = pd.read_csv(BASE_DIR / "docs" / "labeled_cases.csv")
    resolved_ids = set(result.cleansed_receipts["receipt_id"])
    review_map = result.review_queue.set_index("receipt_id")["mapping_status"].to_dict() \
        if not result.review_queue.empty else {}

    # Duplicate check needs the raw flagged receipts
    raw = load_raw_data()
    from pipeline_core import detect_duplicate_receipts
    _, duplicate_ids = detect_duplicate_receipts(raw["receipts"])
    dup_ids = set(duplicate_ids)

    failures: list[str] = []
    passed = 0

    for _, tc in cases.iterrows():
        rid = tc["receipt_id"]
        expected = tc["expected_outcome"]
        ok = False

        if expected == "resolved":
            ok = rid in resolved_ids and rid not in dup_ids
        elif expected == "resolved_with_pack_change_flag":
            ok = rid in resolved_ids and \
                result.cleansed_receipts.set_index("receipt_id").loc[rid, "pack_size_changed"]
        elif expected == "resolved_high_risk_flag":
            row = result.cleansed_receipts.set_index("receipt_id").loc[rid]
            ok = rid in resolved_ids and bool(row["near_boundary"])
        elif expected == "resolved_late_flag":
            ok = rid in resolved_ids and bool(result.cleansed_receipts.set_index("receipt_id").loc[rid, "late_posting"])
        elif expected == "routed_to_review_expired":
            ok = review_map.get(rid) == "expired_mapping"
        elif expected == "routed_to_review_ambiguous":
            ok = review_map.get(rid) == "ambiguous_mapping"
        elif expected == "flagged_duplicate_not_counted":
            ok = rid in dup_ids and rid not in resolved_ids
        else:
            ok = False

        if ok:
            passed += 1
            print(f"  PASS  {tc['case_id']} ({rid}): {expected}")
        else:
            failures.append(f"{tc['case_id']} ({rid}): expected {expected}")
            print(f"  FAIL  {tc['case_id']} ({rid}): expected {expected}")

    # Guard rail: normal cases must never land in the review queue
    normal_ids = cases[cases["category"].str.startswith("normal")]["receipt_id"]
    leaked = [r for r in normal_ids if r in review_map]
    if leaked:
        failures.append(f"Normal cases leaked to review queue: {leaked}")
        print(f"  FAIL  guard rail: normal cases in review queue: {leaked}")
    else:
        print("  PASS  guard rail: no normal case routed to review")

    total = len(cases)
    return passed, total, failures


if __name__ == "__main__":
    print("=== Labeled case validation ===")
    passed, total, failures = validate()
    print(f"\nResult: {passed}/{total} passed")
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All labeled cases match expected outcomes.")
    sys.exit(0)
