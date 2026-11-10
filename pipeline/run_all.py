"""CLIMAX real-data pipeline.  Run from the project folder:

    python3 -m pipeline.run_all                # all areas
    python3 -m pipeline.run_all alquoz         # one area
    python3 -m pipeline.run_all --offline      # re-analyse from data/cache without internet

Needs internet once (Earth Search, AWS Copernicus DEM, Overpass). Takes ~5–15 min. Everything downloaded
is cached in data/cache, so the hackathon demo itself needs no internet.
"""
from __future__ import annotations
import json
import sys
import time
from datetime import datetime, timezone

import numpy as np

from . import analyze, config, core, fetch, grid as gridmod, loans as loanmod

CACHE = config.ROOT / "data" / "cache"
LOG: list = []
T0 = time.time()


def log(aoi, tool, args, result):
    entry = {"t_s": round(time.time() - T0, 1), "aoi": aoi, "tool": tool, "args": args, "result": result}
    LOG.append(entry)
    print(f"[{entry['t_s']:7.1f}s] {aoi:9s} {tool:20s} {result}", flush=True)


def _rgb(items, g):
    rgb = fetch.read_s2_layer(items, g, "rgb")
    return core.stretch_rgb(rgb, 1, 99) if rgb is not None else None


def download(aoi_id, g):
    a = config.AOIS[aoi_id]
    c = CACHE / aoi_id; c.mkdir(parents=True, exist_ok=True)
    by_date = fetch.search_s2(a["bbox"], config.PRE_WINDOW[0], config.POST_WINDOW[1])
    log(aoi_id, "search_stac", {"collection": config.S2_COLLECTION, "from": config.PRE_WINDOW[0], "to": config.POST_WINDOW[1]},
        f"{sum(len(v) for v in by_date.values())} Sentinel-2 items on {len(by_date)} dates")

    usable = {}
    for d, items in by_date.items():
        scl = fetch.read_s2_layer(items, g, "scl")
        vf = float((~np.isin(scl, config.SCL_INVALID)).mean())
        log(aoi_id, "cloud_check", {"date": d}, f"cloud-free {vf * 100:.0f}% of area" + ("" if vf >= config.MIN_AOI_VALID else " · skipped"))
        if vf >= config.MIN_AOI_VALID:
            usable[d] = (items, scl, vf)
    pre_dates = [d for d in usable if config.PRE_WINDOW[0] <= d <= config.PRE_WINDOW[1]]
    post_dates = [d for d in usable if config.POST_WINDOW[0] <= d <= config.POST_WINDOW[1]]
    if not pre_dates or not post_dates:
        raise RuntimeError(f"{aoi_id}: not enough clear scenes (pre={pre_dates}, post={post_dates}). "
                           "Lower MIN_AOI_VALID in pipeline/config.py and retry.")
    pre_d = max(pre_dates, key=lambda d: (round(usable[d][2], 2), d))   # clearest, latest on ties

    def layers(d):
        items, scl, _ = usable[d]
        return {"date": d, "scenes": [i.id for i in items], "scl": scl,
                "green": fetch.read_s2_layer(items, g, "green"), "swir": fetch.read_s2_layer(items, g, "swir"),
                "rgb_png": _rgb(items, g)}

    pre = layers(pre_d)
    log(aoi_id, "read_bands", {"date": pre_d, "bands": ["B03", "B11", "SCL", "TCI"]}, "pre-storm reference loaded")
    posts = []
    for d in post_dates:
        posts.append(layers(d))
        log(aoi_id, "read_bands", {"date": d, "bands": ["B03", "B11", "SCL", "TCI"]}, "post-storm scene loaded")
    dem = fetch.read_dem(g)
    log(aoi_id, "read_dem", {"source": "Copernicus GLO-30"}, f"{dem.shape[1]}×{dem.shape[0]} px resampled to {g.res} m")
    blds = fetch.fetch_buildings(a["bbox"])
    log(aoi_id, "fetch_buildings", {"source": "OpenStreetMap Overpass"}, f"{len(blds):,} building footprints")

    np.savez_compressed(c / "raw.npz", dem=dem,
                        **{f"pre_{k}": pre[k] for k in ("green", "swir", "scl", "rgb_png")},
                        **{f"post{i}_{k}": p[k] for i, p in enumerate(posts) for k in ("green", "swir", "scl", "rgb_png")})
    (c / "index.json").write_text(json.dumps({"pre": {"date": pre["date"], "scenes": pre["scenes"]},
                                              "posts": [{"date": p["date"], "scenes": p["scenes"]} for p in posts]}))
    (c / "buildings.json").write_text(json.dumps(blds))
    return {"pre": pre, "posts": posts, "dem": dem, "buildings": blds}


def load_cache(aoi_id):
    c = CACHE / aoi_id
    z = np.load(c / "raw.npz"); idx = json.loads((c / "index.json").read_text())
    pre = {**idx["pre"], **{k: z[f"pre_{k}"] for k in ("green", "swir", "scl", "rgb_png")}}
    posts = [{**p, **{k: z[f"post{i}_{k}"] for k in ("green", "swir", "scl", "rgb_png")}} for i, p in enumerate(idx["posts"])]
    log(aoi_id, "load_cache", {"path": f"data/cache/{aoi_id}"}, f"{len(posts)} post-storm scenes from cache")
    return {"pre": pre, "posts": posts, "dem": z["dem"], "buildings": json.loads((c / "buildings.json").read_text())}


def main(argv):
    offline = "--offline" in argv
    aois = [a for a in argv if not a.startswith("--")] or list(config.AOIS)
    config.OUT.mkdir(parents=True, exist_ok=True)
    metas, blds = {}, {}
    for aoi_id in aois:
        g = gridmod.make_grid(config.AOIS[aoi_id]["bbox"])
        log(aoi_id, "make_grid", {"epsg": g.epsg, "res_m": g.res}, f"{g.width}×{g.height} px analysis grid")
        raw = load_cache(aoi_id) if offline else download(aoi_id, g)
        metas[aoi_id] = analyze.analyze_aoi(aoi_id, g, raw, "REAL", log, notes=[
            "Sentinel-2 L2A via Element 84 Earth Search; Copernicus DEM GLO-30; OpenStreetMap buildings (ODbL).",
            "Water = MNDWI (Otsu, clamped). Persistence = last post-storm date a pixel was seen wet (lower bound; 5-day revisit + clouds).",
            "Depth = simplified FwDET from a 30 m surface model that includes buildings: indicative only.",
        ])
        blds[aoi_id] = [{"id": f["id"], "use": f["use"], "height": f["height"], "area_m2": f.get("area_m2", 600)} for f in raw["buildings"]]
    # loans are generated over ALL configured areas that have outputs (blind to flood results)
    for aoi_id in config.AOIS:
        if aoi_id not in blds and (CACHE / aoi_id / "buildings.json").exists():
            blds[aoi_id] = [{"id": b["id"], "use": b["use"], "height": b["height"], "area_m2": b.get("area_m2", 600)}
                            for b in json.loads((CACHE / aoi_id / "buildings.json").read_text())]
    from . import gov_data
    gov = gov_data.load_dld()
    if gov:
        (config.OUT / "gov_prices.json").write_text(json.dumps(gov, indent=1))
        log("all", "gov_open_data", {"dataset": "DLD transactions (Data.Dubai)", "files": gov["files"]},
            f"{gov['rows_used']:,} sales used · median AED/m² " + ", ".join(f"{a} {d['all']:,}" for a, d in gov["by_aoi"].items()))
    else:
        log("all", "gov_open_data", {"dataset": "DLD transactions (Data.Dubai)"}, "not provided: put the CSV in data/gov/ to price collateral from DLD")
    loans = loanmod.make_loans(blds, gov=gov)
    loanmod.write(loans)
    log("all", "synthetic_loans", {"n": len(loans), "seed": config.LOAN_SEED}, "placed on real footprints, blind to flood results")
    old = {}
    mf = config.OUT / "manifest.json"
    if mf.exists():
        try:
            old = json.loads(mf.read_text())
        except Exception:
            old = {}
    aoi_list = sorted(set((old.get("aois") or []) if old.get("mode") == "REAL" else []) | set(metas))
    manifest = {"mode": "REAL", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "event_date": config.EVENT_DATE, "aois": aoi_list, "log": LOG}
    mf.write_text(json.dumps(manifest, indent=1))
    print(f"\nDone in {time.time() - T0:.0f}s. Start the app: python3 server.py")


if __name__ == "__main__":
    main(sys.argv[1:])
