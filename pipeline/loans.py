"""Synthetic SME loan book placed on REAL building footprints.

Fairness rule: loans are assigned to buildings by building TYPE only, using a fixed seed, BEFORE and
WITHOUT looking at any flood result. So the share of flooded loans is not cherry-picked.
All money values are synthetic and labelled as such.
"""
from __future__ import annotations
import json
import random

from . import config

SECTOR_BY_USE = {
    "warehouse": ["Logistics", "Wholesale", "Food distribution"],
    "industrial": ["Light manufacturing", "Auto services", "Construction supplies"],
    "commercial": ["Retail", "Wholesale", "Professional services"],
    "retail": ["Retail", "Food & beverage"],
    "office": ["Professional services", "IT services"],
    "hospitality": ["Hospitality"],
    "residential": ["Real-estate SME", "Property management"],
    "unknown": ["Trading", "Services"],
}
OPS_WEIGHT = {"warehouse": 5, "industrial": 5, "commercial": 3, "retail": 2, "office": 2, "hospitality": 1,
              "unknown": 1.2, "residential": 0.3}
COLL_WEIGHT = {"warehouse": 3, "industrial": 3, "commercial": 3, "retail": 2, "office": 2, "residential": 3,
               "hospitality": 1, "unknown": 1}
SECTOR_PD = {"Logistics": 1.8, "Wholesale": 2.2, "Food distribution": 2.0, "Light manufacturing": 2.6,
             "Auto services": 2.9, "Construction supplies": 3.1, "Retail": 2.7, "Professional services": 1.5,
             "IT services": 1.6, "Food & beverage": 3.4, "Hospitality": 2.4, "Real-estate SME": 1.9,
             "Property management": 1.4, "Trading": 2.5, "Services": 2.1}


def _collateral_value(rng, aoi, b, gov):
    """Value of the pledged property. With DLD data: real median AED/m² of the district x a plausible unit size."""
    from .gov_data import price_for
    ppm = price_for(gov, aoi, b["use"])
    if not ppm:
        return None
    if b["use"] in ("residential", "office", "hospitality"):
        size = rng.uniform(90, 260)                                   # a unit / floor in the building
    else:
        size = min(max(float(b.get("area_m2") or 600), 150), 4000)    # owner-occupied warehouse / shop footprint
    return round(size * ppm, -4)


def make_loans(buildings_by_aoi: dict, n=config.N_LOANS, seed=config.LOAN_SEED, label="SYNTHETIC LOAN ON REAL BUILDING", gov=None):
    rng = random.Random(seed)
    pool = [(aoi, b) for aoi, bs in buildings_by_aoi.items() for b in bs]
    if not pool:
        return []
    ops_w = [OPS_WEIGHT.get(b["use"], 1) for _, b in pool]
    coll_w = [COLL_WEIGHT.get(b["use"], 1) for _, b in pool]
    loans = []
    for i in range(n):
        ops_aoi, ops = rng.choices(pool, ops_w)[0]
        if rng.random() < 0.55:      # owner-occupied: business premises pledged as collateral
            coll_aoi, coll, coll_type = ops_aoi, ops, "Owner-occupied premises"
        else:
            coll_aoi, coll = rng.choices(pool, coll_w)[0]
            coll_type = "Residential property" if coll["use"] == "residential" else "Commercial property"
        sector = rng.choice(SECTOR_BY_USE.get(ops["use"], SECTOR_BY_USE["unknown"]))
        ltv = rng.uniform(0.45, 0.8)
        cv = _collateral_value(rng, coll_aoi, coll, gov)
        if cv:                                                     # DLD-anchored: loan = collateral x LTV
            ead = min(max(round(cv * ltv, -4), 300_000), 60_000_000)
            value_src = "DLD median AED/m² (Data.Dubai)"
        else:
            ead = round(rng.lognormvariate(15.6, 0.7), -4)        # median ~6M AED
            ead = min(max(ead, 750_000), 60_000_000)
            cv = round(ead / ltv, -4)
            value_src = "synthetic (no DLD file)"
        pd = round(SECTOR_PD.get(sector, 2.2) * rng.uniform(0.6, 1.5), 2)
        lgd = rng.choice([22, 25, 28, 30, 35, 40])
        loans.append({
            "loan_id": f"SME-{i + 1:03d}", "borrower": f"Illustrative {sector} SME #{i + 1:03d}", "sector": sector,
            "ops_aoi": ops_aoi, "ops_building": ops["id"], "ops_use": ops["use"],
            "coll_aoi": coll_aoi, "coll_building": coll["id"], "coll_type": coll_type,
            "ead_aed": ead, "collateral_value_aed": cv, "collateral_value_source": value_src, "pd_pct": pd, "lgd_pct": lgd,
            "insurance_cover": rng.choice([0.0, 0.0, 0.5, 0.5, 0.8]),
            "data_class": label,
        })
    return loans


def write(loans, path=None):
    path = path or (config.OUT / "loans.json")
    path.write_text(json.dumps({"seed": config.LOAN_SEED, "rule": "assigned by building type with fixed seed, blind to flood results",
                                "class": "SYNTHETIC", "loans": loans}, indent=1))
