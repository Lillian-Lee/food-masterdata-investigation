"""Behavioural regressions covering the real replay, evidence and report boundaries."""
import copy
import hashlib
import unittest
from unittest.mock import patch
from pathlib import Path
import pandas as pd
from pandas.testing import assert_frame_equal
from pipeline_core import load_raw_data, resolve_mappings, detect_duplicate_receipts, RAW_DIR
from approval_workflow import apply_approvals, make_decisions, overlap_pairs
from run_investigation import investigate, build_quality_summary
from uom_checks import check_uom_consistency, flag_effective_boundary
from business_evidence import reconcile_inventory, compare_receipts, production_impact, build_cases


class AuditRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=load_raw_data()
        cls.mapping,cls.log=apply_approvals(cls.raw)
        cls.before=investigate(cls.raw,cls.raw["mapping"])
        cls.after=investigate(cls.raw,cls.mapping)
        cls.reconciliation=reconcile_inventory(cls.raw,cls.after)
        cls.comparison=compare_receipts(cls.before,cls.after)
        cls.production=production_impact(cls.raw,cls.reconciliation)

    def test_approval_does_not_introduce_mapping_ambiguity(self):
        self.assertFalse(overlap_pairs(self.mapping)-overlap_pairs(self.raw["mapping"]))
        self.assertEqual(self.after.quality_summary["ambiguous_mappings"],1)

    def test_summary_matches_actual_reporting_slice(self):
        self.assertEqual(len(self.after.cleansed_receipts),17)
        self.assertEqual(self.after.quality_summary["reporting_ready"],17)
        self.assertEqual(len(self.after.review_queue)+len(self.after.duplicate_receipts)+len(self.after.cleansed_receipts),20)

    def test_boundary_independent_of_mapping_order_and_checks_end(self):
        row=self.raw["receipts"].iloc[[0]].copy()
        row["receipt_date"]=pd.Timestamp("2026-08-31").date()
        resolved,_=resolve_mappings(row,self.mapping)
        a=flag_effective_boundary(resolved,self.mapping)
        b=flag_effective_boundary(resolved,self.mapping.iloc[::-1])
        self.assertEqual(a["near_boundary"].tolist(),[True])
        self.assertEqual(a["near_boundary"].tolist(),b["near_boundary"].tolist())
        self.assertEqual(a["days_to_boundary"].tolist(),b["days_to_boundary"].tolist())

    def test_empty_review_is_valid(self):
        raw=copy.deepcopy(self.raw)
        raw["receipts"]=raw["receipts"].iloc[[2]]
        result=investigate(raw,self.mapping)
        self.assertEqual(result.quality_summary["reporting_ready"],1)
        self.assertTrue(result.review_queue.empty)

    def test_all_review_is_valid(self):
        raw=copy.deepcopy(self.raw)
        raw["receipts"]=raw["receipts"][raw["receipts"]["receipt_id"].isin(["RCV-0012","RCV-0014"])]
        result=investigate(raw,self.mapping)
        self.assertTrue(result.cleansed_receipts.empty)
        self.assertEqual(result.quality_summary["routed_to_review"],2)

    def test_zero_receipts_is_valid(self):
        raw=copy.deepcopy(self.raw)
        raw["receipts"]=raw["receipts"].iloc[:0]
        result=investigate(raw,self.mapping)
        self.assertEqual(result.quality_summary["reporting_ready"],0)

    def test_litres_to_kg_is_applied_only_after_approval(self):
        before=self.before.all_receipts.set_index("receipt_id").loc["RCV-0002"]
        after=self.after.all_receipts.set_index("receipt_id").loc["RCV-0002"]
        self.assertEqual(before["mapping_status"],"unapproved_conversion")
        self.assertTrue(pd.isna(before["qty_base"]))
        self.assertEqual(after["qty_received"],50)
        self.assertEqual(after["receipt_uom"],"L")
        self.assertAlmostEqual(after["qty_base"],47.5)
        self.assertEqual(after["base_uom"],"kg")

    def test_case_conversion_and_historical_version(self):
        after=self.after.all_receipts.set_index("receipt_id").loc["RCV-0004"]
        self.assertEqual(after["qty_base"],144)
        row=self.raw["receipts"].iloc[[3]].copy()
        row["receipt_date"]=pd.Timestamp("2026-08-31").date()
        resolved,_=resolve_mappings(row,self.mapping)
        historical=check_uom_consistency(resolved,self.raw["products"])
        self.assertEqual(historical.iloc[0]["qty_base"],120)
        self.assertEqual(historical.iloc[0]["mapping_id"],"MAP-001")

    def test_before_after_is_real_not_copied(self):
        self.assertEqual(self.before.quality_summary["reporting_ready"],14)
        self.assertEqual(self.after.quality_summary["reporting_ready"],17)
        self.assertAlmostEqual(self.before.quality_summary["eligible_receipt_value_nzd"],6315)
        self.assertAlmostEqual(self.after.quality_summary["eligible_receipt_value_nzd"],7445.6)
        rows=self.comparison[self.comparison["disposition_after"].eq("reporting_ready")]
        self.assertAlmostEqual(rows["qty_delta"].sum(),74)
        self.assertAlmostEqual(rows["value_delta_nzd"].sum(),629)
        self.assertAlmostEqual(rows["newly_eligible_value_nzd"].sum(),501.6)

    def test_inventory_independent_counts_leave_real_residual(self):
        rec=self.reconciliation.set_index("sku")
        self.assertEqual(rec.loc["SKU-FZN-BER-001","expected_closing_qty"],644)
        self.assertEqual(rec.loc["SKU-APL-JCE-003","expected_closing_qty"],156.75)
        self.assertEqual(rec.loc["SKU-FZN-MAN-002","variance_qty"],-3)
        self.assertEqual(rec.loc["SKU-FZN-MAN-002","variance_nzd"],-18)
        raw=copy.deepcopy(self.raw)
        raw["inventory"].loc[(raw["inventory"]["sku"]=="SKU-FZN-BER-001") &
            (raw["inventory"]["snapshot_date"]==pd.Timestamp("2026-09-30").date()),"qty_on_hand"]+=7
        changed=reconcile_inventory(raw,self.after).set_index("sku")
        self.assertEqual(changed.loc["SKU-FZN-BER-001","variance_qty"],7)

    def test_production_shortfalls_are_material_not_lost_sales(self):
        p=self.production.set_index("sku")
        self.assertEqual(p.loc["SKU-FZN-BER-001","shortfall_qty"],16)
        self.assertEqual(p.loc["SKU-APL-JCE-003","shortfall_qty"],13.25)
        self.assertEqual(int(self.production["shortfall_qty"].gt(0).sum()),2)

    def test_rejected_receipts_remain_excluded_and_unvalued(self):
        held=set(self.after.review_queue["receipt_id"])
        self.assertEqual(held,{"RCV-0012","RCV-0014"})
        self.assertTrue(self.after.review_queue["qty_base"].isna().all())
        self.assertFalse(held & set(self.after.cleansed_receipts["receipt_id"]))

    def test_source_line_not_batch_is_duplicate_key(self):
        receipts=self.raw["receipts"].iloc[[3]].copy()
        another=receipts.copy()
        another["receipt_id"]="RCV-9999"
        another["source_line_id"]="OTHER-GRN-1"
        combined=pd.concat([receipts,another],ignore_index=True)
        _,ids=detect_duplicate_receipts(combined)
        self.assertEqual(ids,[])
        _,original=detect_duplicate_receipts(self.raw["receipts"].iloc[::-1])
        self.assertEqual(original,["RCV-0016"])

    def test_conflicting_duplicate_cannot_be_silently_dropped(self):
        receipts=self.raw["receipts"].copy()
        receipts.loc[receipts["receipt_id"].eq("RCV-0016"),"qty_received"]=99
        with self.assertRaisesRegex(ValueError,"Conflicting duplicate"):
            detect_duplicate_receipts(receipts)

    def test_late_posting_is_detected_from_dates(self):
        r=self.after.cleansed_receipts.set_index("receipt_id")
        self.assertTrue(r.loc["RCV-0015","late_posting"])
        self.assertFalse(r.loc["RCV-0002","late_posting"])

    def test_future_posting_is_excluded_as_of_case_review(self):
        raw=copy.deepcopy(self.raw)
        raw["receipts"].loc[raw["receipts"]["receipt_id"].eq("RCV-0015"),"posted_date"]=pd.Timestamp("2026-10-03").date()
        result=investigate(raw,self.mapping)
        self.assertEqual(result.quality_summary["out_of_period"],1)
        self.assertEqual(result.quality_summary["reporting_ready"],16)

    def test_missing_and_not_yet_effective_are_distinct(self):
        row=self.raw["receipts"].iloc[[2]].copy()
        row["supplier_item_code"]="UNKNOWN"
        _,review=resolve_mappings(row,self.mapping)
        self.assertEqual(review.iloc[0]["mapping_status"],"missing_mapping")
        row=self.raw["receipts"].iloc[[2]].copy()
        row["receipt_date"]=pd.Timestamp("2025-12-31").date()
        _,review=resolve_mappings(row,self.mapping)
        self.assertEqual(review.iloc[0]["mapping_status"],"not_yet_effective")

    def test_replay_idempotent(self):
        m,l=apply_approvals(self.raw,self.log)
        assert_frame_equal(m,self.mapping)
        self.assertEqual(set(l["decision_id"]),set(self.log["decision_id"]))

    def test_revoke_restores_baseline_without_deleting_audit(self):
        decisions=make_decisions()+[dict(cr_id="CR-001",action="revoke",approver="lead@example.com",
            reason="Regression reversal",decision_timestamp="2026-10-02T12:00:00+00:00")]
        mapping,log=apply_approvals(self.raw,decisions)
        self.assertEqual(len(log),5)
        self.assertIn("revoke",set(log["action"]))
        r=investigate(self.raw,mapping).all_receipts.set_index("receipt_id")
        self.assertEqual(r.loc["RCV-0004","qty_base"],120)
        self.assertEqual(r.loc["RCV-0004","mapping_id"],"MAP-001")

    def test_no_source_mutation_by_replay_or_reporting(self):
        digest=lambda:{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RAW_DIR.glob("*.csv")}
        original=digest()
        raw=load_raw_data()
        m,_=apply_approvals(raw)
        result=investigate(raw,m)
        rec=reconcile_inventory(raw,result)
        production_impact(raw,rec)
        self.assertEqual(original,digest())

    def test_every_case_has_business_evidence_and_pending_is_not_zero(self):
        cases=build_cases(self.raw,self.before,self.after,self.comparison,self.reconciliation,self.production)
        self.assertEqual(len(cases[cases["status"].eq("open")]),5)
        for col in ["owner","due_date","verification_result","evidence_refs","decision"]:
            self.assertTrue(cases[col].notna().all())
            self.assertTrue(cases[col].str.len().gt(0).all())
        held=cases[cases["category"].isin(["ambiguous_mapping","expired_mapping"])]
        self.assertTrue(held["amount_nzd"].isna().all())
        amb=held[held["category"].eq("ambiguous_mapping")].iloc[0]
        self.assertEqual(amb["value_low_nzd"],40)
        self.assertEqual(amb["value_high_nzd"],212.5)

    def test_approval_cannot_close_a_case_with_unreconciled_stock(self):
        raw=copy.deepcopy(self.raw)
        closing=raw['inventory']['sku'].eq('SKU-FZN-BER-001') & raw['inventory']['snapshot_date'].eq(pd.Timestamp('2026-09-30').date())
        raw['inventory'].loc[closing,'qty_on_hand']+=7
        rec=reconcile_inventory(raw,self.after)
        cases=build_cases(raw,self.before,self.after,self.comparison,rec,production_impact(raw,rec))
        pack=cases[cases['category'].eq('pack_quantity_correction')].iloc[0]
        self.assertEqual(pack['status'],'open')
        self.assertTrue(pd.isna(pack['verified_at']))
        self.assertIn('discrepancy remains',pack['verification_result'])

    def test_invalid_source_quantity_and_missing_count_fail_explicitly(self):
        original_reader=pd.read_csv
        def invalid_receipts(path,**kwargs):
            df=original_reader(path,**kwargs)
            if Path(path).name=='goods_received.csv':
                df.loc[0,'qty_received']='-2'
            return df
        with patch('pipeline_core.pd.read_csv',side_effect=invalid_receipts):
            with self.assertRaisesRegex(ValueError,"positive"):
                load_raw_data()
        raw=copy.deepcopy(self.raw)
        raw["inventory"]=raw["inventory"].iloc[1:]
        with self.assertRaisesRegex(ValueError,"count evidence"):
            reconcile_inventory(raw,self.after)


if __name__=="__main__":
    unittest.main(verbosity=2)
