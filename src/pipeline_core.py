"""Validated source loading and receipt-level mapping. No output writes."""
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
PERIOD_START = pd.Timestamp("2026-09-01").date()
PERIOD_END = pd.Timestamp("2026-09-30").date()
AS_OF = pd.Timestamp("2026-10-02").date()


@dataclass
class InvestigationResult:
    cleansed_receipts: pd.DataFrame = field(default_factory=pd.DataFrame)
    review_queue: pd.DataFrame = field(default_factory=pd.DataFrame)
    quality_summary: dict = field(default_factory=dict)
    approved_changes: pd.DataFrame = field(default_factory=pd.DataFrame)
    all_receipts: pd.DataFrame = field(default_factory=pd.DataFrame)
    duplicate_receipts: pd.DataFrame = field(default_factory=pd.DataFrame)


def load_raw_data(raw_dir=None):
    specs = {
        "products": ("products.csv", ["sku","base_uom","base_qty_per_case","standard_cost_nzd_per_base"]),
        "mapping": ("supplier_mapping.csv", ["mapping_id","supplier","supplier_item_code","sku",
                    "effective_from","effective_to","supplier_uom","base_qty_per_case","conversion_factor","approval_cr_id"]),
        "receipts": ("goods_received.csv", ["receipt_id","source_line_id","receipt_date","posted_date",
                     "supplier","supplier_item_code","qty_received","receipt_uom","batch_ref"]),
        "inventory": ("inventory.csv", ["sku","snapshot_date","qty_on_hand","uom","evidence_ref"]),
        "movements": ("inventory_movements.csv", ["movement_id","sku","movement_date","qty_base","uom","evidence_ref"]),
        "requirements": ("production_requirements.csv", ["production_order","sku","required_date","required_qty_base","uom"]),
        "change_requests": ("change_requests.csv", ["cr_id","supplier","supplier_item_code","proposed_sku","cr_type",
                            "effective_from","proposed_base_qty_per_case","proposed_conversion_factor","evidence_ref"]),
    }
    numeric = {"base_qty_per_case","standard_cost_nzd_per_base","conversion_factor","qty_received",
               "qty_on_hand","qty_base","required_qty_base","proposed_base_qty_per_case","proposed_conversion_factor"}
    dates = {"effective_from","effective_to","receipt_date","posted_date","snapshot_date","movement_date","required_date"}
    raw = {}
    for name,(filename,required) in specs.items():
        df = pd.read_csv((raw_dir or RAW_DIR)/filename, dtype=str)
        missing = set(required)-set(df.columns)
        if missing:
            raise ValueError(f"{filename}: missing columns {sorted(missing)}")
        for col in df.columns:
            if col in numeric:
                df[col] = pd.to_numeric(df[col], errors="raise")
            elif col in dates:
                df[col] = pd.to_datetime(df[col], errors="raise").dt.date
        nullable = {"base_qty_per_case","conversion_factor"} if name=="mapping" else set()
        if df[[c for c in required if c not in nullable]].isna().any().any():
            raise ValueError(f"{filename}: required value is missing")
        raw[name] = df
    for name,key in [("products","sku"),("mapping","mapping_id"),("receipts","receipt_id"),
                     ("movements","movement_id"),("requirements","production_order"),("change_requests","cr_id")]:
        if raw[name][key].duplicated().any():
            raise ValueError(f"{name}: duplicate {key}")
    if raw["inventory"].duplicated(["sku","snapshot_date"]).any():
        raise ValueError("inventory: duplicate SKU snapshot")
    if (raw["mapping"]["effective_from"] > raw["mapping"]["effective_to"]).any():
        raise ValueError("mapping: inverted effective window")
    for name,col in [("products","standard_cost_nzd_per_base"),("products","base_qty_per_case"),
                     ("mapping","base_qty_per_case"),("mapping","conversion_factor"),
                     ("receipts","qty_received"),("requirements","required_qty_base")]:
        if (raw[name][col].dropna() <= 0).any():
            raise ValueError(f"{name}: {col} must be positive")
    prod = raw["products"].set_index("sku")
    for name in ("mapping","inventory","movements","requirements"):
        if not set(raw[name]["sku"]).issubset(set(prod.index)):
            raise ValueError(f"{name}: unknown SKU")
    for name in ("inventory","movements","requirements"):
        if not raw[name]["uom"].eq(raw[name]["sku"].map(prod["base_uom"])).all():
            raise ValueError(f"{name}: unit must equal product base unit")
    if (raw["receipts"]["posted_date"] < raw["receipts"]["receipt_date"]).any():
        raise ValueError("receipt posted before receipt date")
    return raw


def detect_duplicate_receipts(receipts):
    """A repeated source document line is a duplicate; batch alone is not a key.
    Conflicting reimports with the same source key block the run for investigation.
    """
    df = receipts.sort_values("receipt_id").copy()
    keys = ["supplier","source_line_id"]
    fields = ["supplier_item_code","qty_received","receipt_uom","batch_ref","receipt_date"]
    if not df.empty:
        conflicts = df.groupby(keys)[fields].nunique(dropna=False).gt(1).any(axis=1)
        if conflicts.any():
            raise ValueError("Conflicting duplicate source line; reconcile source evidence before reporting")
    df["is_duplicate"] = df.duplicated(keys, keep="first")
    return df, df.loc[df["is_duplicate"],"receipt_id"].tolist()


def resolve_mappings(receipts, mappings):
    extra = ["resolved_sku","mapping_id","supplier_uom","base_qty_per_case",
             "conversion_factor","approval_cr_id","mapping_status","candidate_skus"]
    rows = []
    for _,r in receipts.iterrows():
        all_versions = mappings[(mappings["supplier"]==r["supplier"]) &
                                (mappings["supplier_item_code"]==r["supplier_item_code"])]
        candidates = all_versions[(all_versions["effective_from"]<=r["receipt_date"]) &
                                  (all_versions["effective_to"]>=r["receipt_date"])]
        row = dict(r)
        row.update({c:None for c in extra})
        row["candidate_skus"] = "; ".join(sorted(all_versions["sku"].unique()))
        if len(candidates)==1:
            m = candidates.iloc[0]
            row.update({c:m[c] for c in ["mapping_id","supplier_uom","base_qty_per_case","conversion_factor","approval_cr_id"]})
            row.update(resolved_sku=m["sku"],mapping_status="resolved")
        elif len(candidates)>1:
            row["mapping_status"] = "ambiguous_mapping"
        elif all_versions.empty:
            row["mapping_status"] = "missing_mapping"
        elif r["receipt_date"] < all_versions["effective_from"].min():
            row["mapping_status"] = "not_yet_effective"
        else:
            row["mapping_status"] = "expired_mapping"
        rows.append(row)
    df = pd.DataFrame(rows, columns=list(receipts.columns)+extra)
    return df[df["mapping_status"].eq("resolved")].copy(), df[~df["mapping_status"].eq("resolved")].copy()
