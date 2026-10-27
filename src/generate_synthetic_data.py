"""Deterministic synthetic sources. Reset fixtures only via explicit generation."""
from pathlib import Path
import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
PRODUCTS = [
    ("SKU-FZN-BER-001", "Frozen Blueberries", "Frozen Fruit", "kg", 10, 8.5),
    ("SKU-FZN-MAN-002", "Frozen Mango Chunks", "Frozen Fruit", "kg", 5, 6),
    ("SKU-APL-JCE-003", "Apple Juice Concentrate", "Beverage", "kg", 19, 3.2),
    ("SKU-PLS-TOM-004", "Tomato Passata", "Canned Goods", "kg", 3, 2.8),
    ("SKU-OIL-SUN-005", "Sunflower Oil", "Oils", "L", 20, 4.5),
    ("SKU-FLU-WHT-006", "Wheat Flour", "Bakery", "kg", 25, 1.6),
    ("SKU-SGR-WHT-007", "White Sugar", "Dry Staples", "kg", 1, 1.4),
    ("SKU-CHS-SAU-008", "Cheese Sauce Base", "Dairy Prep", "kg", 4, 5),
]
MAPPINGS = [
    ("MAP-001", "SUP-NORTHFROST", "NF-BER-10", 0, "2026-01-01", "2099-12-31", "kg", 10, 1),
    ("MAP-003", "SUP-NORTHFROST", "NF-MAN-5", 1, "2026-01-01", "2099-12-31", "kg", 5, 1),
    ("MAP-004", "SUNCOAST-BEV", "SC-JCE-20L", 2, "2026-01-01", "2099-12-31", "L", None, None),
    ("MAP-005", "SUNCOAST-BEV", "SC-PAS-3KG", 3, "2026-01-01", "2099-12-31", "kg", 3, 1),
    ("MAP-006", "SUP-NORTHFROST", "NF-OIL-20L", 4, "2026-01-01", "2099-12-31", "L", 20, 1),
    ("MAP-007", "MILLERS-DIRECT", "MD-FLU-25", 5, "2026-01-01", "2099-12-31", "kg", 25, 1.0),
    ("MAP-008", "MILLERS-DIRECT", "MD-SGR-1K", 6, "2026-01-01", "2099-12-31", "kg", 1, 1),
    ("MAP-009", "DAIRYLAND", "DL-SAU-4K", 7, "2026-01-01", "2099-12-31", "kg", 4, 1),
    ("MAP-010", "SUP-NORTHFROST", "NF-AMB-01", 0, "2026-06-01", "2099-12-31", "kg", 10, 1),
    ("MAP-011", "SUP-NORTHFROST", "NF-AMB-01", 5, "2026-06-01", "2099-12-31", "kg", 25, 1),
    ("MAP-012", "LEGACY-FROST", "LF-BER-OLD", 0, "2025-01-01", "2026-07-31", "kg", 10, 1),
]
RECEIPTS = [
    (3,"NF-BER-10",12,"CASE","B-0901"), (5,"SC-JCE-20L",50,"L","B-0903"),
    (7,"MD-FLU-25",80,"kg","B-0905"), (1,"NF-BER-10",12,"CASE","B-0907"),
    (11,"SC-PAS-3KG",100,"kg","B-0909"), (13,"NF-OIL-20L",30,"L","B-0911"),
    (15,"MD-SGR-1K",400,"kg","B-0913"), (17,"DL-SAU-4K",45,"kg","B-0915"),
    (19,"NF-MAN-5",60,"kg","B-0917"), (21,"NF-BER-10",13,"CASE","B-0919"),
    (23,"SC-JCE-20L",55,"L","B-0921"), (25,"NF-AMB-01",25,"kg","B-0923"),
    (27,"MD-FLU-25",90,"kg","B-0925"), (29,"LF-BER-OLD",40,"kg","B-0927"),
    (16,"SC-JCE-20L",60,"L","B-0914"), (1,"NF-BER-10",12,"CASE","B-0907"),
    (6,"NF-MAN-5",55,"kg","B-0904"), (10,"MD-SGR-1K",380,"kg","B-0908"),
    (12,"DL-SAU-4K",42,"kg","B-0910"), (22,"SC-PAS-3KG",95,"kg","B-0920"),
]


def write(name, rows):
    pd.DataFrame(rows).to_csv(RAW_DIR / name, index=False)


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write("products.csv", [dict(sku=s, product_name=n, category=c, base_uom=u,
        base_qty_per_case=p, standard_cost_nzd_per_base=cost,
        data_owner="master-data-team@example.com") for s,n,c,u,p,cost in PRODUCTS])
    write("supplier_mapping.csv", [dict(mapping_id=mid, supplier=sup,
        supplier_item_code=code, sku=PRODUCTS[ix][0], effective_from=start,
        effective_to=end, supplier_uom=uom, base_qty_per_case=pack,
        conversion_factor=factor, approval_cr_id="baseline")
        for mid,sup,code,ix,start,end,uom,pack,factor in MAPPINGS])
    by_code = {m[2]: m for m in MAPPINGS}
    rows = []
    for i,(day,code,qty,uom,batch) in enumerate(RECEIPTS, 1):
        rows.append(dict(receipt_id=f"RCV-{i:04d}", source_line_id=f"GRN-{4 if i==16 else i:04d}-1",
            receipt_date=f"2026-09-{day:02d}",
            posted_date="2026-10-02" if i==15 else f"2026-09-{day:02d}",
            supplier=by_code[code][1], supplier_item_code=code, qty_received=qty,
            receipt_uom=uom, batch_ref=batch,
            source_note="Duplicate import of GRN-0004-1" if i==16 else "Synthetic receiving document"))
    write("goods_received.csv", rows)
    changes = [
        ("CR-001","NF-BER-10",0,"repack","2026-09-01",12,1,"REP-001"),
        ("CR-002","LF-BER-OLD",0,"retire_mapping","2026-08-01",10,1,"TERM-002"),
        ("CR-003","NF-AMB-01",0,"resolve_ambiguity","2026-09-01",10,1,"DIS-003"),
        ("CR-004","SC-JCE-20L",2,"unit_change","2026-09-01",19,.95,"DENS-004"),
    ]
    write("change_requests.csv", [dict(cr_id=cr, supplier=by_code[code][1],
        supplier_item_code=code, proposed_sku=PRODUCTS[ix][0], cr_type=kind,
        effective_from=eff, proposed_base_qty_per_case=pack,
        proposed_conversion_factor=factor, evidence_ref=ev,
        requested_by="procurement@example.com", requested_date="2026-08-20")
        for cr,code,ix,kind,eff,pack,factor,ev in changes])
    opening = [500,200,100,300,100,200,500,100]
    usage = [300,80,100,120,25,100,500,50]
    # Fixed independent synthetic count observations: mango includes a 3kg shortage.
    counted = [644,232,156.75,375,105,270,780,137]
    demand = [660,220,170,300,80,200,600,100]
    write("inventory.csv", [dict(sku=p[0], snapshot_date=d, qty_on_hand=q, uom=p[3],
        evidence_ref=f"COUNT-{stage}-{i+1:02d}")
        for i,p in enumerate(PRODUCTS)
        for stage,d,q in [("OPEN","2026-08-31",opening[i]),("CLOSE","2026-09-30",counted[i])]])
    write("inventory_movements.csv", [dict(movement_id=f"ISS-{i+1:03d}", sku=p[0],
        movement_date="2026-09-30", movement_type="production_issue", qty_base=-usage[i],
        uom=p[3], evidence_ref=f"ISSUE-DOC-{i+1:03d}") for i,p in enumerate(PRODUCTS)])
    write("production_requirements.csv", [dict(production_order=f"PLAN-{i+1:03d}", sku=p[0],
        required_date="2026-10-03", required_qty_base=demand[i], uom=p[3],
        owner="production-planner@example.com", evidence_ref="SYNTHETIC-PLAN-OCT03")
        for i,p in enumerate(PRODUCTS)])
    print("Synthetic sources reset. NZD costs exclude GST. No realised savings asserted.")


if __name__ == "__main__":
    main()
