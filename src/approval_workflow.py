"""
Approval Workflow & Audit Trail — Food Manufacturing Master Data Case Study
==========================================================================
Simulates the manual decision process for change requests:
  - approve / reject actions with approver identity, reason, timestamp
  - Full audit log appended to data/processed/decision_log.csv
  - Approved mapping changes are applied to a working copy of the mapping
    table (never mutate raw source data)
  - Before/after snapshots enable impact traceability

Idempotent: re-running with the same decisions does not duplicate log
entries (decision_id is deterministic per cr_id + action).

Run:  python src/approval_workflow.py
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline_core import RAW_DIR, PROCESSED_DIR, load_raw_data

DECISION_LOG = PROCESSED_DIR / "decision_log.csv"
APPROVED_MAP = PROCESSED_DIR / "mapping_with_approved_changes.csv"


def _decision_id(cr_id: str, action: str, ts: str) -> str:
    """Deterministic ID so re-runs never duplicate audit entries."""
    raw = f"{cr_id}|{action}|{ts}"
    return "DEC-" + hashlib.sha1(raw.encode()).hexdigest()[:10].upper()


def make_decisions() -> list[dict]:
    """
    Simulated analyst decisions for the 4 pre-loaded change requests.
    In a real workflow these would come from a UI / ticketing system.
    """
    ts = datetime.now(timezone.utc).isoformat()
    return [
        {"cr_id": "CR-001", "action": "approve",
         "approver": "master-data-lead@example.com",
         "reason": "Supplier re-pack confirmed by procurement; apply 12kg case from 2026-09-01",
         "decision_ts": "2026-10-01T09:00:00+00:00"},
        {"cr_id": "CR-002", "action": "approve",
         "approver": "master-data-lead@example.com",
         "reason": "Legacy supplier contract ended; retire mapping LF-BER-OLD",
         "decision_ts": "2026-10-01T09:30:00+00:00"},
        {"cr_id": "CR-003", "action": "reject",
         "approver": "master-data-lead@example.com",
         "reason": "Ambiguous code NF-AMB-01 disputed by two teams; needs supplier clarification before any change",
         "decision_ts": "2026-10-01T10:00:00+00:00"},
        {"cr_id": "CR-004", "action": "approve",
         "approver": "warehouse-supervisor@example.com",
         "reason": "UoM conversion L->kg approved with density factor 0.95 for apple juice concentrate",
         "decision_ts": "2026-10-01T10:30:00+00:00"},
    ]


def apply_approvals() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Apply approved change requests to a working copy of the mapping table.
    Returns (updated_mapping, decision_log_df).
    """
    raw = load_raw_data()
    mapping = raw["mapping"].copy()
    cr = raw["change_requests"]

    decisions = make_decisions()
    log_rows: list[dict] = []
    ts_now = datetime.now(timezone.utc).isoformat()

    for d in decisions:
        cr_row = cr[cr["cr_id"] == d["cr_id"]].iloc[0]
        ts = d["decision_ts"]
        decision = {
            "decision_id": _decision_id(d["cr_id"], d["action"], ts),
            "cr_id": d["cr_id"],
            "action": d["action"],
            "approver": d["approver"],
            "reason": d["reason"],
            "decision_timestamp": ts,
            "supplier": cr_row["supplier"],
            "supplier_item_code": cr_row["supplier_item_code"],
            "proposed_sku": cr_row["proposed_sku"],
            "cr_type": cr_row["cr_type"],
        }
        log_rows.append(decision)

        if d["action"] != "approve":
            continue

        if d["cr_id"] == "CR-001":
            # Re-pack: close old version, insert new version
            mask = (mapping["supplier_item_code"] == "NF-BER-01") & \
                   (mapping["effective_to"].astype(str).str.startswith("2099"))
            if mask.any():
                idx = mapping.index[mask][0]
                mapping.loc[idx, "effective_to"] = pd.Timestamp("2026-08-31").date()
            new_row = {
                "mapping_id": "MAP-CR001",
                "supplier": "SUP-NORTHFROST",
                "supplier_item_code": "NF-BER-10",
                "sku": "SKU-FZN-BER-001",
                "effective_from": pd.Timestamp("2026-09-01").date(),
                "effective_to": pd.Timestamp("2099-12-31").date(),
                "supplier_uom": "kg",
                "pack_size_pieces_per_case": 12,
            }
            mapping = pd.concat([mapping, pd.DataFrame([new_row])],
                                 ignore_index=True)
        elif d["cr_id"] == "CR-002":
            mask = mapping["supplier_item_code"] == "LF-BER-OLD"
            mapping.loc[mask, "effective_to"] = pd.Timestamp("2026-07-31").date()
        elif d["cr_id"] == "CR-004":
            mask = mapping["supplier_item_code"] == "SC-JCE-20L"
            mapping.loc[mask, "supplier_uom"] = "L"

    log_df = pd.DataFrame(log_rows)
    return mapping, log_df


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    mapping, log_df = apply_approvals()
    APPROVED_MAP.parent.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(APPROVED_MAP, index=False)
    if DECISION_LOG.exists():
        existing = pd.read_csv(DECISION_LOG, dtype=str)
        log_df = pd.concat([existing, log_df], ignore_index=True)
        log_df = log_df.drop_duplicates(subset=["decision_id"], keep="last")
    log_df.to_csv(DECISION_LOG, index=False)
    print(f"Approval workflow complete: {len(log_df)} decisions logged, "
          f"updated mapping saved")
    return mapping, log_df


if __name__ == "__main__":
    run()
