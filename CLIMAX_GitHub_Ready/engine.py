"""CLIMAX finance engine: satellite-measured flood DURATION -> PD, flood DEPTH -> LGD, per loan.

Formulae (all assumptions are explicit parameters, shown in the UI and in every export):
  interruption_days = days the ring around the OPERATING building was last seen wet  x persist_mult
  PD_stressed  = min(PD x pd_cap, PD x (1 + beta x interruption_days))
  damage       = JRC depth-damage(depth at COLLATERAL building x depth_mult)
  value_loss   = collateral_value x damage x (1 - insurance_cover)
  LGD_stressed = min(100%, LGD + value_loss / EAD)
  dEL          = EAD x PD_stressed x LGD_stressed - EAD x PD x LGD
This is a one-period expected-loss sensitivity for triage, NOT IFRS 9 ECL and NOT a capital number.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GEN = ROOT / "data" / "generated"

JRC_DEPTH = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]
JRC_DAMAGE = [0.0, 0.33, 0.49, 0.62, 0.72, 0.87, 0.93, 0.98, 1.0]

DEFAULTS = {"beta": 0.10, "pd_cap": 5.0, "persist_mult": 1.0, "depth_mult": 1.0}
LIMITS = {"beta": (0.0, 0.5), "pd_cap": (1.0, 10.0), "persist_mult": (0.5, 3.0), "depth_mult": (0.5, 3.0)}

SOURCES = [
    {"name": "ESA · Dubai floods seen from space (Sentinel-2, 17 Apr 2024)", "url": "https://www.esa.int/ESA_Multimedia/Images/2024/04/Dubai_floods_seen_from_space"},
    {"name": "MBZUAI · Emirates & Oman rain case study (S. Khan et al., May 2024)", "url": "https://staticcdn.mbzuai.ac.ae/mbzuaiwpprd01/2024/05/EmiratesAndOman_RainCaseStudy.pdf"},
    {"name": "CBUAE · Climate Forum Report 2025 (stress-test design: damage costs, foregone revenue excluded)", "url": "https://www.centralbank.ae/media/avspmt1i/cbuae-climate-forum-report_2025_a4_e.pdf"},
    {"name": "Zayed University · Flood footprints in Dubai after April 2024 (23.8 km², ~95% still wet after 3 days)", "url": "https://zuscholars.zu.ac.ae/works/7863"},
    {"name": "MBZUAI · OpenEarthAgent: tool-augmented geospatial agents (2026)", "url": "https://arxiv.org/abs/2602.17665"},
    {"name": "NASA Earth Observatory · Deluge in the UAE", "url": "https://science.nasa.gov/earth/earth-observatory/deluge-in-the-united-arab-emirates-152703/"},
    {"name": "Xu 2006 · MNDWI water index", "url": "https://doi.org/10.1080/01431160600589179"},
    {"name": "Cohen et al. 2018 · FwDET flood depth from extent + DEM", "url": "https://doi.org/10.1111/1752-1688.12609"},
    {"name": "Barnes et al. 2014 · Priority-Flood depression filling", "url": "https://doi.org/10.1016/j.cageo.2013.04.024"},
    {"name": "Huizinga et al. 2017 · JRC global flood depth-damage functions", "url": "https://publications.jrc.ec.europa.eu/repository/handle/JRC105688"},
    {"name": "Dubai Land Department transactions · Data.Dubai / Dubai Pulse (collateral AED/m², when provided)", "url": "https://data.dubai/en"},
    {"name": "CBUAE · Challenge Profile 1: Climate Financial Risk Intelligence (UAE Hackathon 2026)", "url": "https://www.centralbank.ae/"},
    {"name": "Element 84 Earth Search · Sentinel-2 L2A COGs", "url": "https://earth-search.aws.element84.com/v1"},
    {"name": "Copernicus DEM GLO-30", "url": "https://registry.opendata.aws/copernicus-dem/"},
    {"name": "OpenStreetMap contributors (ODbL)", "url": "https://www.openstreetmap.org/copyright"},
]


def interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            t = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


def damage_fraction(depth_m):
    return interp(max(0.0, depth_m), JRC_DEPTH, JRC_DAMAGE)


# ------------------------------------------------------------------ data loading (mtime-cached)
_CACHE: dict = {}


def _load(path: Path):
    key = str(path); mt = path.stat().st_mtime
    hit = _CACHE.get(key)
    if hit and hit[0] == mt:
        return hit[1]
    val = json.loads(path.read_text(encoding="utf-8"))
    _CACHE[key] = (mt, val)
    return val


def available() -> bool:
    return (GEN / "manifest.json").exists() and (GEN / "loans.json").exists()


def manifest():
    return _load(GEN / "manifest.json")


def meta(aoi):
    return _load(GEN / aoi / "meta.json")


def buildings_index(aoi):
    key = "bidx:" + aoi
    p = GEN / aoi / "buildings.geojson"
    mt = p.stat().st_mtime
    hit = _CACHE.get(key)
    if hit and hit[0] == mt:
        return hit[1]
    fc = _load(p)
    idx = {f["properties"]["id"]: f["properties"] for f in fc["features"]}
    _CACHE[key] = (mt, idx)
    return idx


def gov():
    p = GEN / "gov_prices.json"
    return _load(p) if p.exists() else None


# Proposed asset-level physical-risk record (addresses Challenge Profile 1 root causes R1-R3: no standard,
# siloed geolocation, no common taxonomy). One row per pledged asset / operating site.
ASSET_HAZARD_SCHEMA = [
    {"field": "asset_id", "type": "string", "example": "SME-012-COLL", "note": "bank internal id"},
    {"field": "role", "type": "enum", "example": "COLLATERAL | OPERATING_SITE"},
    {"field": "building_ref", "type": "string", "example": "osm-w123456 / DLD plot no.", "note": "geolocation key linking finance to hazard data"},
    {"field": "lon, lat", "type": "float", "example": "55.2312, 25.1421"},
    {"field": "hazard_event_id", "type": "string", "example": "UAE-PLUVIAL-2024-04-16"},
    {"field": "observed_flooded", "type": "bool", "example": "true", "note": "satellite, 15 m ring"},
    {"field": "days_wet_lower_bound", "type": "int", "example": "11"},
    {"field": "depth_indicative_m", "type": "float", "example": "0.6"},
    {"field": "evidence_scene_ids", "type": "string[]", "example": "S2B_40RCN_20240427_0_L2A"},
    {"field": "forecast_flagged", "type": "bool", "example": "false", "note": "did the hazard model see it coming"},
    {"field": "valuation_source", "type": "string", "example": "DLD median AED/m² 2021+"},
    {"field": "insurance_cover_pct", "type": "float", "example": "50"},
    {"field": "pd_uplift_x, lgd_uplift_pp", "type": "float", "example": "2.1, 8.5"},
    {"field": "review_status", "type": "enum", "example": "QUEUED | EVIDENCE_REQUESTED | CLEARED"},
]


def detection(aoi):
    m = meta(aoi)
    first = m["dates"][0] if m["dates"] else None
    return {"first_clear_pass": first["date"] if first else None, "days_after_event": first["day"] if first else None,
            "compare": "typical quarterly credit review: up to ~90 days"}


def loans():
    return _load(GEN / "loans.json")["loans"]


def clean_params(raw: dict | None):
    p = dict(DEFAULTS)
    for k, v in (raw or {}).items():
        if k in LIMITS and v not in (None, ""):
            lo, hi = LIMITS[k]
            v = float(v)
            if not math.isfinite(v) or not lo <= v <= hi:
                raise ValueError(f"{k} must be between {lo} and {hi}")
            p[k] = v
    return p


# ------------------------------------------------------------------ core computation
def _bmetrics(aoi, bid):
    if aoi not in manifest().get("aois", []):
        return None
    try:
        return buildings_index(aoi).get(bid)
    except FileNotFoundError:
        return None


def assess(loan, p, dates_by_aoi):
    ops = _bmetrics(loan["ops_aoi"], loan["ops_building"]) or {}
    col = _bmetrics(loan["coll_aoi"], loan["coll_building"]) or {}
    pd0 = loan["pd_pct"] / 100; lgd0 = loan["lgd_pct"] / 100; ead = loan["ead_aed"]
    ops_hit = bool(ops.get("flooded")); col_hit = bool(col.get("flooded"))
    days = (ops.get("days", 0) if ops_hit else 0) * p["persist_mult"]
    pd_s = min(1.0, pd0 * p["pd_cap"], pd0 * (1 + p["beta"] * days))
    depth = (col.get("depth_m", 0.0) if col_hit else 0.0) * p["depth_mult"]
    dmg = damage_fraction(depth) if col_hit else 0.0
    vloss = loan["collateral_value_aed"] * dmg * (1 - loan["insurance_cover"])
    lgd_s = min(1.0, lgd0 + vloss / ead)
    base = ead * pd0 * lgd0; stress = ead * pd_s * lgd_s
    channel = "DUAL" if ops_hit and col_hit else "OPERATIONS" if ops_hit else "COLLATERAL" if col_hit else "NONE"

    def last_date(aoi, d):
        ds = [x for x in dates_by_aoi.get(aoi, []) if x["day"] <= d]
        return ds[-1]["date"] if ds else None

    why = []
    if ops_hit:
        why.append(f"Operating site {loan['ops_building']}: water in {ops['wet_frac'] * 100:.0f}% of its 15 m ring; last seen wet on day {ops['days']}"
                   f" ({last_date(loan['ops_aoi'], ops['days'])}) → ~{days:.0f} interruption days → PD ×{pd_s / pd0:.2f}")
    if col_hit:
        why.append(f"Collateral {loan['coll_building']}: indicative depth {col['depth_m']:.2f} m → JRC damage {dmg * 100:.0f}%"
                   f" × uninsured {100 * (1 - loan['insurance_cover']):.0f}% → value loss AED {vloss:,.0f}")
    if not why:
        why.append("No water detected around either building on any clear satellite pass")
    return {**loan, "channel": channel, "ops_days": ops.get("days", 0) if ops_hit else 0,
            "ops_wet_frac": ops.get("wet_frac", 0), "coll_days": col.get("days", 0) if col_hit else 0,
            "coll_use": col.get("use", "unknown"), "coll_depth_m": col.get("depth_m", 0.0) if col_hit else 0.0,
            "interruption_days": round(days, 1), "pd_stress_pct": round(pd_s * 100, 2), "lgd_stress_pct": round(lgd_s * 100, 1),
            "damage_frac": round(dmg, 3), "value_loss_aed": round(vloss), "base_el": round(base), "stress_el": round(stress),
            "delta_el": round(stress - base), "why": why,
            "predicted_ops": (ops.get("pred_frac", 0) or 0) >= 0.10, "predicted_coll": (col.get("pred_frac", 0) or 0) >= 0.10}


def stress(params=None, aoi=None):
    p = clean_params(params)
    m = manifest()
    dates = {}
    for a in m.get("aois", []):
        try:
            dates[a] = meta(a)["dates"]
        except FileNotFoundError:
            pass
    rows = [assess(l, p, dates) for l in loans()]
    rows.sort(key=lambda r: r["delta_el"], reverse=True)
    in_aoi = [r for r in rows if aoi in (None, "all") or aoi in (r["ops_aoi"], r["coll_aoi"])]

    def summ(rs):
        hit = [r for r in rs if r["channel"] != "NONE"]
        return {"loans": len(rs), "ead": round(sum(r["ead_aed"] for r in rs)),
                "flagged": len(hit), "dual": sum(r["channel"] == "DUAL" for r in rs),
                "ops_only": sum(r["channel"] == "OPERATIONS" for r in rs), "coll_only": sum(r["channel"] == "COLLATERAL" for r in rs),
                "ead_flagged": round(sum(r["ead_aed"] for r in hit)),
                "base_el": round(sum(r["base_el"] for r in rs)), "stress_el": round(sum(r["stress_el"] for r in rs)),
                "delta_el": round(sum(r["delta_el"] for r in rs)),
                "delta_pd_channel": round(sum(r["ead_aed"] * (r["pd_stress_pct"] - r["pd_pct"]) / 100 * r["lgd_pct"] / 100 for r in rs)),
                "uninsured_flagged": sum(r["insurance_cover"] == 0 for r in hit),
                "missed_by_terrain_forecast": sum(1 for r in hit if not (r["predicted_ops"] or r["predicted_coll"]))}
    return {"mode": m.get("mode"), "params": p, "aoi": aoi or "all", "summary": summ(in_aoi), "portfolio": summ(rows),
            "loans": in_aoi, "formula": __doc__.split("Formulae")[1].split("This is")[0].strip(),
            "disclaimer": "Synthetic loans on real building footprints. One-period expected-loss sensitivity for triage, not IFRS 9 ECL, not capital, not a bank observation."}


def explain(loan_id, params=None):
    for r in stress(params)["loans"]:
        if r["loan_id"].lower() == str(loan_id).lower():
            return r
    return None
