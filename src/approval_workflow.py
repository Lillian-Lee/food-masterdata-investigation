"""Replayable simulated decisions. Reversal appends evidence; it never deletes logs."""
import argparse
import hashlib
from datetime import timedelta
import pandas as pd
from pipeline_core import load_raw_data, PROCESSED_DIR

DECISION_LOG = PROCESSED_DIR / "decision_log.csv"
APPROVED_MAP = PROCESSED_DIR / "mapping_with_approved_changes.csv"


def _decision_id(cr_id,action,ts):
    return "DEC-"+hashlib.sha256(f"{cr_id}|{action}|{ts}".encode()).hexdigest()[:12].upper()


def make_decisions():
    reasons = ["Supplier confirmed 12kg per case", "Retirement confirmed; late receipt remains on hold",
               "Rejected: disputed SKU identity requires supplier clarification",
               "Approved synthetic density specification: 0.95 kg per litre"]
    return [dict(cr_id=f"CR-{i:03d}",action="reject" if i==3 else "approve",
        approver="master-data-lead@example.com",reason=reasons[i-1],
        decision_timestamp=f"2026-10-01T{8+i:02d}:00:00+00:00")
        for i in range(1,5)]


def overlap_pairs(mapping):
    pairs = set()
    for _,g in mapping.groupby(["supplier","supplier_item_code"]):
        records = g.to_dict("records")
        for i,a in enumerate(records):
            for b in records[i+1:]:
                if max(a["effective_from"],b["effective_from"])<=min(a["effective_to"],b["effective_to"]):
                    pairs.add(tuple(sorted([a["mapping_id"],b["mapping_id"]])))
    return pairs


def apply_approvals(raw=None, decisions=None):
    raw = raw if raw is not None else load_raw_data()
    mapping = raw["mapping"].copy()
    decisions = pd.DataFrame(make_decisions()) if decisions is None else pd.DataFrame(decisions).copy()
    logs = []
    crs = raw["change_requests"].set_index("cr_id")
    for _,d in decisions.iterrows():
        if d["cr_id"] not in crs.index or d["action"] not in ("approve","reject","revoke"):
            raise ValueError("Unknown change request or decision action")
        cr = crs.loc[d["cr_id"]]
        logs.append(dict(d, decision_id=_decision_id(d["cr_id"],d["action"],d["decision_timestamp"]),
            supplier=cr["supplier"],supplier_item_code=cr["supplier_item_code"],
            proposed_sku=cr["proposed_sku"],cr_type=cr["cr_type"],evidence_ref=cr["evidence_ref"]))
    log = pd.DataFrame(logs)
    if log.empty:
        return mapping, log
    latest = log.sort_values(["decision_timestamp","decision_id"]).drop_duplicates("cr_id",keep="last")
    existing_overlaps = overlap_pairs(mapping)
    for _,d in latest.iterrows():
        if d["action"]!="approve":
            continue
        cr = crs.loc[d["cr_id"]]
        mask = (mapping["supplier"]==cr["supplier"]) & (mapping["supplier_item_code"]==cr["supplier_item_code"])
        if cr["cr_type"]=="retire_mapping":
            mapping.loc[mask & (mapping["effective_to"]>=cr["effective_from"]),"effective_to"] = cr["effective_from"]-timedelta(days=1)
            continue
        if cr["cr_type"] not in ("repack","unit_change"):
            raise ValueError("Unsupported approval type")
        if cr["proposed_base_qty_per_case"]<=0 or cr["proposed_conversion_factor"]<=0:
            raise ValueError("Approved conversion factors must be positive")
        active = mapping[mask & (mapping["effective_from"]<=cr["effective_from"]) &
                         (mapping["effective_to"]>=cr["effective_from"])]
        if len(active)!=1:
            raise ValueError(f'{d["cr_id"]}: approval requires exactly one baseline version')
        template = active.iloc[0].to_dict()
        new_id = "MAP-"+d["cr_id"].replace("-","")
        new = dict(template,mapping_id=new_id,effective_from=cr["effective_from"],
            sku=cr["proposed_sku"],base_qty_per_case=cr["proposed_base_qty_per_case"],
            conversion_factor=cr["proposed_conversion_factor"],approval_cr_id=d["cr_id"])
        old_index = active.index[0]
        if template["effective_from"]==cr["effective_from"]:
            mapping = mapping.drop(old_index)
        else:
            mapping.loc[old_index,"effective_to"] = cr["effective_from"]-timedelta(days=1)
        mapping = pd.concat([mapping,pd.DataFrame([new])],ignore_index=True)
    if overlap_pairs(mapping)-existing_overlaps:
        raise ValueError("Approval introduced overlapping mapping versions")
    return mapping.sort_values("mapping_id").reset_index(drop=True), log.sort_values("decision_timestamp").reset_index(drop=True)


def run(revoke=None):
    PROCESSED_DIR.mkdir(parents=True,exist_ok=True)
    decisions = pd.DataFrame(make_decisions())
    if DECISION_LOG.exists():
        old = pd.read_csv(DECISION_LOG)
        if "decision_timestamp" not in old:
            raise ValueError("Old ledger schema must be archived before migration")
        decisions = pd.concat([old,decisions],ignore_index=True)[list(make_decisions()[0])]
    if revoke:
        # Fixed case-study review timestamp makes repeated reversals idempotent.
        decisions = pd.concat([decisions,pd.DataFrame([dict(cr_id=revoke,action="revoke",
            approver="master-data-lead@example.com",reason="Synthetic reversal requested; replay baseline",
            decision_timestamp="2026-10-02T12:00:00+00:00")])],ignore_index=True)
    decisions = decisions.drop_duplicates(["cr_id","action","decision_timestamp"])
    mapping,log = apply_approvals(decisions=decisions)
    mapping.to_csv(APPROVED_MAP,index=False)
    log.to_csv(DECISION_LOG,index=False)
    print(f"Approval replay: {len(log)} audit events, {len(mapping)} mapping versions")
    return mapping,log


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--revoke",choices=[f"CR-{i:03d}" for i in range(1,5)])
    run(parser.parse_args().revoke)
