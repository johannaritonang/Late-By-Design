"""Helpers for the Late by Design notebook.

`load()` cleans the raw order-line extract with exactly the same rules as the Power BI model
(promised-date repair, delivery status, stock status, flags), so the numbers reconcile with the dashboard.
"""
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- palette (matches the Power BI report)
NAVY, BLUE, RED, AMBER, GREEN, PURPLE, SLATE, INK, MUTED, LINE = (
    "#0B2545", "#2563EB", "#EF4444", "#F59E0B", "#10B981", "#8B5CF6", "#64748B", "#0F172A", "#64748B", "#E2E8F0")


def style_charts():
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#CBD5E1",
                         "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlecolor": INK, "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED, "figure.facecolor": "white", "axes.facecolor": "white"})


def find_workbook(folders):
    """First .xlsx whose name mentions 'assessment' or 'raw' in the given folders."""
    for folder in folders:
        folder = Path(folder)
        if folder.exists():
            hits = sorted(f for f in folder.glob("*.xlsx") if not f.name.startswith("~$")
                          and any(k in f.name.lower() for k in ("assessment", "raw", "order")))
            if hits:
                return hits[0]
    return None


# ---------------------------------------------------------------- cleaning (mirrors the Power BI query)
def _fix_promise(raw, entry):
    """Repair the promised delivery date: text dates, impossible years (2925, 0224, ...) and 1899 placeholders."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return pd.NaT, "Missing"
    try:
        if isinstance(raw, str):
            y, m, d = (int(p) for p in raw.strip().split("-"))
        else:
            ts = pd.Timestamp(raw)
            y, m, d = ts.year, ts.month, ts.day
    except Exception:
        return pd.NaT, "Missing"
    if y == 1899:
        return pd.NaT, "Missing"

    def safe(yy):
        last = pd.Timestamp(yy, m, 1) + pd.offsets.MonthEnd(0)
        return pd.Timestamp(yy, m, min(d, last.day))

    diff = y - entry.year
    if y < 1900 or diff > 2 or diff < -1:
        fixed = safe(entry.year)
        if fixed < entry:
            fixed = safe(entry.year + 1)
        return fixed, "Year Typo Fixed"
    as_is = safe(y)
    return as_is, ("Promise Before Entry" if as_is < entry else "Valid")


def load(path):
    raw = pd.read_excel(path, sheet_name=0)
    d = raw.copy()
    for c in ("ENTRY_DATE", "SHIP_DATE", "REC_DATE"):
        d[c] = pd.to_datetime(d[c]).dt.normalize()

    key_cols = [c for c in raw.columns if c not in ("Id", "SOD_AUTO_KEY")]
    d["possible_duplicate"] = raw[key_cols].astype(str).duplicated(keep=False)

    fixed = [_fix_promise(r, e) for r, e in zip(d.DELIVERY_DATE, d.ENTRY_DATE)]
    d["promised_date"] = pd.to_datetime([f[0] for f in fixed])
    d["promise_quality"] = [f[1] for f in fixed]
    as_of = d.ENTRY_DATE.max()
    valid = d.promised_date.notna() & (d.promise_quality != "Promise Before Entry")

    status = np.select(
        [d.SHIP_DATE.isna() & ~valid, d.SHIP_DATE.isna() & (d.promised_date < as_of), d.SHIP_DATE.isna(),
         ~valid, d.SHIP_DATE > d.promised_date],
        ["Not Shipped", "Overdue (Not Shipped)", "Open (Not Due)", "No Valid Promise Date", "Late"], default="On Time")
    d["status"] = status
    d["days_late"] = np.where(d.status == "Late", (d.SHIP_DATE - d.promised_date).dt.days, np.nan)
    proc = (d.SHIP_DATE - d.ENTRY_DATE).dt.days
    d["processing_days"] = proc.where(proc >= 0)
    d["promised_lead_days"] = np.where(valid, (d.promised_date - d.ENTRY_DATE).dt.days, np.nan)
    d["stock_status"] = np.where(d.REC_DATE.isna(), "No Receipt Date", np.where(d.REC_DATE > d.ENTRY_DATE, "Backorder", "In Stock"))
    d["order_type"] = np.where(d.SCHEDULED == "SCH", "Scheduled", "Regular")
    d["sourcing"] = np.where(d.BROKERED_FLAG == "T", "Brokered", "Own Stock")
    d["operator_region"] = d.OperatorWorldRegion.fillna("Unmapped").replace("", "Unmapped")
    d["sales_region"] = d.REGION.fillna("Unknown").replace("", "Unknown")
    d["product_line"] = d.PRODUCT_LINE.fillna("Unknown").replace("", "Unknown")
    d["as_of"] = as_of
    return d


def scored(d):
    """Lines that can be judged late / on time (shipped, with a valid promise)."""
    s = d[d.status.isin(["Late", "On Time"])].copy()
    s["late"] = (s.status == "Late").astype(int)
    return s


# ---------------------------------------------------------------- features known when the order is entered
CATEGORICAL = ["supplier", "product_line", "product_type", "stock_category", "sales_region", "sales_channel",
               "operator_region", "order_type", "sourcing", "buy_plan", "stock_status"]
NUMERIC = ["promised_lead_days", "supplier_lead_days", "promise_gap", "qty", "log_unit_price", "entry_month", "entry_weekday",
           "lines_in_order", "part_history_lines"]
LABELS = {"promise_gap": "promise − supplier lead (days)", "promised_lead_days": "promised lead time (days)",
          "supplier_lead_days": "supplier lead time (days)", "stock_status": "stock at entry", "supplier": "supplier",
          "log_unit_price": "unit price (log)", "qty": "quantity", "entry_month": "entry month", "entry_weekday": "entry weekday",
          "lines_in_order": "lines in the same order", "part_history_lines": "earlier lines for this part",
          "product_line": "product line", "product_type": "product type", "stock_category": "stock category",
          "sales_region": "sales region", "sales_channel": "sales channel", "operator_region": "operator region",
          "order_type": "order type", "sourcing": "sourcing", "buy_plan": "buy plan"}


def features(s):
    f = pd.DataFrame(index=s.index)
    f["supplier"] = s.MFG_NAME.fillna("Unknown")
    f["product_line"] = s.product_line
    f["product_type"] = s.PRODUCT_TYPE.fillna("Unknown")
    f["stock_category"] = s.STOCK_CATEGORY_CODE.fillna("Unknown")
    f["sales_region"] = s.sales_region
    f["sales_channel"] = s.REGION_SP.fillna("Unknown")
    f["operator_region"] = s.operator_region
    f["order_type"] = s.order_type
    f["sourcing"] = s.sourcing
    f["buy_plan"] = s.BUY_PLAN_CODE.fillna("Unknown")
    f["stock_status"] = s.stock_status
    f["promised_lead_days"] = s.promised_lead_days
    f["supplier_lead_days"] = s.LEAD_DAYS
    f["promise_gap"] = s.promised_lead_days - s.LEAD_DAYS
    f["qty"] = s.QTY_SOLD
    f["log_unit_price"] = np.log1p(s.EXT_PRICE.clip(lower=0) / s.QTY_SOLD.replace(0, np.nan))
    f["entry_month"] = s.ENTRY_DATE.dt.month
    f["entry_weekday"] = s.ENTRY_DATE.dt.weekday
    f["lines_in_order"] = s.groupby("SO_NUMBER").Id.transform("count")
    order = s.sort_values("ENTRY_DATE")
    f["part_history_lines"] = order.groupby("PN").cumcount().reindex(s.index)
    for c in CATEGORICAL:
        f[c] = f[c].astype("category")
    return f
