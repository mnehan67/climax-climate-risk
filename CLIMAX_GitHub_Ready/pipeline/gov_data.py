"""UAE government open data: Dubai Land Department (DLD) real-estate transactions from Data.Dubai / Dubai Pulse.

Why: collateral values for the (synthetic) loan book are anchored to REAL government transaction prices
(median AED per m² in the same districts), instead of invented numbers.

How to get the file (manual; the Data.Dubai API needs a key):
  data.dubai → Dubai Land Department → "Transactions" (open dataset) → export CSV
  save it as   data/gov/dld_transactions.csv     (any file name in data/gov/ ending .csv works)
Then:  python3 -m pipeline.gov_data          (re-prices the loan book; no internet needed)

The loader is tolerant to column naming: it looks for an area-name column, a price-per-m² column
(or worth / area), and optionally usage, transaction group and date.
"""
from __future__ import annotations
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config

GOV_DIR = config.ROOT / "data" / "gov"
OUT_FILE = config.OUT / "gov_prices.json"

# DLD area names that fall inside each analysis area (matched case-insensitively by keyword)
AREA_KEYWORDS = {
    "alquoz": ["quoz", "qouz", "barsha"],
    "jebelali": ["furjan", "jebel ali", "jabal ali", "discovery", "garden"],
    "dxb": ["garhoud", "garhood", "rashidiya", "rashidiy", "airport", "nahda", "twar", "qusais", "mamzar", "mizhar"],
}
CSV_FIELD_LIMIT = 10_000_000


def _find(cols, *needles):
    low = {c.lower().strip(): c for c in cols}
    for n in needles:
        for lc, c in low.items():
            if n in lc:
                return c
    return None


def _num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def load_dld(paths=None, since_year=2021):
    paths = paths or sorted(GOV_DIR.glob("*.csv"))
    if not paths:
        return None
    csv.field_size_limit(CSV_FIELD_LIMIT)
    prices = {a: {"residential": [], "commercial": [], "all": []} for a in AREA_KEYWORDS}
    matched_names = {a: set() for a in AREA_KEYWORDS}
    rows_read = rows_used = 0
    used_files = []
    for p in paths:
        with open(p, newline="", encoding="utf-8-sig", errors="replace") as f:
            r = csv.DictReader(f)
            cols = r.fieldnames or []
            c_area = _find(cols, "area_name_en", "area_name", "area")
            c_ppm = _find(cols, "meter_sale_price", "price_per_sqm", "meter_price")
            c_worth = _find(cols, "actual_worth", "trans_value", "amount", "worth")
            c_size = _find(cols, "procedure_area", "property_size", "actual_area", "size")
            c_use = _find(cols, "property_usage_en", "property_usage", "usage")
            c_grp = _find(cols, "trans_group_en", "trans_group", "transaction_type")
            c_date = _find(cols, "instance_date", "transaction_date", "date")
            if not c_area or not (c_ppm or (c_worth and c_size)):
                print(f"skip {p.name}: needs an area-name column and a price-per-m² (or worth + size) column. Columns: {cols[:12]}")
                continue
            used_files.append(p.name)
            for row in r:
                rows_read += 1
                if c_grp and row.get(c_grp) and "sale" not in row[c_grp].lower():
                    continue
                if c_date and row.get(c_date):
                    yr = row[c_date][:4] if row[c_date][:4].isdigit() else row[c_date][-4:]
                    if yr.isdigit() and int(yr) < since_year:
                        continue
                name = (row.get(c_area) or "").lower()
                aoi = next((a for a, kws in AREA_KEYWORDS.items() if any(k in name for k in kws)), None)
                if not aoi:
                    continue
                ppm = _num(row.get(c_ppm)) if c_ppm else None
                if not ppm and c_worth and c_size:
                    w, s = _num(row.get(c_worth)), _num(row.get(c_size))
                    ppm = w / s if w and s else None
                if not ppm or not (200 <= ppm <= 200_000):     # drop obvious data-entry errors
                    continue
                use = (row.get(c_use) or "").lower() if c_use else ""
                cls = "residential" if "resid" in use else "commercial" if any(k in use for k in ("commerc", "industr", "office", "retail", "hospitality")) else None
                prices[aoi]["all"].append(ppm)
                if cls:
                    prices[aoi][cls].append(ppm)
                matched_names[aoi].add(row.get(c_area))
                rows_used += 1
    if not used_files:
        return None
    by_aoi = {}
    for a, d in prices.items():
        if not d["all"]:
            continue
        by_aoi[a] = {k: round(statistics.median(v)) if v else None for k, v in d.items()}
        by_aoi[a]["n"] = len(d["all"])
        by_aoi[a]["areas"] = sorted(x for x in matched_names[a] if x)[:12]
    return {"source": "Dubai Land Department transactions · Data.Dubai (Dubai Pulse open data)",
            "url": "https://data.dubai/en", "files": used_files, "since_year": since_year,
            "rows_read": rows_read, "rows_used": rows_used, "by_aoi": by_aoi,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def price_for(gov, aoi, use):
    if not gov or aoi not in gov.get("by_aoi", {}):
        return None
    d = gov["by_aoi"][aoi]
    key = "residential" if use == "residential" else "commercial"
    return d.get(key) or d.get("all")


def buildings_from_outputs():
    out = {}
    m = config.OUT / "manifest.json"
    aois = json.loads(m.read_text()).get("aois", []) if m.exists() else []
    for a in aois:
        p = config.OUT / a / "buildings.geojson"
        if p.exists():
            fc = json.loads(p.read_text())
            out[a] = [{"id": f["properties"]["id"], "use": f["properties"]["use"], "height": f["properties"].get("height", 8),
                       "area_m2": f["properties"].get("area_m2") or 600} for f in fc["features"]]
    return out


def main():
    from . import loans as loanmod
    gov = load_dld()
    if not gov:
        print(f"No usable CSV in {GOV_DIR}. Download DLD transactions from data.dubai and save it there.")
        sys.exit(1)
    OUT_FILE.write_text(json.dumps(gov, indent=1))
    print(json.dumps({k: v for k, v in gov.items() if k != "by_aoi"}, indent=1))
    for a, d in gov["by_aoi"].items():
        print(f"  {a:9s} median AED/m²: all {d['all']}, residential {d['residential']}, commercial {d['commercial']}  (n={d['n']})")
    mf = json.loads((config.OUT / "manifest.json").read_text())
    label = "SYNTHETIC LOAN ON TEST BUILDING" if mf.get("mode") == "TEST" else "SYNTHETIC LOAN ON REAL BUILDING"
    loans = loanmod.make_loans(buildings_from_outputs(), gov=gov, label=label)
    loanmod.write(loans)
    print(f"Re-priced {len(loans)} synthetic loans with DLD collateral values → {config.OUT / 'loans.json'}")


if __name__ == "__main__":
    main()
