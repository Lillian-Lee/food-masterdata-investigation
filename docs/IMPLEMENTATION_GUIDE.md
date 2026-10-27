# Implementation and Business Definitions

## 1. Scope

This case checks how supplier pack-size and unit changes affect receipt quantities, stock balances
and the material available for production. It records the corrections, the checks performed and the
items still requiring follow-up.

It covers one warehouse, eight SKUs and September 2026, reviewed as of 2 October 2026.
All suppliers, people, costs, densities, counts, demand and evidence references are fictional.
It is not a live operational system.

## 2. Presentation

The case study follows this sequence:

**Business problem → Records reviewed → Findings and impact → Decisions → Checks after correction → Outstanding actions**

The HTML report and the first six Excel sheets use this sequence.
Supporting calculation sheets retain the receipt, inventory, production and source evidence.

## 3. Sources and units

| Source | Record definition and key | Business use |
|---|---|---|
| products.csv | One row per SKU | Base unit, standard pack baseline and synthetic NZD cost per base unit |
| supplier_mapping.csv | One version per mapping_id | Supplier + code + effective receipt-date window |
| goods_received.csv | One imported row per receipt_id | Quantity, receipt_uom, receipt_date, posted_date, batch_ref and source_line_id |
| inventory.csv | SKU + snapshot_date | Independent available-stock counts at 31 August and 30 September |
| inventory_movements.csv | movement_id | Signed production issues in September |
| production_requirements.csv | production_order | SKU requirement for 3 October |
| change_requests.csv | cr_id | Proposed values, effective date and synthetic evidence reference |
| processed/decision_log.csv | decision_id | Simulated approval, rejection and reversal events |

Each SKU retains its base unit. Quantities in kg and L are never added together.
Amounts are in NZD at synthetic standard cost, excluding GST.
Source quantities retain their original units. The product base unit for juice is kg.

The field `qty_base` records a quantity in the product's base unit.
The field `base_qty_per_case` records the number of base units in a case.
These replace the ambiguous earlier names `qty_internal_pieces` and `pack_size_pieces_per_case`.

## 4. Immutable sources and approval replay

Normal investigation, approval and reporting commands do not write to `data/raw/`.
Only an explicit run of `generate_synthetic_data.py` resets the synthetic inputs.

CR-001 locates the old version by supplier and code, closes it on the day before the new effective date,
and inserts the approved pack version. CR-004 applies the density conversion through a new version.
It does not overwrite the source unit from L to kg while retaining the same numeric quantity.

New overlapping version pairs are rejected. The pre-existing NF-AMB-01 conflict remains unresolved.

Decision IDs are deterministic hashes of the request, action and timestamp.
The latest event per request determines whether its change is applied. Repeated runs deduplicate the same event.
A reversal appends a `revoke` event and rebuilds the mappings from baseline.
Deleting the audit log is not a valid rollback.

Approvals on 1 October retrospectively correct September using explicit effective dates.
The report is therefore a retrospective restatement. Named fictional approvers provide audit context,
not authentication or production authorisation controls.

## 5. Quantities and duplicates

- Same unit as the product base unit: `qty_base = qty_received`.
- CASE receipts: `qty_base = qty_received × effective base_qty_per_case`.
- A different supplier unit: `qty_base = qty_received × approved conversion_factor`.
  A missing factor routes the receipt to review.
- Duplicate key: `supplier + source_line_id`. A shared batch alone does not prove a duplicate.
- Conflicting quantities, dates, product codes, units or batches on the same source line stop the run.
  The pipeline does not silently select one conflicting import.

Valid zero values where permitted, unavailable conversion results and excluded records remain distinct.
Missing conversion results remain null. Before/after comparisons do not subtract zero in their place.
A repeated source document line is excluded once, with its evidence retained.

Every receipt belongs to exactly one of `reporting_ready`, `review`, `duplicate_excluded` or `out_of_period`.
The source count equals the sum of these mutually exclusive populations.

## 6. Late posting and effective-date boundaries

September uses physical receipt dates, restated with postings known by 2 October 2026.
RCV-0015 was received on 16 September and posted on 2 October, so it receives an explicit late-posting flag.
A receipt posted after the review date does not enter the earlier snapshot.

Boundary risk uses the nearest start or finite end across all relevant mapping versions.
The open-ended 2099 sentinel is excluded. Receipts within two days of a boundary are flagged.
The calculation does not depend on mapping row order, and historical and approved versions remain traceable.

## 7. Inventory reconciliation

```text
Expected closing = opening + eligible receipts + signed production movements
Variance = independently counted closing − expected closing
Variance value = variance quantity × SKU standard cost
```

Each SKU retains its base unit. Missing opening or closing count evidence fails explicitly.

Counts cover available stock only and exclude the two held receipts.
NF-AMB-01 can raise risk alerts for more than one candidate SKU, but its quantity is never allocated
to multiple inventories.

The 3 kg mango shortage remains open after replay. No balancing adjustment is created.
SKU-level counts do not establish which batch caused the shortage, so batch attribution remains unconfirmed.

## 8. Valuation and business impact

| Case | Quantity | Value basis |
|---|---|---|
| Packaging correction | 37 eligible cases × (12 − 10) = +74 kg | +NZD 629.00 comparable stock valuation correction |
| Approved density | 165 L × 0.95 = 156.75 kg | NZD 501.60 newly eligible stock value |
| Duplicate excluded | 12 cases × 12 = 144 kg | NZD 1,224.00 prevented overstatement |
| Late posting | 60 L × 0.95 = 57 kg | NZD 182.40, overlapping the conversion case |
| Legacy held receipt | 40 kg, candidate identity only | Conditional NZD 340.00; confirmed amount unavailable |
| Ambiguous held receipt | 25 kg, either flour or blueberries | Conditional NZD 40.00–212.50; confirmed amount unavailable |
| Mango residual | −3 kg | −NZD 18.00 unexplained count variance |

The packaging correction compares receipts with known quantities before and after approval.
Juice is shown separately because its quantity in kg was unknown before the conversion was approved.
Receipts on hold are excluded from the stock value. Their possible values depend on which SKU is confirmed.

Some amounts overlap, including late-posted juice already counted in the conversion total.
They should not be added together as savings or losses. An unknown amount is left blank rather than set to zero.

## 9. Production material check

```text
Conservative availability = max(min(expected eligible stock, independently counted available stock), 0)
Material shortfall = max(dated requirement − conservative availability, 0)
```

No additional inbound before 3 October is assumed. Held goods do not count as available stock.
The supplied case leaves blueberries short by 16 kg and juice short by 13.25 kg.
Values estimate material shortfalls only, not downtime or lost sales.

This is a material readiness check, not a capacity plan or BOM explosion.

## 10. Actions and verification

`case_register.csv` retains case IDs, receipts, affected SKUs, batches where attributable, quantity, unit,
valuation basis, evidence, owner, due date, handling decision, status and verification result.
Closed cases also retain a verification date. Unknown batch attribution is explicit.
`review_queue.csv` includes the owner, deadline, decision and verification information for held receipts.

Closing a packaging or conversion case requires both approved arithmetic and matching eligible-stock
reconciliation for its SKU. A rejected identity change or a retired mapping does not automatically close
the associated held receipt. Deadlines are assessed against the fixed review date, not the computer's current date.

Regression tests exercise actual replay and evidence changes.
The workbook independently cross-checks Python results and verifies formula recalculation.
Its arithmetic is live; mapping selection, approval state, case closure and action evidence are pipeline snapshots.
Rerun the workflow after changing those sources.

## 11. Engineering scope

| Module | Responsibility |
|---|---|
| pipeline_core.py | Source validation and effective-date mapping |
| uom_checks.py | Approved quantity conversion and boundary flags |
| approval_workflow.py | Approval-event replay and reversal |
| run_investigation.py | Mutually exclusive receipt dispositions |
| business_evidence.py | Inventory, valuation, material readiness and action evidence |
| generate_reports.py | English case study and investigation narrative |
| build_workbook.mjs | Excel authoring and formula verification |
| run_case_study.py | Ordered execution and failure handling |

Report-bundle metadata contains source-file and decision-log SHA-256 hashes for provenance.

The project does not claim automated balancing, external messaging, live authentication, a complete ERP,
cost accounting, actual supplier documentation or production deployment.
