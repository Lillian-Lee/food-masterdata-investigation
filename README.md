# Food Manufacturing — Product Master Data Change & Inventory Discrepancy Investigation

**Status:** Complete (synthetic case study)
**Scope:** One warehouse, 8 fictional products, one month (September 2026)
**All data is synthetic.** No real company data is used.

## What This Project Does

Investigates product-code and unit-of-measure discrepancies between a
supplier-facing receiving system (supplier item codes) and an internal
warehouse system (internal SKUs). It demonstrates:

1. **Versioned mappings** — supplier codes map to SKUs with explicit
   effective-date windows; re-packaging creates new versions, not overwrites.
2. **Deterministic discrepancy detection** — duplicates, expired mappings,
   ambiguous codes (same supplier code → two SKUs), and effective-date
   boundary risks.
3. **Review queue, not silent fixes** — anything unresolvable is routed to
   a named owner. No record is deleted, guessed, or force-merged.
4. **Audit trail** — simulated approve/reject decisions with approver,
   reason, and timestamp; deterministic IDs make re-runs idempotent.
5. **Reporting** — Excel exception workbook + one-page narrative summary.

## Quick Start

```bash
# 1. Generate synthetic raw data (fixed seed — fully deterministic)
python src/generate_synthetic_data.py

# 2. Run investigation pipeline
python src/run_investigation.py

# 3. Simulate approval decisions (idempotent — safe to re-run)
python src/approval_workflow.py

# 4. Validate all 12 labeled test cases
python src/test_labeled_cases.py

# 5. Generate Excel report + markdown summary
python src/generate_reports.py
```

All four commands in one line:

```bash
python src/generate_synthetic_data.py && python src/run_investigation.py && python src/approval_workflow.py && python src/test_labeled_cases.py && python src/generate_reports.py
```

## Project Structure

```
food-masterdata-investigation/
├── data/
│   ├── raw/                  # Synthetic source CSVs (fixed seed)
│   │   ├── products.csv
│   │   ├── supplier_mapping.csv
│   │   ├── goods_received.csv
│   │   ├── inventory.csv
│   │   └── change_requests.csv
│   └── processed/            # Pipeline outputs (regenerated on each run)
│       ├── cleansed_receipts.csv
│       ├── review_queue.csv
│       ├── quality_summary.json
│       ├── decision_log.csv
│       └── mapping_with_approved_changes.csv
├── docs/
│   ├── labeled_cases.csv     # 12 hand-labeled test scenarios
│   └── IMPLEMENTATION_GUIDE_BILINGUAL.md  # Detailed 中/英 design doc
├── reports/
│   ├── exception_report.xlsx
│   └── investigation_summary.md
├── src/
│   ├── generate_synthetic_data.py
│   ├── pipeline_core.py
│   ├── uom_checks.py
│   ├── run_investigation.py
│   ├── approval_workflow.py
│   ├── test_labeled_cases.py
│   └── generate_reports.py
└── README.md
```

## Data Dictionary

| File | Key Fields | Description |
|---|---|---|
| products.csv | sku, base_uom, pack_size_pieces_per_case | Internal product master (8 SKUs) |
| supplier_mapping.csv | supplier_item_code, sku, effective_from, effective_to | Versioned supplier-code → SKU mapping |
| goods_received.csv | receipt_id, supplier_item_code, qty_received | Receiving records keyed by supplier code |
| inventory.csv | sku, qty_on_hand_pieces, snapshot_date | Daily inventory snapshots |
| change_requests.csv | cr_id, proposed_sku, cr_type, requested_by | Pre-decision change requests |

## Investigation Results (Current Run)

| Metric | Value |
|---|---|
| Total receipts | 20 |
| Resolved to SKU | 18 |
| Duplicates flagged | 1 |
| Routed to review | 2 (1 ambiguous, 1 expired) |
| Reporting-ready | 15 |

## Design Principles

1. **No silent resolution** — ambiguous/expired/missing mappings go to the
   review queue, never auto-resolved by fuzzy matching or guessing.
2. **Raw data is immutable** — approved changes apply only to a working
   copy (`mapping_with_approved_changes.csv`).
3. **Idempotent audit trail** — `decision_id = hash(cr_id + action + ts)`,
   so re-running the approval workflow never duplicates entries.
4. **Deterministic data** — fixed NumPy seed (`20261017`); every run
   produces identical raw fixtures.
5. **Guard rails in tests** — normal cases must never be flagged; the test
   suite fails if any "normal" record lands in the review queue.

## Requirements

- Python 3.10+
- pandas, openpyxl

```bash
pip install pandas openpyxl
```

## Disclaimer

This is a **synthetic teaching case study**. All suppliers, products,
receipts, and people are fictional. It does not represent any real
company's systems or data. Built to demonstrate master-data investigation
skills: versioned mapping, discrepancy triage, audit trails, and
evidence-based reporting.
