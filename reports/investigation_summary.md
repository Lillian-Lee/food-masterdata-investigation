# Product Master Data Change & Inventory Discrepancy Investigation
**Synthetic case study — one warehouse, 8 products, September 2026**

## Quality Summary (one page)

| Metric | Value |
|---|---|
| Total receipt records | 20 |
| Resolved to internal SKU | 18 |
| Duplicates flagged (excluded from reporting) | 1 |
| Routed to manual review | 2 |
| — Ambiguous mappings (cannot auto-resolve) | 1 |
| — Expired mappings | 1 |
| — Missing mappings | 0 |
| Pack-size changes detected | 4 |
| Effective-date boundary risks | 2 |
| **Reporting-ready records** | **15** |

**Key principle:** 2 records remain in the review queue.
No record was silently deleted, guessed, or force-merged. Unapproved change
requests never enter the reporting slice.

## Three Investigation Narratives

### 1. Expired mapping — late-arriving receipt (CR-002)
- **Finding:** Receipt RCV-0014 (supplier code
  LF-BER-OLD) references a mapping that expired
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
  on the boundary is flagged near_boundary; 4 receipts carry the
  pack_size_changed flag.
- **Who to confirm:** Master data team (owns product master).
- **Post-processing check:** CR-001 approved — new version inserted with
  effective_from = 2026-09-01, old version closed 2026-08-31. Before/after
  comparison confirms record counts unchanged and no reporting gaps.

## Before / After Approved Changes

| metric                  |   before |   after |   delta | note                                                                           |
|:------------------------|---------:|--------:|--------:|:-------------------------------------------------------------------------------|
| total_receipt_records   |       20 |      20 |       0 | Approvals never delete source records                                          |
| resolved_to_sku         |       18 |      18 |       0 | CR-001/CR-002/CR-004 confirm existing behavior; no new records resolved        |
| in_review_queue         |        2 |       2 |       0 | CR-003 rejected — ambiguous code stays in queue pending supplier clarification |
| reporting_ready_records |       15 |      15 |       0 | Unapproved items never enter reporting slice                                   |

## Replay / Rollback

- Replay: `python src/generate_synthetic_data.py && python src/run_investigation.py
  && python src/approval_workflow.py && python src/test_labeled_cases.py`
- All decision_ids are deterministic — re-running never duplicates audit entries.
- Rollback: delete `data/processed/decision_log.csv` and re-run; raw source
  files are never mutated (approved changes live only in the working copy
  `data/processed/mapping_with_approved_changes.csv`).
