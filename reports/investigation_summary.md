# Food Supply Chain Master Data & Inventory Investigation

Synthetic case study: one warehouse, eight SKUs, September 2026.
Reviewed on **2 October 2026**. Amounts use assumed standard costs in NZD, excluding GST.

## 1. Business problem

The supplier increased blueberry cases from 10 kg to 12 kg, but the receiving system still used
the old case size. Juice was received in litres while the warehouse recorded stock in kilograms,
with no approved conversion factor.

The investigation checked the September receipts, corrected the quantities supported by supplier
specifications, and compared the resulting stock balances with the physical counts.
It then checked whether enough material was available for production on 3 October.

## 2. Records reviewed

The source records include 20 receipt rows, opening and closing counts for eight SKUs, eight
production issues and eight material requirements. One receipt row is a duplicate import.

Two specifications support the corrections: REP-001 sets the blueberry case size at 12 kg,
and DENS-004 gives a juice conversion factor of 0.95 kg/L. These specification references and
values were created for this case, along with the other data and approval records.

Receipts are assigned to September by their physical receipt date, using postings known by
2 October. RCV-0015 was received on 16 September but posted on 2 October, so it is included
and flagged as a late posting. Counts cover stock available for use and exclude the held receipts.

## 3. Findings and impact

| Measure | Before correction | After correction | Change |
| --- | --- | --- | --- |
| Imported receipt rows | 20 | 20 | 0 |
| Duplicate imports excluded | 1 | 1 | 0 |
| Receipts cleared for reporting | 14 | 17 | 3 |
| Receipts held for review | 5 | 2 | -3 |
| Receipts awaiting a conversion factor | 3 | 0 | -3 |
| Late postings included in the report | 0 | 1 | 1 |
| Value of cleared receipts (NZD) | 6,315.00 | 7,445.60 | 1,130.60 |

**Blueberries.** Applying the revised case size to 37 cases increases recorded receipts by
**74 kg**, a stock value correction of **NZD 629.00**.
The affected receipts are RCV-0001, RCV-0004 and RCV-0010, covering batches B-0901, B-0907 and B-0919.

**Juice concentrate.** The approved factor converts 165 L to **156.75 kg**, worth
**NZD 501.60**. These receipts can now be included in the stock report.
Their quantities in kg were previously unknown, so this amount is shown separately from the
blueberry correction.

**Duplicate import.** RCV-0016 repeats source line GRN-0004-1. Counting it again would add
144 kg of blueberries, worth NZD 1,224.00. The original receipt is counted once and both import
records are retained.

**Held receipts.** RCV-0012 has a disputed product code, and RCV-0014 uses an expired supplier
mapping. Both remain outside the stock report. For RCV-0012, the value could be NZD 40.00 or
NZD 212.50 depending on which product is confirmed. RCV-0014 would be worth NZD 340.00 if its
historical product identification is confirmed.

These figures measure different effects and overlap. For example, the late-posted juice receipt
is already included in the juice total. They should not be added together as savings.

### Inventory reconciliation

For each SKU, expected closing stock is opening stock plus cleared receipts, less production usage.
The table compares this with the independent closing count.

| SKU | Unit | Opening stock | Cleared receipts | Production issues (signed) | Expected closing stock | Closing count | Difference | Difference (NZD) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SKU-FZN-BER-001 | kg | 500 | 444 | -300 | 644 | 644 | 0 | 0.00 |
| SKU-FZN-MAN-002 | kg | 200 | 115 | -80 | 235 | 232 | -3 | -18.00 |
| SKU-APL-JCE-003 | kg | 100 | 156.75 | -100 | 156.75 | 156.75 | 0 | 0.00 |
| SKU-PLS-TOM-004 | kg | 300 | 195 | -120 | 375 | 375 | 0 | 0.00 |
| SKU-OIL-SUN-005 | L | 100 | 30 | -25 | 105 | 105 | 0 | 0.00 |
| SKU-FLU-WHT-006 | kg | 200 | 170 | -100 | 270 | 270 | 0 | 0.00 |
| SKU-SGR-WHT-007 | kg | 500 | 780 | -500 | 780 | 780 | 0 | 0.00 |
| SKU-CHS-SAU-008 | kg | 100 | 87 | -50 | 137 | 137 | 0 | 0.00 |

The corrections reconcile blueberries and juice to the counts. Mango remains 3 kg short,
worth NZD 18.00. The count is at SKU level, so it does not establish which batch caused the shortage.

### Materials required for 3 October

Available stock is the lower of the calculated balance and the physical count. The check assumes
no further deliveries before production.

| Order | SKU | Unit | Available stock | Required | Shortfall | Material value (NZD) | Stock check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PLAN-001 | SKU-FZN-BER-001 | kg | 644 | 660 | 16 | 136.00 | Shortfall |
| PLAN-002 | SKU-FZN-MAN-002 | kg | 232 | 220 | 0 | 0.00 | Sufficient |
| PLAN-003 | SKU-APL-JCE-003 | kg | 156.75 | 170 | 13.25 | 42.40 | Shortfall |
| PLAN-004 | SKU-PLS-TOM-004 | kg | 375 | 300 | 0 | 0.00 | Sufficient |
| PLAN-005 | SKU-OIL-SUN-005 | L | 105 | 80 | 0 | 0.00 | Sufficient |
| PLAN-006 | SKU-FLU-WHT-006 | kg | 270 | 200 | 0 | 0.00 | Sufficient |
| PLAN-007 | SKU-SGR-WHT-007 | kg | 780 | 600 | 0 | 0.00 | Sufficient |
| PLAN-008 | SKU-CHS-SAU-008 | kg | 137 | 100 | 0 | 0.00 | Sufficient |

Blueberries are 16 kg short and juice is 13.25 kg short. The planner needs to confirm another
delivery or reschedule the affected orders. The amounts above value the missing material only.

## 4. Decisions

| Request | Decision | Effect |
| --- | --- | --- |
| CR-001 | Approve the 12 kg blueberry case from 1 September | Close the old mapping on 31 August and add the revised version. |
| CR-004 | Approve the juice conversion of 0.95 kg/L | Convert the receipts to kg while retaining their original quantities in L. |
| CR-002 | Confirm that the legacy mapping has expired | Keep RCV-0014 on hold until procurement confirms its delivery details or arranges a return. |
| CR-003 | Reject the proposed product-code resolution | Keep RCV-0012 on hold until the supplier confirms the product in writing. |

The decisions were recorded on 1 October and applied retrospectively to September.
The audit log records the approver, date, reason and supporting document for each decision.

## 5. Checks after correction

The original and corrected mappings were run through the same receipt and stock calculations.
The [receipt comparison](../data/processed/receipt_changes.csv) lists the mapping, quantity and
value before and after each correction.

| Check | Calculated | Control total | Result |
| --- | --- | --- | --- |
| All imported rows accounted for | 20 | 20 | PASS |
| Reporting count agrees with receipt detail | 17 | 17 | PASS |
| Unique source document lines in cleared receipts | 17 | 17 | PASS |
| Receipt value agrees with the summary (NZD) | 7,445.60 | 7,445.60 | PASS |
| Product-code conflicts remaining after correction | 1 | 1 | PASS |

Receipts cleared for reporting increased from **14 to 17**.
The remaining inventory difference is **NZD 18.00**.
No inventory adjustment was entered to remove the mango shortage.

The process retains the source records. If a decision is reversed, a new audit event records
the reversal and the calculations are rerun from the original mappings.

## 6. Outstanding actions

| Case | Issue | Owner | Due | Next action | Latest check |
| --- | --- | --- | --- | --- | --- |
| CASE-006 | Disputed product code | master-data-team@example.com | 2026-10-05 | CR-003 rejected; obtain written SKU confirmation | Still excluded from eligible receipts and available counts; identity remains unconfirmed |
| CASE-005 | Expired supplier mapping | procurement@example.com | 2026-10-02 | CR-002 retirement confirmed; obtain valid delivery evidence or arrange return | Still excluded from eligible receipts and available counts; identity remains unconfirmed |
| CASE-007 | Unexplained count shortage | warehouse-supervisor@example.com | 2026-10-02 | Recount stock and verify production issue documents before adjustment | Residual persists after replay; SKU-level count cannot attribute the shortage to a batch |
| CASE-020 | Material shortfall | production-planner@example.com | 2026-10-02 | Confirm supply or reschedule order | Estimated material gap for 3 October; no lost production or sales value assumed |
| CASE-021 | Material shortfall | production-planner@example.com | 2026-10-02 | Confirm supply or reschedule order | Estimated material gap for 3 October; no lost production or sales value assumed |

The dates above are assessed as of 2 October 2026. The [case register](../data/processed/case_register.csv)
contains the receipt IDs, SKUs, batches, quantities, valuation assumptions and latest check for each item.
Held receipts remain unvalued in the stock report until the product and delivery details are confirmed.

## Reproduce the case

Run `python src/run_case_study.py` to repeat the analysis using the supplied records and decision log.
See the [implementation guide](../docs/IMPLEMENTATION_GUIDE.md) for the calculation rules.

This case covers a receipt and inventory investigation. It does not estimate production downtime,
lost sales or realised savings.
