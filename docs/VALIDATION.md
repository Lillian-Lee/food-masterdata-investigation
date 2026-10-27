# Validation record

Validated on 27 October 2026. Business snapshot remains 2 October 2026.

- Full command: `python src/run_case_study.py` completed with exit code 0.
- 23 behavioural regression tests passed, including the original incorrect summary,
  overlapping approval, unit conversion, order-dependent boundary and empty-review failures.
- All 12 labelled scenarios passed. Late posting now checks the actual date-derived flag.
- Independent physical-count perturbation changes the inventory variance.
- Reversal preserves five audit events and restores the historical pack quantity.
- Raw CSV hashes do not change during investigation or replay.
- Workbook quantity perturbation changes inventory by the approved case factor and
  leaves availability capped by independent count evidence.
- Saved XLSX was reopened for inspection: eleven sheets, native table filters,
  freeze panes, correctly formatted approval dates, a native chart with Baseline and
  Approved labels, no cached formula errors, and the expected headline values.
- All eleven worksheet opening views were rendered and inspected. A discovered
  serial-date display was fixed and confirmed in the saved workbook.
- HTML has six ordered sections with internal navigation and links to the other outputs.

## Environment limits

Desktop Microsoft Excel was not used for a manual application check.
The in-app browser could not reach the local preview server, so HTML browser-based
visual and responsive testing was not completed. Local HTML remains self-contained.

The bundled Windows image renderer can fail during native cleanup after saving its PNGs.
Preview generation is optional (`node src/build_workbook.mjs --previews`); the normal
export path avoids rendering and completes successfully. This affects preview tooling,
not the saved workbook arithmetic or the default replay command.

## Scope of results

All values describe synthetic case assumptions. They are not actual savings or losses.
The residual shortage and held receipts remain open by design. Five unresolved action
items have owners, deadlines and explicit latest verification outcomes.
