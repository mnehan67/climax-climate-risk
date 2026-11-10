"""Turn raw arrays (real or test) into flood, persistence, depth, prediction and per-building metrics."""
from __future__ import annotations
from datetime import date as _date

import numpy as np

from . import config, core, grid as gridmod


def _valid(scl):
    return ~np.isin(scl, config.SCL_INVALID)


def analyze_aoi(aoi_id, g, raw, mode, log, notes=None):
    notes = list(notes or [])
    ev = _date.fromisoformat(config.EVENT_DATE)

    pre = raw["pre"]
    pre_valid = _valid(pre["scl"]) & np.isfinite(pre["green"]) & np.isfinite(pre["swir"])
    pre_idx = core.mndwi(pre["green"], pre["swir"])
    pre_water, pre_t = core.water_mask(pre_idx, pre_valid, config.MNDWI_CLAMP)
    log(aoi_id, "compute_index", {"index": "MNDWI", "date": pre["date"]},
        f"pre-storm water baseline · threshold {pre_t:.2f} · {pre_water.sum() * g.res ** 2 / 1e6:.2f} km² permanent/pre-existing water")

    post_dates, wet, valid, thr, scenes, rgbs = [], [], [], [], [], []
    for p in raw["posts"]:
        v = _valid(p["scl"]) & np.isfinite(p["green"]) & np.isfinite(p["swir"])
        idx = core.mndwi(p["green"], p["swir"])
        w, t = core.water_mask(idx, v, config.MNDWI_CLAMP)
        w = core.despeckle(w, config.MIN_FLOOD_PATCH_PX)
        day = (_date.fromisoformat(p["date"]) - ev).days
        post_dates.append((p["date"], day)); wet.append(w); valid.append(v); thr.append(t)
        scenes.append(p.get("scenes", [])); rgbs.append(p.get("rgb_png"))
        new = w & ~(pre_water & pre_valid)
        log(aoi_id, "detect_water", {"date": p["date"], "day": day},
            f"{new.sum() * g.res ** 2 / 1e6:.2f} km² new water · cloud-free {v.mean() * 100:.0f}% · Otsu t={t:.2f}")

    persist = core.persistence(pre_water, pre_valid, np.array(wet), np.array(valid), [d for _, d in post_dates])
    fl_km2 = persist["flooded"].sum() * g.res ** 2 / 1e6
    log(aoi_id, "persistence", {"observations": len(post_dates)},
        f"{fl_km2:.2f} km² flooded · {persist['censored'].sum() * g.res ** 2 / 1e6:.2f} km² still wet at last clear pass")

    dem = raw["dem"]
    depth = core.fwdet_depth(persist["flooded"], dem, cap=config.DEPTH_CAP_M)
    filled = core.priority_flood(dem)
    dep_depth = filled - dem
    tpi_map = core.tpi(dem, size_px=max(5, int(500 / g.res) | 1))
    log(aoi_id, "terrain", {"dem": "Copernicus GLO-30", "fill": "Priority-Flood"},
        f"DEM {np.nanmin(dem):.1f}–{np.nanmax(dem):.1f} m · median FwDET depth {np.median(depth[depth > 0]) if (depth > 0).any() else 0:.2f} m")

    obs_valid = pre_valid & np.array(valid).any(0)
    pred, report = core.calibrate_predictor(dep_depth, tpi_map, persist["flooded"], obs_valid, calib_cols=g.width // 2)
    log(aoi_id, "validate_prediction", {"split": "spatial west/east"},
        f"terrain-only forecast vs satellite · holdout IoU {report['holdout']['iou']:.2f} (random {report['random_baseline_holdout']['iou']:.2f})")

    buildings = raw["buildings"]
    rings = gridmod.ring_labels(g, buildings)
    metrics = core.building_metrics(rings, len(buildings), persist["flooded"], persist["last_wet_day"], depth, pred)
    nf = sum(m["flooded"] for m in metrics)
    log(aoi_id, "join_buildings", {"source": "OpenStreetMap", "ring_m": config.BUILDING_RING_M},
        f"{len(buildings):,} footprints · {nf:,} with water in their 15 m ring · {sum(m['days'] >= 7 for m in metrics):,} wet ≥ 7 days")

    dem_stats = {"min": round(float(np.nanmin(dem)), 1), "max": round(float(np.nanmax(dem)), 1)}
    meta = gridmod.export_aoi(
        aoi_id, g, rgb_pre=pre["rgb_png"], rgb_posts=rgbs, pre_valid=pre_valid, post_dates=post_dates,
        wet_stack=np.array(wet), valid_stack=np.array(valid), thresholds=thr, scene_ids=scenes,
        pre_meta={"date": pre["date"], "scenes": pre.get("scenes", []), "valid_frac": round(float(pre_valid.mean()), 3),
                  "mndwi_threshold": round(pre_t, 3)},
        persist=persist, depth=depth, pred=pred, pred_report=report, buildings_ll=buildings, metrics=metrics,
        dem_stats=dem_stats, mode=mode, notes=notes)
    return meta
