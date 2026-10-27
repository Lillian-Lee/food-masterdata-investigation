"""One receipt, one reporting disposition. Baseline and approved runs share one path."""
import json
import pandas as pd
from pipeline_core import (InvestigationResult, load_raw_data, detect_duplicate_receipts,
    resolve_mappings, PROCESSED_DIR, PERIOD_START, PERIOD_END, AS_OF)
from uom_checks import check_uom_consistency, flag_effective_boundary


def build_quality_summary(raw_receipts, flagged, resolved, review):
    """Resolved includes duplicates; final clean count excludes them exactly once."""
    statuses = review.get("mapping_status",pd.Series(dtype=str))
    clean = resolved[~resolved["is_duplicate"].astype(bool)] if not resolved.empty else resolved
    return dict(total_receipts=len(raw_receipts),resolved=len(resolved),
        duplicates_flagged=int(flagged["is_duplicate"].sum()),routed_to_review=len(review),
        ambiguous_mappings=int(statuses.eq("ambiguous_mapping").sum()),
        expired_mappings=int(statuses.eq("expired_mapping").sum()),
        missing_mappings=int(statuses.eq("missing_mapping").sum()),
        unapproved_conversions=int(statuses.eq("unapproved_conversion").sum()),
        near_boundary=int(clean.get("near_boundary",pd.Series(dtype=bool)).sum()),
        pack_size_changes=int(clean.get("pack_size_changed",pd.Series(dtype=bool)).sum()),
        clean_resolvable=len(clean),reporting_ready=len(clean))


def investigate(raw,mappings):
    receipts = raw["receipts"]
    flagged,_ = detect_duplicate_receipts(receipts)
    resolved,unmapped = resolve_mappings(flagged,mappings)
    resolved = flag_effective_boundary(check_uom_consistency(resolved,raw["products"]),mappings)
    resolved.loc[resolved["conversion_status"].ne("approved"),"mapping_status"] = "unapproved_conversion"
    all_rows = pd.concat([resolved,unmapped],ignore_index=True).sort_values("receipt_id")
    all_rows["late_posting"] = (all_rows["receipt_date"]<=PERIOD_END) & (all_rows["posted_date"]>PERIOD_END)
    all_rows["in_period"] = all_rows["receipt_date"].between(PERIOD_START,PERIOD_END)
    all_rows["known_as_of"] = all_rows["posted_date"]<=AS_OF
    all_rows["disposition"] = "review"
    all_rows.loc[all_rows["mapping_status"].eq("resolved") & all_rows["in_period"] & all_rows["known_as_of"],"disposition"] = "reporting_ready"
    all_rows.loc[~all_rows["in_period"] | ~all_rows["known_as_of"],"disposition"] = "out_of_period"
    all_rows.loc[all_rows["is_duplicate"].astype(bool),"disposition"] = "duplicate_excluded"
    clean = all_rows[all_rows["disposition"].eq("reporting_ready")].copy()
    review = all_rows[all_rows["disposition"].eq("review")].copy()
    duplicates = all_rows[all_rows["disposition"].eq("duplicate_excluded")].copy()
    eligible_resolved = all_rows[all_rows["mapping_status"].eq("resolved") & all_rows["in_period"] & all_rows["known_as_of"]]
    summary = build_quality_summary(receipts,flagged,eligible_resolved,review)
    summary["reporting_ready"] = summary["clean_resolvable"] = len(clean)
    summary["out_of_period"] = int(all_rows["disposition"].eq("out_of_period").sum())
    summary["late_postings"] = int(clean["late_posting"].sum())
    summary["eligible_receipt_value_nzd"] = round(float(clean["receipt_value_nzd"].sum()),2)
    assert len(clean)+len(review)+len(duplicates)+summary["out_of_period"]==len(receipts)
    return InvestigationResult(clean,review,summary,raw["change_requests"],all_rows,duplicates)


def run(write=True):
    raw = load_raw_data()
    # Materialise approved mappings from the ledger on every run; do not trust a stale CSV cache.
    from approval_workflow import apply_approvals, DECISION_LOG
    if not DECISION_LOG.exists():
        raise FileNotFoundError("Run approval_workflow.py first")
    mapping,log = apply_approvals(raw,pd.read_csv(DECISION_LOG))
    result = investigate(raw,mapping)
    result.approved_changes = log
    if write:
        PROCESSED_DIR.mkdir(parents=True,exist_ok=True)
        for name,df in [("cleansed_receipts",result.cleansed_receipts),("review_queue",result.review_queue),
                        ("receipt_dispositions",result.all_receipts),("duplicate_receipts",result.duplicate_receipts),
                        ("mapping_with_approved_changes",mapping)]:
            df.to_csv(PROCESSED_DIR/f"{name}.csv",index=False)
        (PROCESSED_DIR/"quality_summary.json").write_text(json.dumps(result.quality_summary,indent=2),encoding="utf-8")
    print("Approved pipeline:",result.quality_summary)
    return result


if __name__=="__main__":
    run()
