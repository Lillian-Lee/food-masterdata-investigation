"""Case study report from independently recalculated evidence."""
import html
import hashlib
import json
from pathlib import Path
import pandas as pd
from approval_workflow import apply_approvals, run as run_approvals, DECISION_LOG
from pipeline_core import BASE_DIR, PROCESSED_DIR, load_raw_data
from run_investigation import investigate, run
from business_evidence import reconcile_inventory, compare_receipts, production_impact, build_cases

REPORTS_DIR = BASE_DIR/'reports'


def build_before_after(before,after):
    keys = ['total_receipts','duplicates_flagged','reporting_ready','routed_to_review','unapproved_conversions','late_postings','eligible_receipt_value_nzd']
    return pd.DataFrame([dict(metric=k,before=before.quality_summary[k],after=after.quality_summary[k],
        delta=round(after.quality_summary[k]-before.quality_summary[k],2)) for k in keys])


REPORT_LABELS = {
    'metric':'Measure','before':'Before correction','after':'After correction','delta':'Change',
    'sku':'SKU','base_uom':'Unit','opening_qty':'Opening stock',
    'eligible_receipts_qty':'Cleared receipts','net_movements_qty':'Production issues (signed)',
    'expected_closing_qty':'Expected closing stock','counted_closing_qty':'Closing count',
    'variance_qty':'Difference','variance_nzd':'Difference (NZD)',
    'production_order':'Order','conservative_available_qty':'Available stock',
    'required_qty_base':'Required','shortfall_qty':'Shortfall',
    'shortfall_value_nzd':'Material value (NZD)','risk':'Stock check',
    'check':'Check','actual':'Calculated','expected':'Control total','result':'Result',
    'case_id':'Case','category':'Issue','owner':'Owner','due_date':'Due',
    'decision':'Next action','verification_result':'Latest check'}
REPORT_VALUES = {
    'total_receipts':'Imported receipt rows','duplicates_flagged':'Duplicate imports excluded',
    'reporting_ready':'Receipts cleared for reporting','routed_to_review':'Receipts held for review',
    'unapproved_conversions':'Receipts awaiting a conversion factor',
    'late_postings':'Late postings included in the report',
    'eligible_receipt_value_nzd':'Value of cleared receipts (NZD)',
    'material_shortfall':'Shortfall','covered':'Sufficient',
    'ambiguous_mapping':'Disputed product code','expired_mapping':'Expired supplier mapping',
    'residual_inventory_variance':'Unexplained count shortage',
    'production_material_risk':'Material shortfall',
    'Receipt partition equals source':'All imported rows accounted for',
    'Reporting summary equals detail':'Reporting count agrees with receipt detail',
    'Canonical source lines':'Unique source document lines in cleared receipts',
    'Eligible receipt value (NZD)':'Receipt value agrees with the summary (NZD)',
    'Post-replay ambiguous receipts':'Product-code conflicts remaining after correction'}


def table(df,columns=None):
    df = df[columns].copy() if columns else df.copy()
    for name in ['metric','category','risk','check']:
        if name in df:
            df[name] = df[name].map(lambda value:REPORT_VALUES.get(value,value))

    def cell(value,money=False):
        if pd.isna(value):
            return 'Pending'
        if isinstance(value,float):
            formatted=f'{value:,.2f}'
            return formatted if money else formatted.rstrip('0').rstrip('.')
        return str(value).replace('|','/').replace('\n',' ')

    headers=[REPORT_LABELS.get(c,c) for c in df.columns]
    lines=['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']
    for row in df.itertuples(index=False,name=None):
        money_row=any(isinstance(v,str) and '(NZD)' in v for v in row)
        lines.append('| '+' | '.join(cell(v,'nzd' in c or money_row) for c,v in zip(df.columns,row))+' |')
    return '\n'.join(lines)


def build_bundle():
    raw = load_raw_data()
    if not DECISION_LOG.exists():
        run_approvals()
    after = run()
    before = investigate(raw,raw['mapping'])
    comparison = compare_receipts(before,after)
    rec_before = reconcile_inventory(raw,before)
    rec_after = reconcile_inventory(raw,after)
    production = production_impact(raw,rec_after)
    cases = build_cases(raw,before,after,comparison,rec_after,production)
    held_cases = cases[cases['receipt_ids'].isin(after.review_queue['receipt_id'])]
    after.review_queue = after.review_queue.merge(
        held_cases[['receipt_ids','case_id','owner','due_date','deadline_status','decision','verification_result']],
        left_on='receipt_id',right_on='receipt_ids',how='left',validate='one_to_one').drop(columns='receipt_ids')
    after.review_queue.to_csv(PROCESSED_DIR/'review_queue.csv',index=False)
    mapping,log = apply_approvals(raw,pd.read_csv(DECISION_LOG))
    checks = pd.DataFrame([
        dict(check='Receipt partition equals source',actual=len(after.all_receipts),expected=len(raw['receipts']),result='PASS'),
        dict(check='Reporting summary equals detail',actual=after.quality_summary['reporting_ready'],expected=len(after.cleansed_receipts),result='PASS'),
        dict(check='Canonical source lines',actual=after.cleansed_receipts['source_line_id'].nunique(),expected=len(after.cleansed_receipts),result='PASS'),
        dict(check='Eligible receipt value (NZD)',actual=round(after.cleansed_receipts['receipt_value_nzd'].sum(),2),expected=after.quality_summary['eligible_receipt_value_nzd'],result='PASS'),
        dict(check='Post-replay ambiguous receipts',actual=after.quality_summary['ambiguous_mappings'],expected=before.quality_summary['ambiguous_mappings'],result='PASS'),
    ])
    if not checks['actual'].eq(checks['expected']).all():
        raise AssertionError('Report evidence check failed')
    datasets = dict(before_after=build_before_after(before,after),receipt_changes=comparison,
        inventory_before=rec_before,inventory_after=rec_after,production_impact=production,
        case_register=cases,verification_checks=checks,approved_mapping=mapping,decision_log=log,
        receipts=after.all_receipts,source_receipts=raw['receipts'],products=raw['products'],
        inventory_sources=raw['inventory'],movements=raw['movements'],requirements=raw['requirements'],
        change_requests=raw['change_requests'])
    for name in ['before_after','receipt_changes','inventory_before','inventory_after',
                 'production_impact','case_register','verification_checks']:
        datasets[name].to_csv(PROCESSED_DIR/f'{name}.csv',index=False)
    datasets['quality_before'] = pd.DataFrame([before.quality_summary])
    datasets['quality_after'] = pd.DataFrame([after.quality_summary])
    payload = {k:json.loads(v.to_json(orient='records',date_format='iso')) for k,v in datasets.items()}
    payload['meta'] = dict(as_of='2026-10-02',period='September 2026',currency='NZD',synthetic=True,
        inventory_scope='Counted available stock excludes held receipts. No October inbound assumed.',
        amount_basis='Standard-cost estimates excluding GST. Categories overlap and must not be added as savings.')
    payload['meta']['source_sha256'] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((BASE_DIR/'data/raw').glob('*.csv'))}
    payload['meta']['decision_log_sha256'] = hashlib.sha256(DECISION_LOG.read_bytes()).hexdigest()
    return payload,datasets


def write_narrative(payload,d):
    before,after = payload['quality_before'][0],payload['quality_after'][0]
    rec = d['inventory_after']
    open_cases = d['case_register'][d['case_register']['status'].eq('open')]
    pack = d['case_register'][d['case_register']['category'].eq('pack_quantity_correction')]
    unit = d['case_register'][d['case_register']['category'].eq('approved_unit_conversion')]
    correction = float(pack['amount_nzd'].sum())
    newly = float(unit['amount_nzd'].sum())
    pack_qty = float(pack['impact_qty'].sum())
    unit_qty = float(unit['impact_qty'].sum())
    md = f'''# Food Supply Chain Master Data & Inventory Investigation

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

{table(d['before_after'])}

**Blueberries.** Applying the revised case size to 37 cases increases recorded receipts by
**{pack_qty:g} kg**, a stock value correction of **NZD {correction:,.2f}**.
The affected receipts are RCV-0001, RCV-0004 and RCV-0010, covering batches B-0901, B-0907 and B-0919.

**Juice concentrate.** The approved factor converts 165 L to **{unit_qty:g} kg**, worth
**NZD {newly:,.2f}**. These receipts can now be included in the stock report.
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

{table(rec,['sku','base_uom','opening_qty','eligible_receipts_qty','net_movements_qty','expected_closing_qty','counted_closing_qty','variance_qty','variance_nzd'])}

The corrections reconcile blueberries and juice to the counts. Mango remains 3 kg short,
worth NZD 18.00. The count is at SKU level, so it does not establish which batch caused the shortage.

### Materials required for 3 October

Available stock is the lower of the calculated balance and the physical count. The check assumes
no further deliveries before production.

{table(d['production_impact'],['production_order','sku','base_uom','conservative_available_qty','required_qty_base','shortfall_qty','shortfall_value_nzd','risk'])}

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

{table(d['verification_checks'])}

Receipts cleared for reporting increased from **{before['reporting_ready']} to {after['reporting_ready']}**.
The remaining inventory difference is **NZD {rec['variance_nzd'].abs().sum():,.2f}**.
No inventory adjustment was entered to remove the mango shortage.

The process retains the source records. If a decision is reversed, a new audit event records
the reversal and the calculations are rerun from the original mappings.

## 6. Outstanding actions

{table(open_cases,['case_id','category','owner','due_date','decision','verification_result'])}

The dates above are assessed as of 2 October 2026. The [case register](../data/processed/case_register.csv)
contains the receipt IDs, SKUs, batches, quantities, valuation assumptions and latest check for each item.
Held receipts remain unvalued in the stock report until the product and delivery details are confirmed.

## Reproduce the case

Run `python src/run_case_study.py` to repeat the analysis using the supplied records and decision log.
See the [implementation guide](../docs/IMPLEMENTATION_GUIDE.md) for the calculation rules.

This case covers a receipt and inventory investigation. It does not estimate production downtime,
lost sales or realised savings.
'''
    (REPORTS_DIR/'investigation_summary.md').write_text(md,encoding='utf-8')
    return md


def write_html(payload,d):
    titles = ['Business problem','Records reviewed','Findings and impact',
              'Decisions','Checks after correction','Outstanding actions']
    cases = d['case_register']
    opened = cases[cases['status'].eq('open')]
    summary = payload['quality_after'][0]

    def grid(df,cols):
        view = df[cols].copy().fillna('Pending')
        labels = {
            'sku':'SKU','product_name':'Product','base_uom':'Base unit',
            'standard_cost_nzd_per_base':'Standard cost (NZD/base unit)',
            'case_id':'Case','category':'Issue type','affected_skus':'Affected SKUs',
            'batch_refs':'Batches','impact_qty':'Impact quantity','amount_nzd':'Amount (NZD)',
            'value_low_nzd':'Possible value, low (NZD)',
            'value_high_nzd':'Possible value, high (NZD)','status':'Status',
            'opening_qty':'Opening quantity','eligible_receipts_qty':'Eligible receipts',
            'net_movements_qty':'Production usage (outflows)','expected_closing_qty':'Expected closing',
            'counted_closing_qty':'Independent count','variance_qty':'Count variance',
            'variance_nzd':'Variance (NZD)','production_order':'Production order',
            'conservative_available_qty':'Available stock',
            'required_qty_base':'Required quantity','shortfall_qty':'Material shortfall',
            'shortfall_value_nzd':'Material shortfall value (NZD)','risk':'Material readiness',
            'cr_id':'Change request','action':'Decision','approver':'Approver',
            'decision_timestamp':'Decision time (UTC)','reason':'Reason','evidence_ref':'Evidence reference',
            'metric':'Metric','before':'Before correction','after':'After correction','delta':'Change',
            'check':'Verification check','actual':'Actual','expected':'Expected','result':'Result',
            'receipt_ids':'Receipts','owner':'Owner','due_date':'Due date',
            'deadline_status':'Deadline status','decision':'Handling decision',
            'verification_result':'Latest check'}
        display = {
            'pack_quantity_correction':'Pack quantity correction',
            'approved_unit_conversion':'Approved unit conversion',
            'duplicate_import_excluded':'Duplicate import excluded',
            'late_posting':'Late posting','ambiguous_mapping':'Ambiguous mapping',
            'expired_mapping':'Expired mapping','residual_inventory_variance':'Residual inventory variance',
            'production_material_risk':'Production material risk','material_shortfall':'Material shortfall',
            'covered':'Covered','open':'Open','closed':'Closed','scheduled':'Scheduled',
            'due_today':'Due today','overdue':'Overdue','approve':'Approve','reject':'Reject','revoke':'Revoke',
            'total_receipts':'Imported receipt rows','duplicates_flagged':'Duplicate imports excluded',
            'reporting_ready':'Receipts cleared for reporting','routed_to_review':'Receipts held for review',
            'unapproved_conversions':'Receipts awaiting a conversion factor','late_postings':'Eligible late postings',
            'eligible_receipt_value_nzd':'Eligible receipt value (NZD)'}
        for column in ['category','risk','status','deadline_status','action','metric']:
            if column in view:
                view[column] = view[column].map(lambda value:display.get(value,value))
        if 'check' in view:
            view['check'] = view['check'].map(lambda value:REPORT_VALUES.get(value,value))
        view = view.rename(columns=labels)
        return '<div class="scroll">'+view.to_html(index=False,border=0,float_format=lambda n:f'{n:,.2f}',escape=True)+'</div>'

    sections = [
        '<p class="lead">A blueberry pack-size change and a missing juice conversion left the September stock figures incomplete.</p>'
        '<p>This case checks the receipts for one warehouse and eight SKUs, corrects the quantities supported by supplier specifications, and compares them with physical stock counts. The review date is 2 October 2026, ahead of production on 3 October.</p>',
        '<p>The review uses 20 receipt rows, opening and closing counts for eight SKUs, eight production issue records and eight material requirements. One receipt row repeats an earlier import. The source document line identifies the duplicate, while the batch reference identifies the stock received.</p>'
        '<p>REP-001 supports the new 12 kg blueberry case. DENS-004 supplies the juice conversion of 0.95 kg/L. These specifications and all other records are fictional. Amounts use assumed standard costs in NZD, excluding GST.</p>'
        +grid(d['products'],['sku','product_name','base_uom','standard_cost_nzd_per_base']),
        '<p>The revised case size adds 74 kg to blueberry receipts. The approved juice conversion allows another 156.75 kg to enter the stock report. The table also records the duplicate import, held receipts and remaining shortages. Some amounts overlap, so they should not be added together as savings.</p>'
        +grid(d['case_register'],['case_id','category','affected_skus','batch_refs','impact_qty','base_uom','amount_nzd','value_low_nzd','value_high_nzd','status'])
        +'<h3>Inventory reconciliation</h3><p>Expected closing stock is opening stock plus cleared receipts, less production usage. Comparing this with the closing count leaves a 3 kg mango shortage to investigate. Held receipts are excluded from available stock.</p>'
        +grid(d['inventory_after'],['sku','base_uom','opening_qty','eligible_receipts_qty','net_movements_qty','expected_closing_qty','counted_closing_qty','variance_qty','variance_nzd'])
        +'<h3>Materials required for 3 October</h3><p>With no further deliveries assumed, blueberries are 16 kg short and juice is 13.25 kg short. Availability uses the lower of the calculated stock balance and the physical count. The amounts below value the missing material.</p>'
        +grid(d['production_impact'],['production_order','sku','base_uom','conservative_available_qty','required_qty_base','shortfall_qty','shortfall_value_nzd','risk']),
        '<p>The pack-size and density changes were approved on 1 October for September receipts. The legacy mapping remained expired, and the disputed product code was left unresolved. The decision log records the approver, date, reason and supporting document.</p>'
        +grid(d['decision_log'],['cr_id','action','approver','decision_timestamp','reason','evidence_ref']),
        '<p>The original and corrected mappings were run through the same calculations. Receipts cleared for reporting increased from 14 to 17. Blueberries and juice now agree with the counts. The mango shortage remains, with no adjustment entered to remove it.</p>'
        +grid(d['before_after'],['metric','before','after','delta'])
        +grid(d['verification_checks'],['check','actual','expected','result']),
        '<p>Five actions remain open: confirm two held receipts, investigate the mango shortage, and resolve two material shortfalls. Owners and deadlines are shown below, assessed as of 2 October. A receipt stays on hold until its outstanding questions are resolved.</p>'
        +grid(opened,['case_id','category','affected_skus','receipt_ids','owner','due_date','deadline_status','decision','verification_result'])
    ]
    body = ''.join(f'<section id="s{i+1}"><div class="step">0{i+1}</div><h2>{title}</h2>{content}</section>'
                   for i,(title,content) in enumerate(zip(titles,sections)))
    nav = ''.join(f'<a href="#s{i+1}">{i+1}. {html.escape(t)}</a>' for i,t in enumerate(titles))
    page = (
        '<!doctype html><html lang="en-NZ"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Food Supply Chain Investigation Case Study</title><style>'+CSS+'</style>'
        '<header><div class="eyebrow">SUPPLY CHAIN INVESTIGATION</div>'
        '<h1>September receipts: correcting pack sizes and units</h1>'
        '<p>Food supply chain master data and inventory investigation. Synthetic case study.</p>'
        '<div class="stats"><div><b>'+str(summary['total_receipts'])+'</b>Imported receipt rows</div>'
        '<div><b>'+str(summary['reporting_ready'])+'</b>Receipts cleared for reporting</div>'
        '<div><b>'+str(summary['routed_to_review'])+'</b>Receipts held for review</div>'
        '<div><b>'+str(len(opened))+'</b>Open actions</div></div></header>'
        '<nav aria-label="Case study sections">'+nav+'</nav><main>'+body+'</main>'
        '<footer>All data, costs, demand, evidence references and approvers are fictional. '
        'Figures reflect the review on 2 October 2026. Rerun the project after changing the source records.<br>'
        '<a href="investigation_summary.md">Detailed investigation report</a> · '
        '<a href="exception_report.xlsx">Excel evidence workbook</a></footer></html>')
    (REPORTS_DIR/'portfolio.html').write_text(page,encoding='utf-8')


CSS = '''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f4f5f7;color:#17243b;font:16px/1.75 "Segoe UI","Arial",sans-serif}header,main,footer{max-width:1240px;margin:auto;padding:40px 36px}header{padding-top:64px}.eyebrow{font-size:12px;letter-spacing:3px;color:#526786}h1{font-size:42px;line-height:1.3;margin:14px 0}header p{color:#53647c}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:32px}.stats div{background:#fff;border-top:3px solid #3051a0;padding:18px 24px;font-size:14px}.stats b{display:block;font-size:32px;font-weight:600}nav{position:sticky;top:0;background:#17243b;display:flex;justify-content:center;gap:24px;padding:14px;z-index:2;flex-wrap:wrap}nav a{color:#fff;text-decoration:none;font-size:14px}section{background:#fff;border:1px solid #e0e5ed;border-radius:8px;padding:28px;margin-bottom:24px;scroll-margin-top:90px}.step{font-size:13px;letter-spacing:2px;color:#536995}h2{font-size:25px;margin:4px 0 16px}h3{margin-top:28px;font-size:19px}.lead{font-size:21px;max-width:900px}.scroll{overflow:auto;margin:20px 0;max-height:520px}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th{background:#edf1f7;color:#233b61;font-weight:600;position:sticky;top:0}th,td{padding:12px 14px;border-bottom:1px solid #e3e8ef;min-width:110px;max-width:360px;overflow-wrap:anywhere;vertical-align:top}tr:nth-child(even){background:#fafbfe}footer{font-size:13px;color:#61708a;padding-top:0}a{color:#254b9a}@media(max-width:700px){header,main,footer{padding:24px 16px}h1{font-size:30px}.stats{grid-template-columns:repeat(2,1fr)}nav{position:static;gap:12px}section{padding:18px}}@media print{nav{display:none}body{background:white}section{break-inside:avoid}.scroll{max-height:none}th{position:static}}'''


def run_reports():
    REPORTS_DIR.mkdir(parents=True,exist_ok=True)
    payload,datasets = build_bundle()
    (PROCESSED_DIR/'report_bundle.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    write_narrative(payload,datasets)
    write_html(payload,datasets)
    print('English case study, narrative and workbook input bundle generated.')
    return payload


if __name__=='__main__':
    run_reports()
