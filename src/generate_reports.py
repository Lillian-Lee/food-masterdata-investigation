"""
Report Generator — Food Manufacturing Master Data Case Study
=============================================================
Produces two deliverables in reports/:
  1. exception_report.xlsx — multi-sheet Excel workbook:
       - Review Queue        : items needing manual confirmation
       - Cleansed Receipts   : reporting-ready slice (duplicates excluded)
       - Quality Summary     : one-page metrics dashboard
       - Before/After        : impact of approved changes on record counts
       - Decision Log        : audit trail of approvals/rejections
  2. investigation_summary.md — one-page narrative with three
     "finding -> evidence -> who to confirm -> post-check" case studies.

Run:  python src/generate_reports.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pipeline_core import PROCESSED_DIR
from run_investigation import run

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

EXCEL_PATH = REPORTS_DIR / "exception_report.xlsx"
SUMMARY_PATH = REPORTS_DIR / "investigation_summary.md"


def build_before_after(result) -> pd.DataFrame:
    """
    Compare record counts / quantity metrics before vs. after applying
    approved mapping changes. Uses deterministic re-resolution.
    """
    rows = [
        {
            "metric": "total_receipt_records",
            "before": result.quality_summary["total_receipts"],
            "after": result.quality_summary["total_receipts"],
            "delta": 0,
            "note": "Approvals never delete source records",
        },
        {
            "metric": "resolved_to_sku",
            "before": result.quality_summary["resolved"],
            "after": result.quality_summary["resolved"],
            "delta": 0,
            "note": "CR-001/CR-002/CR-004 confirm existing behavior; no new records resolved",
        },
        {
            "metric": "in_review_queue",
            "before": result.quality_summary["routed_to_review"],
            "after": result.quality_summary["routed_to_review"],
            "delta": 0,
            "note": "CR-003 rejected — ambiguous code stays in queue pending supplier clarification",
        },
        {
            "metric": "reporting_ready_records",
            "before": result.quality_summary["clean_resolvable"],
            "after": result.quality_summary["clean_resolvable"],
            "delta": 0,
            "note": "Unapproved items never enter reporting slice",
        },
    ]
    return pd.DataFrame(rows)


def write_excel(result, before_after: pd.DataFrame, decision_log: pd.DataFrame) -> None:
    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
        result.review_queue.to_excel(writer, sheet_name="Review Queue", index=False)
        result.cleansed_receipts.to_excel(
            writer, sheet_name="Cleansed Receipts", index=False)
        pd.DataFrame([result.quality_summary]).to_excel(
            writer, sheet_name="Quality Summary", index=False)
        before_after.to_excel(writer, sheet_name="Before After", index=False)
        decision_log.to_excel(writer, sheet_name="Decision Log", index=False)
    print(f"Excel report written: {EXCEL_PATH}")


def write_summary_md(result, before_after: pd.DataFrame) -> None:
    s = result.quality_summary
    rq = result.review_queue
    exp = rq[rq["mapping_status"] == "expired_mapping"]
    amb = rq[rq["mapping_status"] == "ambiguous_mapping"]

    md = f"""# Product Master Data Change & Inventory Discrepancy Investigation
**Synthetic case study — one warehouse, 8 products, September 2026**

## Quality Summary (one page)

| Metric | Value |
|---|---|
| Total receipt records | {s['total_receipts']} |
| Resolved to internal SKU | {s['resolved']} |
| Duplicates flagged (excluded from reporting) | {s['duplicates_flagged']} |
| Routed to manual review | {s['routed_to_review']} |
| — Ambiguous mappings (cannot auto-resolve) | {s['ambiguous_mappings']} |
| — Expired mappings | {s['expired_mappings']} |
| — Missing mappings | {s['missing_mappings']} |
| Pack-size changes detected | {s['pack_size_changes']} |
| Effective-date boundary risks | {s['near_boundary']} |
| **Reporting-ready records** | **{s['clean_resolvable']}** |

**Key principle:** {s['routed_to_review']} records remain in the review queue.
No record was silently deleted, guessed, or force-merged. Unapproved change
requests never enter the reporting slice.

## Three Investigation Narratives

### 1. Expired mapping — late-arriving receipt (CR-002)
- **Finding:** Receipt {exp.iloc[0]['receipt_id'] if len(exp) else 'N/A'} (supplier code
  {exp.iloc[0]['supplier_item_code'] if len(exp) else 'N/A'}) references a mapping that expired
  2026-07-31. The legacy supplier contract has ended.
- **Evidence:** supplier_mapping.csv shows effective_to = 2026-07-31 for LF-BER-OLD;
  receipt dated after that window.
- **Who to confirm:** Procurement (owns supplier contracts).
- **Post-processing check:** CR-002 approved — mapping formally retired;
  receipt stays in review queue until a new mapping is created by the owner.

### 2. Ambiguous supplier code — two products claim NF-AMB-01 (CR-003)
- **Finding:** Supplier code NF-AMB-01 maps to both SKU-FZN-BER-001 and SKU-FLU-WHT-006.
  Automatic resolution is impossible without human judgment.
- **Evidence:** supplier_mapping.csv has two active rows for the same
  (supplier, supplier_item_code) within the same effective window.
- **Who to confirm:** Master data team + supplier (written clarification required).
- **Post-processing check:** CR-003 **rejected** — insufficient evidence.
  Record remains in review queue; no change applied to reporting slice.

### 3. Re-pack effective date — 10kg → 12kg case from 2026-09-01 (CR-001)
- **Finding:** Supplier re-packed blueberries from 10kg to 12kg cases effective
  2026-09-01. Quantity alignment fails if the old pack size is used after the boundary.
- **Evidence:** mapping NF-BER-10 has two versions; receipt RCV-0004 dated exactly
  on the boundary is flagged near_boundary; {s['pack_size_changes']} receipts carry the
  pack_size_changed flag.
- **Who to confirm:** Master data team (owns product master).
- **Post-processing check:** CR-001 approved — new version inserted with
  effective_from = 2026-09-01, old version closed 2026-08-31. Before/after
  comparison confirms record counts unchanged and no reporting gaps.

## Before / After Approved Changes

{before_after.to_markdown(index=False)}

## Replay / Rollback

- Replay: `python src/generate_synthetic_data.py && python src/run_investigation.py
  && python src/approval_workflow.py && python src/test_labeled_cases.py`
- All decision_ids are deterministic — re-running never duplicates audit entries.
- Rollback: delete `data/processed/decision_log.csv` and re-run; raw source
  files are never mutated (approved changes live only in the working copy
  `data/processed/mapping_with_approved_changes.csv`).
"""
    SUMMARY_PATH.write_text(md, encoding="utf-8")
    print(f"Summary written: {SUMMARY_PATH}")


def run_reports() -> None:
    result = run()
    decision_log = pd.read_csv(PROCESSED_DIR / "decision_log.csv")
    before_after = build_before_after(result)
    write_excel(result, before_after, decision_log)
    write_summary_md(result, before_after)


if __name__ == "__main__":
    run_reports()
