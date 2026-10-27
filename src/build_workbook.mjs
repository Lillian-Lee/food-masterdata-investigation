/** Excel evidence report. Authoring uses only the bundled artifact runtime. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const moduleRoot = process.env.ARTIFACT_MODULE_ROOT || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const requireRuntime = createRequire(path.join(moduleRoot, 'package.json'));
const { Workbook, SpreadsheetFile, FileBlob } = await import(pathToFileURL(requireRuntime.resolve('@oai/artifact-tool')).href);
const out = path.join(root, 'outputs/supply-chain-evidence');
await fs.mkdir(out, { recursive: true });
if (process.argv.includes('--inspect-existing')) {
  const previous = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(root, 'reports/exception_report.xlsx')));
  console.log((await previous.inspect({kind:'workbook,sheet,table',maxChars:2000,tableMaxRows:2,tableMaxCols:4})).ndjson);
  const preview = await previous.render({sheetName:'Quality Summary',range:'A1:F3',scale:1,format:'png'});
  await fs.writeFile(path.join(out,'before.png'), new Uint8Array(await preview.arrayBuffer()));
  process.exit(0);
}
const data = JSON.parse(await fs.readFile(path.join(root,'data/processed/report_bundle.json'),'utf8'));
const wb = Workbook.create();
const names = ['01 Business','02 Evidence','03 Impact','04 Decisions','05 Verification','06 Actions',
  '07 Inventory','08 Receipt Calc','09 Sources','10 Production','11 Mapping'];
const sheets = Object.fromEntries(names.map(n=>[n,wb.worksheets.add(n)]));
const col = n => { let s=''; for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s; return s; };
const put = (sh,cell,v) => sheets[sh].getRange(cell).values=[[v]];
const fx = (sh,cell,v) => sheets[sh].getRange(cell).formulas=[[v]];
const ref = (sh,cell) => `'${sh}'!${cell}`;
const money = '"NZ$"#,##0.00;[Red]("NZ$"#,##0.00);"NZ$"0.00';
const qty = '#,##0.00;[Red](#,##0.00);0.00';
const serial = value => Math.round((Date.parse(value.slice(0,10)+'T00:00:00Z')-Date.UTC(1899,11,30))/86400000);
function base(name,title,note,width=12) {
  const s=sheets[name];
  s.showGridLines=false;
  s.getRange(`A1:${col(width-1)}50`).format.font={name:'Arial',size:10,color:'#1D2C43'};
  s.getRange(`A1:${col(width-1)}50`).format.columnWidth=18;
  s.getRange(`A1:${col(width-1)}50`).format.rowHeight=24;
  s.getRange('A2').values=[[title]];
  s.getRange('A2').format.font={name:'Arial',size:16,bold:true,color:'#17243B'};
  s.getRange('A3').values=[[note]];
  s.getRange('A3').format.font={name:'Arial',size:10,italic:true,color:'#526786'};
  s.tabColor=name.startsWith('0')&&Number(name.slice(0,2))<7?'#243E72':'#D9E2EF';
  return s;
}
function table(name,headers,rows,row=5,tableName='T'+name.replace(/\W/g,'')) {
  const s=sheets[name], last=col(headers.length-1), end=row+rows.length;
  s.getRange(`A${row}:${last}${end}`).values=[headers,...rows];
  const t=s.tables.add(`A${row}:${last}${end}`,true,tableName);
  t.style='TableStyleMedium2';
  s.getRange(`A${row}:${last}${row}`).format={fill:'#243E72',font:{bold:true,color:'#FFFFFF',name:'Arial',size:10},wrapText:true,rowHeight:38,horizontalAlignment:'center',verticalAlignment:'center'};
  s.getRange(`A${row+1}:${last}${end}`).format.verticalAlignment='center';
  s.freezePanes.freezeRows(row);
  return end;
}
function textColumns(name,columns,widths,start=6,end=30) {
  columns.forEach((c,i)=>{
    sheets[name].getRange(`${c}5:${c}${end}`).format.columnWidth=widths[i];
    sheets[name].getRange(`${c}${start}:${c}${end}`).format.wrapText=true;
  });
}

// Sources own cost, counts, movements and demand. All are explicitly synthetic.
base('09 Sources','Synthetic source assumptions','Costs exclude GST. Counts exclude held receipts. No additional inbound before 3 October.',14);
const sourceRows=data.products.map(p=>{
  const inv=data.inventory_after.find(x=>x.sku===p.sku), req=data.requirements.find(x=>x.sku===p.sku);
  return [p.sku,p.product_name,p.base_uom,p.standard_cost_nzd_per_base,inv.opening_qty,inv.counted_closing_qty,
    inv.net_movements_qty,req.required_qty_base,serial(req.required_date),req.production_order,inv.evidence_refs,req.evidence_ref];
});
table('09 Sources',['SKU','Product','Base UoM','Cost NZD/base','Opening 31 Aug','Count 30 Sep','Signed issues','Demand qty','Demand date','Order','Count / issue evidence','Demand evidence'],sourceRows);
textColumns('09 Sources',['A','B','K','L'],[25,28,55,34],6,13);
sheets['09 Sources'].getRange('D6:D13').setNumberFormat(money);
sheets['09 Sources'].getRange('E6:H13').setNumberFormat(qty);
sheets['09 Sources'].getRange('I6:I13').setNumberFormat('dd mmm yyyy');
put('09 Sources','A17','Source: synthetic products, opening/closing counts, production issues and dated material requirements.');
put('09 Sources','A19','The 0.95 kg/L factor is a synthetic approved specification, not a universal density.');
put('09 Sources','A21','Input edits recalculate arithmetic. Rerun Python for changes to mapping/date/approval selection or action evidence.');
put('09 Sources','A23','Review date'); put('09 Sources','B23',serial(data.meta.as_of)); sheets['09 Sources'].getRange('B23').setNumberFormat('dd mmm yyyy');

base('02 Evidence','2. Data evidence','20 imported source rows. Duplicate identity is supplier plus source document line; batch is traceability.',11);
const receiptHeaders=['Receipt','Source line','Receipt date','Posted date','Supplier','Supplier code','Batch','Qty received','Receipt UoM','Source note'];
table('02 Evidence',receiptHeaders,data.source_receipts.map(r=>[r.receipt_id,r.source_line_id,serial(r.receipt_date),serial(r.posted_date),r.supplier,r.supplier_item_code,r.batch_ref,r.qty_received,r.receipt_uom,r.source_note]));
textColumns('02 Evidence',['A','B','E','F','J'],[18,19,24,20,42],6,25);
sheets['02 Evidence'].getRange('C6:D25').setNumberFormat('dd mmm yyyy');
sheets['02 Evidence'].getRange('H6:H25').setNumberFormat(qty);
put('02 Evidence','A28','Source: synthetic goods_received.csv. Raw receipt quantities and UoMs are retained.');
put('02 Evidence','A30','September receipt-date restatement, including postings known by 2 October 2026.');

base('11 Mapping','Mapping versions used in replay','Approved versions preserve history. Mapping selection is performed by the Python pipeline.',12);
// Approved mapping versions are inspection evidence. Receipt factors are selected by Python.
table('11 Mapping',['Mapping ID','Supplier','Supplier code','SKU','Effective from','Effective to','Supplier UoM','Base qty/case','kg or L per supplier unit','Approval'],
 data.approved_mapping.map(m=>[m.mapping_id,m.supplier,m.supplier_item_code,m.sku,serial(m.effective_from),serial(m.effective_to),m.supplier_uom,m.base_qty_per_case,m.conversion_factor,m.approval_cr_id]));
textColumns('11 Mapping',['A','B','C','D'],[20,24,20,26],6,18);
sheets['11 Mapping'].getRange('E6:F18').setNumberFormat('dd mmm yyyy');
sheets['11 Mapping'].getRange('H6:I18').setNumberFormat(qty);
put('11 Mapping','A22','Source: baseline supplier mappings plus decisions supported by REP-001, TERM-002, DIS-003 and DENS-004.');

base('08 Receipt Calc','Receipt quantity and value calculation','Blank baseline conversion means unavailable, not zero. Baseline and approved quantities use the same source row.',22);
const compareById=new Map(data.receipt_changes.map(x=>[x.receipt_id,x]));
const receiptRows=data.receipts.map(r=>{
  const c=compareById.get(r.receipt_id);
  const beforeFactor=c.qty_base_before===null?null:c.qty_base_before/r.qty_received;
  const afterFactor=c.qty_base_after===null?null:c.qty_base_after/r.qty_received;
  return [r.receipt_id,c.disposition_before,c.disposition_after,r.resolved_sku||null,r.batch_ref,r.qty_received,r.receipt_uom,r.base_uom||null,
    beforeFactor,afterFactor,null,null,null,null,null,null,null,r.late_posting?1:0,r.mapping_id||null,c.mapping_id_before||null];
});
table('08 Receipt Calc',['Receipt','Before disposition','After disposition','SKU','Batch','Source qty','Source UoM','Base UoM','Before factor','Approved factor','Before base qty','After base qty','Cost NZD/base','Before value','After value','Comparable delta','New eligible value','Late flag','Approved mapping','Baseline mapping'],receiptRows);
const sourceRowBySku=new Map(data.products.map((p,i)=>[p.sku,i+6]));
data.receipts.forEach((r,i)=>{
  const n=i+6, sourceN=data.source_receipts.findIndex(s=>s.receipt_id===r.receipt_id)+6;
  fx('08 Receipt Calc',`F${n}`,`=${ref('02 Evidence',`H${sourceN}`)}`);
  fx('08 Receipt Calc',`K${n}`,`=IF(I${n}="","",F${n}*I${n})`);
  fx('08 Receipt Calc',`L${n}`,`=IF(J${n}="","",F${n}*J${n})`);
  if(r.resolved_sku)fx('08 Receipt Calc',`M${n}`,`=${ref('09 Sources',`D${sourceRowBySku.get(r.resolved_sku)}`)}`);
  fx('08 Receipt Calc',`N${n}`,`=IF(K${n}="","",K${n}*M${n})`);
  fx('08 Receipt Calc',`O${n}`,`=IF(L${n}="","",L${n}*M${n})`);
  fx('08 Receipt Calc',`P${n}`,`=IF(AND(B${n}="reporting_ready",C${n}="reporting_ready"),O${n}-N${n},"")`);
  fx('08 Receipt Calc',`Q${n}`,`=IF(AND(B${n}<>"reporting_ready",C${n}="reporting_ready"),O${n},"")`);
});
textColumns('08 Receipt Calc',['A','B','C','D','S','T'],[18,24,24,26,20,20],6,25);
sheets['08 Receipt Calc'].getRange('F6:F25').setNumberFormat(qty);
sheets['08 Receipt Calc'].getRange('I6:L25').setNumberFormat(qty);
sheets['08 Receipt Calc'].getRange('M6:Q25').setNumberFormat(money);

base('07 Inventory','Eligible-stock inventory reconciliation','Count minus expected = variance. Do not sum kg with litres. Held candidate receipts remain excluded.',16);
table('07 Inventory',['SKU','UoM','Opening','Before receipts','After receipts','Signed issues','Before expected','After expected','Counted close','Before variance','After variance','Cost NZD/base','Before variance NZD','After variance NZD'],data.products.map(p=>[p.sku,p.base_uom,...Array(12).fill(null)]));
data.products.forEach((p,i)=>{
  const n=i+6;
  for(const [target,source] of [['C','E'],['F','G'],['I','F'],['L','D']])fx('07 Inventory',`${target}${n}`,`=${ref('09 Sources',`${source}${n}`)}`);
  fx('07 Inventory',`D${n}`,`=SUMIFS('08 Receipt Calc'!$K$6:$K$25,'08 Receipt Calc'!$D$6:$D$25,A${n},'08 Receipt Calc'!$B$6:$B$25,"reporting_ready")`);
  fx('07 Inventory',`E${n}`,`=SUMIFS('08 Receipt Calc'!$L$6:$L$25,'08 Receipt Calc'!$D$6:$D$25,A${n},'08 Receipt Calc'!$C$6:$C$25,"reporting_ready")`);
  fx('07 Inventory',`G${n}`,`=C${n}+D${n}+F${n}`);fx('07 Inventory',`H${n}`,`=C${n}+E${n}+F${n}`);
  fx('07 Inventory',`J${n}`,`=I${n}-G${n}`);fx('07 Inventory',`K${n}`,`=I${n}-H${n}`);
  fx('07 Inventory',`M${n}`,`=J${n}*L${n}`);fx('07 Inventory',`N${n}`,`=K${n}*L${n}`);
});
textColumns('07 Inventory',['A'],[26],6,13);
sheets['07 Inventory'].getRange('C6:K13').setNumberFormat(qty);
sheets['07 Inventory'].getRange('L6:N13').setNumberFormat(money);
sheets['07 Inventory'].getRange('K6:K13').conditionalFormats.add('cellIs',{operator:'notEqual',formula:0,format:{fill:'#FCE7E7',font:{color:'#A52828',bold:true}}});

base('10 Production','3 October material availability','Available = lower of eligible ledger stock and counted available stock. No additional inbound assumed.',12);
table('10 Production',['Order','SKU','UoM','Required date','Required qty','Available qty','Shortfall qty','Cost NZD/base','Material gap NZD','Risk'],data.products.map((p,i)=>[data.requirements[i].production_order,p.sku,p.base_uom,null,null,null,null,null,null,null]));
data.products.forEach((p,i)=>{
  const n=i+6;
  fx('10 Production',`D${n}`,`=${ref('09 Sources',`I${n}`)}`);fx('10 Production',`E${n}`,`=${ref('09 Sources',`H${n}`)}`);
  fx('10 Production',`F${n}`,`=MAX(MIN('07 Inventory'!H${n},'07 Inventory'!I${n}),0)`);
  fx('10 Production',`G${n}`,`=MAX(E${n}-F${n},0)`);fx('10 Production',`H${n}`,`=${ref('09 Sources',`D${n}`)}`);
  fx('10 Production',`I${n}`,`=G${n}*H${n}`);fx('10 Production',`J${n}`,`=IF(G${n}>0,"material_shortfall","covered")`);
});
textColumns('10 Production',['A','B','J'],[18,26,25],6,13);
sheets['10 Production'].getRange('D6:D13').setNumberFormat('dd mmm yyyy');
sheets['10 Production'].getRange('E6:G13').setNumberFormat(qty);
sheets['10 Production'].getRange('H6:I13').setNumberFormat(money);
sheets['10 Production'].getRange('G6:G13').conditionalFormats.add('cellIs',{operator:'greaterThan',formula:0,format:{fill:'#FFF1D6',font:{color:'#8A4D00',bold:true}}});

base('03 Impact','3. Discrepancy and impact','Different impact categories overlap. Conditional held-stock values are not posted amounts or confirmed losses.',12);
table('03 Impact',['Case','Category','Affected SKU(s)','Batch(es)','Impact qty','UoM','Amount NZD','Candidate low NZD','Candidate high NZD','Status'],data.case_register.map(c=>[c.case_id,c.category,c.affected_skus,c.batch_refs,c.impact_qty,c.base_uom,c.amount_nzd,c.value_low_nzd,c.value_high_nzd,c.status]));
data.case_register.forEach((c,i)=>{
  const n=i+6;
  if(c.category==='pack_quantity_correction'){
    fx('03 Impact',`G${n}`,`=SUM('08 Receipt Calc'!P6:P25)`);
    const ids=c.receipt_ids.split('; ').map(id=>data.receipts.findIndex(r=>r.receipt_id===id)+6);
    fx('03 Impact',`E${n}`,'='+ids.map(j=>`('08 Receipt Calc'!L${j}-'08 Receipt Calc'!K${j})`).join('+'));
  } else if(c.category==='approved_unit_conversion') {
    fx('03 Impact',`G${n}`,`=SUM('08 Receipt Calc'!Q6:Q25)`);
    const ids=c.receipt_ids.split('; ').map(id=>data.receipts.findIndex(r=>r.receipt_id===id)+6);
    fx('03 Impact',`E${n}`,'='+ids.map(j=>`'08 Receipt Calc'!L${j}`).join('+'));
  } else if(['duplicate_import_excluded','late_posting'].includes(c.category)) {
    const j=data.receipts.findIndex(r=>r.receipt_id===c.receipt_ids)+6;
    fx('03 Impact',`E${n}`,`='08 Receipt Calc'!L${j}`);fx('03 Impact',`G${n}`,`='08 Receipt Calc'!O${j}`);
  } else if(c.category==='residual_inventory_variance') {
    const j=sourceRowBySku.get(c.affected_skus);
    fx('03 Impact',`E${n}`,`='07 Inventory'!K${j}`);fx('03 Impact',`G${n}`,`='07 Inventory'!N${j}`);
  } else if(c.category==='production_material_risk') {
    const j=sourceRowBySku.get(c.affected_skus);
    fx('03 Impact',`E${n}`,`='10 Production'!G${j}`);fx('03 Impact',`G${n}`,`='10 Production'!I${j}`);
  }
});
textColumns('03 Impact',['A','B','C','D'],[18,30,40,32],6,14);
sheets['03 Impact'].getRange('E6:E14').setNumberFormat(qty);
sheets['03 Impact'].getRange('G6:I14').setNumberFormat(money);
put('03 Impact','A18','Blank confirmed amount = pending SKU confirmation. Candidate ranges are conditional, never zero-valued certainty.');
put('03 Impact','A20','Production amounts value material shortfalls only. No downtime, revenue loss or realised savings is calculated.');

base('04 Decisions','4. Handling decisions','Simulated approvals preserve baseline history and retain rejected requests.',10);
table('04 Decisions',['Change request','Decision','Approver','Timestamp (UTC)','Reason','Evidence'],data.decision_log.map(d=>[d.cr_id,d.action,d.approver,d.decision_timestamp,d.reason,d.evidence_ref]));
textColumns('04 Decisions',['A','B','C','D','E','F'],[20,16,40,33,62,22],6,9);
sheets['04 Decisions'].getRange('A6:F9').format.rowHeight=48;
sheets['04 Decisions'].getRange('D6:D9').setNumberFormat('dd mmm yyyy hh:mm');
put('04 Decisions','A13','A retired mapping does not authorise a late receipt. Rejected identity changes remain on hold.');
put('04 Decisions','A15','Reversal appends a revoke event and replays baseline. The audit ledger is never deleted for rollback.');

base('06 Actions','6. Unresolved items','Snapshot as of 2 October 2026. Pipeline replay refreshes this evidence register after source changes.',12);
const open=data.case_register.filter(c=>c.status==='open');
table('06 Actions',['Case','Issue','SKU(s)','Receipt / batch','Owner','Due date','Deadline status','Next action','Verification result'],open.map(c=>[c.case_id,c.category,c.affected_skus,[c.receipt_ids,c.batch_refs].filter(Boolean).join(' / '),c.owner,serial(c.due_date),null,c.decision,c.verification_result]));
open.forEach((c,i)=>{const n=i+6;fx('06 Actions',`G${n}`,`=IF(F${n}<'09 Sources'!$B$23,"overdue",IF(F${n}='09 Sources'!$B$23,"due_today","scheduled"))`);});
textColumns('06 Actions',['A','B','C','D','E','H','I'],[17,29,38,32,42,58,64],6,10);
sheets['06 Actions'].getRange('F6:F10').setNumberFormat('dd mmm yyyy');
sheets['06 Actions'].getRange('A6:I10').format.rowHeight=65;
sheets['06 Actions'].getRange('G6:G10').conditionalFormats.add('containsText',{text:'due_today',format:{fill:'#FFF1D6',font:{color:'#8A4D00'}}});
sheets['06 Actions'].getRange('G6:G10').conditionalFormats.add('containsText',{text:'overdue',format:{fill:'#FCE7E7',font:{color:'#A52828'}}});

base('05 Verification','5. Recalculation and verification','Before and after are independent runs. Amount changes are stock valuation effects, not savings.',12);
table('05 Verification',['Metric','Baseline','Approved','Change'],[
 ['Imported rows',null,null,null],['Reporting-ready rows',null,null,null],['Review rows',null,null,null],
 ['Duplicate excluded rows',null,null,null],['Eligible receipt value NZD',null,null,null],['Absolute inventory variance NZD',null,null,null]]);
fx('05 Verification','B6',`=COUNTA('02 Evidence'!A6:A25)`);fx('05 Verification','C6',`=COUNTA('08 Receipt Calc'!A6:A25)`);
for(const [n,status] of [[7,'reporting_ready'],[8,'review'],[9,'duplicate_excluded']]){
 fx('05 Verification',`B${n}`,`=COUNTIF('08 Receipt Calc'!B6:B25,"${status}")`);fx('05 Verification',`C${n}`,`=COUNTIF('08 Receipt Calc'!C6:C25,"${status}")`);
}
fx('05 Verification','B10',`=SUMIF('08 Receipt Calc'!B6:B25,"reporting_ready",'08 Receipt Calc'!N6:N25)`);
fx('05 Verification','C10',`=SUMIF('08 Receipt Calc'!C6:C25,"reporting_ready",'08 Receipt Calc'!O6:O25)`);
fx('05 Verification','B11',`=SUMIF('07 Inventory'!M6:M13,">0",'07 Inventory'!M6:M13)-SUMIF('07 Inventory'!M6:M13,"<0",'07 Inventory'!M6:M13)`);fx('05 Verification','C11',`=SUMIF('07 Inventory'!N6:N13,">0",'07 Inventory'!N6:N13)-SUMIF('07 Inventory'!N6:N13,"<0",'07 Inventory'!N6:N13)`);
for(let n=6;n<=11;n++)fx('05 Verification',`D${n}`,`=C${n}-B${n}`);
sheets['05 Verification'].getRange('B10:D11').setNumberFormat(money);
textColumns('05 Verification',['A'],[43],6,11);
table('05 Verification',['Independent control','Difference (must be 0)'],[['Source partitions',null],['Workbook vs Python eligible row count',null],['Workbook vs Python eligible value',null]],15,'ControlChecks');
fx('05 Verification','B16','=C6-SUM(C7:C9)');
fx('05 Verification','B17',`=C7-${data.quality_after[0].reporting_ready}`);
fx('05 Verification','B18',`=ROUND(C10-${data.quality_after[0].eligible_receipt_value_nzd},2)`);
sheets['05 Verification'].getRange('B16:B18').conditionalFormats.add('cellIs',{operator:'notEqual',formula:0,format:{fill:'#FCE7E7',font:{color:'#A52828',bold:true}}});
sheets['05 Verification'].freezePanes.unfreeze();
const chart=sheets['05 Verification'].charts.add('bar',sheets['05 Verification'].getRange('A5:C9'));
chart.title='Receipt dispositions before and after';chart.titleTextStyle.typeface='Arial';chart.titleTextStyle.fontSize=13;
chart.legend={position:'bottom',textStyle:{typeface:'Arial',fontSize:11}};
chart.xAxis={axisType:'textAxis',textStyle:{typeface:'Arial',fontSize:11}};
chart.yAxis={minimumScale:0,numberFormatCode:'0',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:11}};
chart.series.items[0].fill='#93A3BE';chart.series.items[1].fill='#3051A0';chart.setPosition('F5','N20');

base('01 Business','Food supply chain investigation','Synthetic case study. September 2026 receipts. Review as of 2 October 2026. NZD, excluding GST.',12);
put('01 Business','A5','1. Business problem');
put('01 Business','A6','Pack-size and unit changes can distort available stock and production material decisions.');
put('01 Business','A8','2. Data evidence');
put('01 Business','A9','20 imported receipts, independent stock counts, production issues, costs and dated material requirements.');
put('01 Business','A11','3. Discrepancy and impact');
put('01 Business','A12','Packaging correction NZD');fx('01 Business','D12',`=SUMIF('03 Impact'!B6:B14,"pack_quantity_correction",'03 Impact'!G6:G14)`);
put('01 Business','A13','New eligible stock value NZD');fx('01 Business','D13',`=SUMIF('03 Impact'!B6:B14,"approved_unit_conversion",'03 Impact'!G6:G14)`);
put('01 Business','A15','4. Handling decision');
put('01 Business','A16','Approve the evidenced pack and density changes. Hold disputed and expired-code receipts.');
put('01 Business','A18','5. Recalculation');
put('01 Business','A19','Reporting-ready rows');fx('01 Business','D19',`=COUNTIF('08 Receipt Calc'!C6:C25,"reporting_ready")`);
put('01 Business','A20','Residual inventory variance NZD');fx('01 Business','D20',`=SUMIF('07 Inventory'!N6:N13,">0",'07 Inventory'!N6:N13)-SUMIF('07 Inventory'!N6:N13,"<0",'07 Inventory'!N6:N13)`);
put('01 Business','A22','6. Unresolved items');
put('01 Business','A23','Held receipts');fx('01 Business','D23',`=COUNTIF('08 Receipt Calc'!C6:C25,"review")`);
put('01 Business','A24','Production orders with material gaps');fx('01 Business','D24',`=COUNTIF('10 Production'!J6:J13,"material_shortfall")`);
put('01 Business','A26','No balancing adjustment. Held stock remains excluded. Impact categories overlap; do not add as savings.');
put('01 Business','A28','This workbook recalculates arithmetic. Rerun the pipeline to refresh mapping selection and investigation actions.');
sheets['01 Business'].getRange('A5:A24').format.columnWidth=48;
sheets['01 Business'].getRange('D5:D24').format.columnWidth=24;
sheets['01 Business'].getRange('D12:D13').setNumberFormat(money);sheets['01 Business'].getRange('D20').setNumberFormat(money);
for(const n of [5,8,11,15,18,22])sheets['01 Business'].getRange(`A${n}`).format.font={name:'Arial',size:12,bold:true,color:'#243E72'};

// Perturb an actual quantity: shared receipt, inventory, valuation and production formulas must react.
const original=sheets['02 Evidence'].getRange('H6').values[0][0];
const originalQty=sheets['07 Inventory'].getRange('E6').values[0][0];
const originalGap=sheets['10 Production'].getRange('G6').values[0][0];
put('02 Evidence','H6',original+1);
assert.ok(Math.abs(sheets['07 Inventory'].getRange('E6').values[0][0]-originalQty-12)<1e-7);
assert.ok(Math.abs(sheets['10 Production'].getRange('G6').values[0][0]-originalGap)<1e-7); // count caps availability
put('02 Evidence','H6',original);
wb.recalculate();
assert.equal(sheets['01 Business'].getRange('D19').values[0][0],data.quality_after[0].reporting_ready);
assert.ok(Math.abs(sheets['01 Business'].getRange('D12').values[0][0]-data.case_register.filter(c=>c.category==='pack_quantity_correction').reduce((a,c)=>a+c.amount_nzd,0))<1e-7);
assert.ok(Math.abs(sheets['05 Verification'].getRange('C10').values[0][0]-data.quality_after[0].eligible_receipt_value_nzd)<1e-7);
assert.ok(Math.abs(sheets['01 Business'].getRange('D20').values[0][0]-data.inventory_after.reduce((a,c)=>a+Math.abs(c.variance_nzd),0))<1e-7);
for(let n=16;n<=18;n++)assert.equal(sheets['05 Verification'].getRange(`B${n}`).values[0][0],0);
console.log((await wb.inspect({kind:'table',range:"'05 Verification'!A5:D11",include:'values,formulas',tableMaxRows:8,tableMaxCols:4,maxChars:3500})).ndjson);
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},summary:'Final formula scan',maxChars:3000});
console.log(errors.ndjson);
assert.ok(!errors.ndjson.split('\n').some(line=>line.trim() && JSON.parse(line).kind==='match'),'Formula error detected');
// Optional visual QA only. On this Windows runtime, renderer native cleanup can fail
// after PNGs are saved. Normal workbook replay does not load the renderer.
// Bounded opening views for every sheet; wide evidence tables remain horizontally scrollable.
for(const name of process.argv.includes('--previews') ? names : []){
  const ranges={'01 Business':'A1:F29','02 Evidence':'A1:J10','03 Impact':'A1:J15','04 Decisions':'A1:F16','05 Verification':'A1:N20','06 Actions':'A1:I11',
    '07 Inventory':'A1:N14','08 Receipt Calc':'A1:Q10','09 Sources':'A1:L14','10 Production':'A1:J14','11 Mapping':'A1:J10'};
  const image=await wb.render({sheetName:name,range:ranges[name],scale:1,format:'png'});
  await fs.writeFile(path.join(out,name.slice(0,2)+'-preview.png'),new Uint8Array(await image.arrayBuffer()));
}
const xlsx=await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(path.join(out,'exception_report.xlsx'));
await fs.copyFile(path.join(out,'exception_report.xlsx'),path.join(root,'reports/exception_report.xlsx'));
console.log('Workbook exported; quantity perturbation and cross-source controls passed.');
process.exit(0);
