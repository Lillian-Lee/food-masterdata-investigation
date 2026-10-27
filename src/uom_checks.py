"""Approved conversion and order-independent effective-date risk flags."""
import pandas as pd


def check_uom_consistency(resolved, products):
    df = resolved.copy()
    prod = products.set_index("sku")
    df["base_uom"] = df["resolved_sku"].map(prod["base_uom"])
    df["product_pack_size"] = df["resolved_sku"].map(prod["base_qty_per_case"])
    df["unit_cost_nzd"] = df["resolved_sku"].map(prod["standard_cost_nzd_per_base"])
    df["uom_match"] = df["receipt_uom"].eq(df["base_uom"])
    df["qty_base"] = float("nan")
    df["conversion_status"] = "unapproved_conversion"
    df["uom_note"] = ""
    for idx,r in df.iterrows():
        factor = None
        if r["receipt_uom"]==r["base_uom"]:
            factor = 1
        elif r["receipt_uom"]=="CASE" and pd.notna(r["base_qty_per_case"]):
            factor = r["base_qty_per_case"]
        elif r["receipt_uom"]==r["supplier_uom"] and pd.notna(r["conversion_factor"]):
            factor = r["conversion_factor"]
        if factor is not None and factor>0:
            df.loc[idx,"qty_base"] = r["qty_received"]*factor
            df.loc[idx,"conversion_status"] = "approved"
            df.loc[idx,"uom_note"] = f'{r["qty_received"]:g} {r["receipt_uom"]} x {factor:g} = {r["qty_received"]*factor:g} {r["base_uom"]}'
        else:
            df.loc[idx,"uom_note"] = f'Await approved {r["receipt_uom"]} to {r["base_uom"]} factor'
    df["pack_size_changed"] = df["base_qty_per_case"].notna() & df["base_qty_per_case"].ne(df["product_pack_size"])
    df["receipt_value_nzd"] = df["qty_base"]*df["unit_cost_nzd"]
    return df


def flag_effective_boundary(resolved, mappings):
    df = resolved.copy()
    df["days_to_boundary"] = pd.Series(index=df.index,dtype=float)
    df["near_boundary"] = False
    for idx,r in df.iterrows():
        versions = mappings[(mappings["supplier"]==r["supplier"]) &
                            (mappings["supplier_item_code"]==r["supplier_item_code"])]
        # Starts and ends both matter. Ignore the open-ended 2099 sentinel.
        boundaries = list(versions["effective_from"]) + [d for d in versions["effective_to"] if d.year<2099]
        if boundaries:
            delta = min(((r["receipt_date"]-d).days for d in boundaries),key=lambda v:(abs(v),v))
            df.loc[idx,"days_to_boundary"] = delta
            df.loc[idx,"near_boundary"] = abs(delta)<=2
    return df
