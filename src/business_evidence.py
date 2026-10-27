"""Inventory rollforward, receipt-level changes and actionable case evidence.

Values are NZD standard-cost estimates, not realised savings. Mixed UoMs are
never summed. Held-stock candidate values are conditional, never posted.
"""
import pandas as pd
from pipeline_core import PERIOD_START, PERIOD_END, AS_OF


def reconcile_inventory(raw, result):
    rows = []
    for _,p in raw['products'].iterrows():
        sku = p['sku']
        counts = raw['inventory'][raw['inventory']['sku'].eq(sku)]
        opening = counts[counts['snapshot_date'].eq(PERIOD_START-pd.Timedelta(days=1))]
        closing = counts[counts['snapshot_date'].eq(PERIOD_END)]
        if len(opening)!=1 or len(closing)!=1:
            raise ValueError(f'{sku}: opening and closing count evidence required')
        mov = raw['movements'][raw['movements']['sku'].eq(sku) &
            raw['movements']['movement_date'].between(PERIOD_START,PERIOD_END)]
        receipts = result.cleansed_receipts[result.cleansed_receipts['resolved_sku'].eq(sku)]
        qty = float(receipts['qty_base'].sum())
        expected = float(opening.iloc[0]['qty_on_hand']+qty+mov['qty_base'].sum())
        counted = float(closing.iloc[0]['qty_on_hand'])
        variance = counted-expected
        held = result.review_queue
        candidates = held['candidate_skus'].fillna('').str.split('; ').map(lambda values:sku in values)
        unknown_count = int(candidates.sum())
        rows.append(dict(sku=sku,product=p['product_name'],base_uom=p['base_uom'],
            opening_qty=float(opening.iloc[0]['qty_on_hand']),eligible_receipts_qty=qty,
            net_movements_qty=float(mov['qty_base'].sum()),expected_closing_qty=round(expected,4),
            counted_closing_qty=counted,variance_qty=round(variance,4),
            unit_cost_nzd=float(p['standard_cost_nzd_per_base']),
            variance_nzd=round(variance*p['standard_cost_nzd_per_base'],2),
            unresolved_candidate_receipts=unknown_count,
            reconciliation_status='variance_to_investigate' if abs(variance)>.0001 else 'matched_eligible_stock',
            evidence_refs='; '.join([opening.iloc[0]['evidence_ref'],closing.iloc[0]['evidence_ref']]+mov['evidence_ref'].tolist()),
            receipt_ids='; '.join(receipts['receipt_id']),batch_refs='; '.join(sorted(receipts['batch_ref'].unique()))))
    return pd.DataFrame(rows)


def compare_receipts(before, after):
    cols = ['receipt_id','resolved_sku','mapping_id','qty_base','base_uom','receipt_value_nzd','disposition']
    comparison = before.all_receipts[cols].merge(after.all_receipts[cols],on='receipt_id',suffixes=('_before','_after'),validate='one_to_one')
    comparison['comparable_quantity'] = comparison['qty_base_before'].notna() & comparison['qty_base_after'].notna() & comparison['base_uom_before'].eq(comparison['base_uom_after'])
    comparison['qty_delta'] = (comparison['qty_base_after']-comparison['qty_base_before']).where(comparison['comparable_quantity'])
    comparison['value_delta_nzd'] = (comparison['receipt_value_nzd_after']-comparison['receipt_value_nzd_before']).where(comparison['comparable_quantity'])
    comparison['newly_eligible_value_nzd'] = comparison['receipt_value_nzd_after'].where(
        comparison['disposition_after'].eq('reporting_ready') & ~comparison['disposition_before'].eq('reporting_ready'))
    comparison['changed'] = comparison['disposition_before'].ne(comparison['disposition_after']) | comparison['qty_delta'].fillna(0).abs().gt(.0001)
    return comparison


def production_impact(raw, reconciliation):
    rows = []
    for _,req in raw['requirements'].iterrows():
        r = reconciliation.set_index('sku').loc[req['sku']]
        # No assumed inbound after 30 September. Counted stock excludes the held receipts.
        available = max(min(r['counted_closing_qty'],r['expected_closing_qty']),0)
        gap = max(req['required_qty_base']-available,0)
        rows.append(dict(production_order=req['production_order'],sku=req['sku'],base_uom=req['uom'],
            required_date=req['required_date'],required_qty_base=float(req['required_qty_base']),
            conservative_available_qty=round(available,4),shortfall_qty=round(gap,4),
            shortfall_value_nzd=round(gap*r['unit_cost_nzd'],2),
            risk='material_shortfall' if gap>0 else 'covered',owner=req['owner'],
            action_due='2026-10-02',action='Confirm supply or reschedule order' if gap>0 else 'Monitor scheduled demand',
            evidence_ref=req['evidence_ref']))
    return pd.DataFrame(rows)


def build_cases(raw,before,after,comparison,reconciliation,production):
    rows = []
    def add(case_id,category,ids,skus,qty,uom,amount,status,owner,due,decision,evidence,review,**extra):
        receipts = after.all_receipts[after.all_receipts['receipt_id'].isin(ids)]
        row = dict(case_id=case_id,category=category,receipt_ids='; '.join(ids),affected_skus=skus,
            batch_refs='; '.join(sorted(receipts['batch_ref'].unique())),impact_qty=qty,base_uom=uom,
            amount_nzd=amount,status=status,owner=owner,due_date=due,as_of_date=AS_OF,
            decision=decision,evidence_refs=evidence,verification_result=review,
            verified_at='2026-10-02' if status=='closed' else None,
            valuation_basis='Standard cost estimate; no realised savings',value_low_nzd=None,value_high_nzd=None)
        row.update(extra)
        rows.append(row)
    berries = comparison[comparison['comparable_quantity'] & comparison['qty_delta'].abs().gt(.0001) & comparison['disposition_after'].eq('reporting_ready')]
    if not berries.empty:
        add('CASE-001','pack_quantity_correction',berries['receipt_id'].tolist(),'SKU-FZN-BER-001',
            float(berries['qty_delta'].sum()),'kg',round(float(berries['value_delta_nzd'].sum()),2),
            'closed','master-data-team@example.com','2026-10-02',
            'CR-001 approved: 12kg per case from 1 September','REP-001; CR-001; MAP-CR001',
            'Replayed approved mapping; no new overlaps; corrected quantity matches eligible stock count')
    new = comparison[comparison['newly_eligible_value_nzd'].notna()]
    if not new.empty:
        add('CASE-002','approved_unit_conversion',new['receipt_id'].tolist(),'SKU-APL-JCE-003',
            float(new['qty_base_after'].sum()),'kg',round(float(new['newly_eligible_value_nzd'].sum()),2),
            'closed','master-data-team@example.com','2026-10-02',
            'CR-004 approved: litres x 0.95 = kg','DENS-004; CR-004; MAP-CR004',
            'Converted quantities recalculated; no raw unit overwrite; eligible stock count reconciles')
    for _,d in after.duplicate_receipts.iterrows():
        add('CASE-003','duplicate_import_excluded',[d['receipt_id']],d['resolved_sku'],d['qty_base'],d['base_uom'],
            round(d['receipt_value_nzd'],2),'closed','warehouse-ops@example.com','2026-10-02',
            'Exclude repeated source document line; retain original and duplicate as evidence',d['source_line_id'],
            'Canonical source line counted exactly once; this is prevented overstatement, not a saving')
    for _,r in after.cleansed_receipts[after.cleansed_receipts['late_posting']].iterrows():
        add('CASE-004','late_posting',[r['receipt_id']],r['resolved_sku'],r['qty_base'],r['base_uom'],
            round(r['receipt_value_nzd'],2),'closed','warehouse-ops@example.com','2026-10-02',
            'Include in September receipt-date restatement as of 2 October',r['source_line_id'],
            'Receipt 16 September; posted 2 October; late flag verified; value overlaps conversion case')
    prod = raw['products'].set_index('sku')
    for _,r in after.review_queue.iterrows():
        candidates = r['candidate_skus'].split('; ') if r['candidate_skus'] else []
        prices = [float(prod.loc[s,'standard_cost_nzd_per_base']) for s in candidates if prod.loc[s,'base_uom']==r['receipt_uom']]
        low = round(r['qty_received']*min(prices),2) if prices else None
        high = round(r['qty_received']*max(prices),2) if prices else None
        ambiguous = r['mapping_status']=='ambiguous_mapping'
        add('CASE-006' if ambiguous else 'CASE-005',r['mapping_status'],[r['receipt_id']],r['candidate_skus'],
            r['qty_received'],r['receipt_uom'],None,'open',
            'master-data-team@example.com' if ambiguous else 'procurement@example.com',
            '2026-10-05' if ambiguous else '2026-10-02',
            'CR-003 rejected; obtain written SKU confirmation' if ambiguous else 'CR-002 retirement confirmed; obtain valid delivery evidence or arrange return',
            f"{r['source_line_id']}; {'DIS-003; CR-003' if ambiguous else 'TERM-002; CR-002'}",
            'Still excluded from eligible receipts and available counts; identity remains unconfirmed',
            value_low_nzd=low,value_high_nzd=high,
            valuation_basis='Conditional candidate-SKU exposure; not posted and not a confirmed loss')
    for i,(_,r) in enumerate(reconciliation[reconciliation['variance_qty'].abs().gt(.0001)].iterrows(),7):
        add(f'CASE-{i:03d}','residual_inventory_variance',[],r['sku'],r['variance_qty'],r['base_uom'],
            r['variance_nzd'],'open','warehouse-supervisor@example.com','2026-10-02',
            'Recount stock and verify production issue documents before adjustment',r['evidence_refs'],
            'Residual persists after replay; SKU-level count cannot attribute the shortage to a batch',
            batch_refs='Pending: SKU-level counts; batch attribution unconfirmed')
    for i,(_,r) in enumerate(production[production['shortfall_qty'].gt(0)].iterrows(),20):
        add(f'CASE-{i:03d}','production_material_risk',[],r['sku'],r['shortfall_qty'],r['base_uom'],
            r['shortfall_value_nzd'],'open',r['owner'],r['action_due'],r['action'],
            r['production_order']+'; '+r['evidence_ref'],
            'Estimated material gap for 3 October; no lost production or sales value assumed',
            batch_refs='Not allocated: SKU-level production requirement')
    df = pd.DataFrame(rows)
    # Approval alone is not sufficient to close the investigation if its stock still fails reconciliation.
    for idx,r in df[df['category'].isin(['pack_quantity_correction','approved_unit_conversion'])].iterrows():
        stock = reconciliation[reconciliation['sku'].eq(r['affected_skus'])]
        if stock['variance_qty'].abs().gt(.0001).any():
            df.loc[idx,'status'] = 'open'
            df.loc[idx,'verified_at'] = None
            df.loc[idx,'verification_result'] = 'Approved arithmetic replayed; physical count discrepancy remains. Recount before closure.'
    df['deadline_status'] = df.apply(lambda r:'closed' if r['status']=='closed' else (
        'overdue' if pd.Timestamp(r['due_date']).date()<AS_OF else 'due_today' if pd.Timestamp(r['due_date']).date()==AS_OF else 'scheduled'),axis=1)
    return df
