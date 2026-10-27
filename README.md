# Food Supply Chain Master Data & Inventory Investigation

**Status:** Synthetic case study. One warehouse, 8 SKUs, September 2026.
**Review date:** 2 October 2026. All suppliers, people, costs, demand and evidence are fictional.

## Read the case

Start with [the investigation report](reports/investigation_summary.md) for reading directly on GitHub.
The [Excel evidence workbook](reports/exception_report.xlsx) contains the calculations and action register.
Download [the HTML case study](reports/portfolio.html) and open it in a browser for the presentation view.

The report follows six sections:

**Business problem → Records reviewed → Findings and impact → Decisions → Checks after correction → Outstanding actions**

The case investigates September receiving errors caused by a supplier pack-size change and a missing
litre-to-kilogram conversion. It follows the corrections through to inventory reconciliation and the next
production run, with unresolved items assigned for follow-up.

## Findings

| Measure | Before correction | After correction |
|---|---:|---:|
| Imported receipt rows | 20 | 20 |
| Receipts cleared for reporting | 14 | 17 |
| Held for review | 5 | 2 |
| Duplicate source-line imports excluded | 1 | 1 |
| Value of cleared receipts (NZD) | 6,315.00 | 7,445.60 |
| Total absolute stock difference (NZD) | 1,148.60 | 18.00 |

- Packaging: 37 eligible cases change from 10 to 12 kg/case: **+74 kg, NZD 629.00**.
- Juice: 165 L × the approved synthetic 0.95 kg/L: **156.75 kg, worth NZD 501.60**, can now be included in the stock report.
- Duplicate: one repeated document line represents **144 kg / NZD 1,224.00** of prevented overstatement.
- Inventory: **3 kg / NZD 18.00 mango shortage** remains unexplained after correction.
- Next production: blueberries short **16 kg**, juice short **13.25 kg**, assuming no further inbound.

Some amounts overlap and should not be added together as savings. Receipts on hold remain outside
the stock value until their product and delivery details are confirmed. Production figures value the
missing material only.

## Reproduce

Python 3.10+ and pandas are required for the investigation, tests, HTML and Markdown.

```bash
pip install -r requirements.txt
python src/run_case_study.py
```

The full command also generates the workbook using the bundled Node.js runtime and @oai/artifact-tool.
Outside Codex, set ARTIFACT_NODE to Node.js and ARTIFACT_MODULE_ROOT to the node_modules directory
containing @oai/artifact-tool.

For the Python-only path:

```bash
python src/run_case_study.py --skip-workbook
```

The replay uses the supplied raw evidence and appends missing simulated decisions idempotently.
It **does not reset fixtures** or discard reversals. To intentionally recreate the supplied synthetic raw data:

```bash
python src/generate_synthetic_data.py
```

Generating fixtures resets raw inputs only. Existing decision history is preserved.
Use a fresh checkout to reproduce the exact initial decision history after experimenting with reversals.

## Investigation chain

1. **Source evidence:** immutable during analysis. Receipts carry quantity, explicit unit, physical receipt date,
   posting date, batch and source document line. Products supply base UoM and synthetic standard cost.
2. **Versioned selection:** supplier + code + receipt date must identify exactly one valid mapping.
   Ambiguous, missing, expired and not-yet-effective codes remain distinct.
3. **Approved quantity:** CASE uses effective base quantity per case. Supplier UoM uses an approved factor.
   Missing conversion factors block the record from reporting. kg and L are never aggregated as one quantity.
4. **Receipt disposition:** every imported row belongs to reporting-ready, review, duplicate-excluded or
   out-of-period. Source document line identifies duplicates; a shared batch alone is insufficient.
   Conflicting duplicate imports stop the run instead of arbitrarily choosing a quantity.
5. **Inventory:** opening + eligible receipts + signed production issues = expected closing.
   Independently supplied physical count − expected closing = variance. No balancing adjustment is created.
6. **Business action:** each case records affected SKUs/batches where attributable, quantity, valuation basis,
   evidence, owner, due date, decision and verification result. Unknown batch attribution is explicit.
7. **Production:** available quantity is the lower of counted eligible stock and expected ledger stock.
   Compare it with dated material requirements; held receipts and unconfirmed future inbound stay excluded.

September is a **receipt-date restatement as of 2 October**, not an original posting-date ledger.
The 1 October approvals are retrospective corrections with September effective dates.
Late-posted RCV-0015 is explicitly identified and included because it was known by the review date.
Counts describe available stock and exclude the two held receipts.

## Decisions and reversal

CR-001 adds the 12 kg case version; CR-004 adds the approved conversion of 0.95 kg/L.
CR-002 confirms an existing retirement while the late receipt stays on hold.
CR-003 rejects disputed product identity, keeping the receipt on hold.

```bash
python src/approval_workflow.py --revoke CR-001
python src/run_case_study.py
```

Reversal appends a deterministic revoke event and replays the baseline.
The log is never deleted for rollback. The most recent event for each request determines its application.
This is a simulated audit workflow with fictional identities, not a permission-controlled production approval service.

## Tests and outputs

```bash
python src/test_regressions.py
python src/test_labeled_cases.py
```

23 regression tests and 12 labelled cases cover real replay, historical pack boundaries, approved conversion,
no/only-review/empty populations, source-line duplicates, as-of cutoffs, independent count perturbation,
production gaps, rejected requests, reversal, raw-file immutability and pending valuation.

The Excel builder temporarily changes a receipt quantity to check that dependent formulas update,
then restores it. It also compares key figures with Python and checks for formula errors.
Worksheet previews are optional; see [validation notes](docs/VALIDATION.md) for the checks performed.

- data/raw/: eight source tables, including movement and dated material requirements.
- data/processed/: receipt dispositions, baseline/approved comparison, per-SKU inventory reconciliation,
  production impacts, actionable case register, source hashes and report input bundle.
- reports/portfolio.html: local responsive English case study.
- reports/investigation_summary.md: detailed English evidence narrative.
- reports/exception_report.xlsx: linked formulas, review controls, source tables and native chart.
- docs/IMPLEMENTATION_GUIDE.md: calculation definitions and scope.
- outputs/: ignored authoring output and previews.

The workbook recalculates quantity and valuation arithmetic. Mapping selection, approval state,
case closure and action evidence are Python snapshots: rerun the pipeline after those sources change.
Before replacing the earlier workbook, its existing local modification was preserved under
.local-backups/before-evidence-upgrade/. Backups are local and ignored by Git.

## Scope

The case covers receipt mapping, unit conversion, inventory reconciliation and a material availability check.
Purchase-order matching, BOM calculations, production scheduling and cost accounting are outside its scope.
