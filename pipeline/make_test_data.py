"""Generate clearly-labelled TEST data so the app can be developed and rehearsed before the real
pipeline has been run. It runs the SAME analysis code as the real pipeline on procedurally generated
rasters. The app shows a 'TEST DATA' watermark whenever this data is loaded.

    python3 -m pipeline.make_test_data
"""
from __future__ import annotations
import json
import time
from datetime import date, timedelta, datetime, timezone

import numpy as np
from pyproj import Transformer
from scipy import ndimage

from . import analyze, config, core, grid as gridmod, loans as loanmod

LOG = []; T0 = time.time()


def log(aoi, tool, args, result):
    LOG.append({"t_s": round(time.time() - T0, 1), "aoi": aoi, "tool": tool, "args": args, "result": "[TEST] " + result})


def synth(aoi_id, g, seed):
    rng = np.random.default_rng(seed)
    h, w = g.shape
    yy, xx = np.mgrid[0:h, 0:w].astype("float32")
    noise = ndimage.gaussian_filter(rng.normal(0, 1, (h, w)), 18) * 25
    dem = 6 + 0.004 * xx + 0.003 * yy + noise
    # street grid: slightly lower corridors every ~180 m, some blocked (=ponding)
    streets = ((xx % 18) < 2) | ((yy % 18) < 2)
    dem = dem - streets * 0.35
    for _ in range(14):  # a few real depressions
        cy, cx = rng.integers(40, h - 40), rng.integers(40, w - 40); r = rng.integers(15, 45)
        dem -= 1.4 * np.exp(-(((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * r ** 2)))
    dem = dem.astype("float32")
    filled = core.priority_flood(dem)
    dd = filled - dem + ndimage.gaussian_filter(rng.normal(0, 1, (h, w)), 3) * 0.12

    base = np.stack([200 + noise * 0.6, 180 + noise * 0.5, 150 + noise * 0.4], -1)
    ev = date.fromisoformat(config.EVENT_DATE)

    def scene(level, clouds):
        water = dd > level
        green = np.where(water, 0.09, 0.12).astype("float32") + rng.normal(0, 0.006, (h, w)).astype("float32")
        swir = np.where(water, 0.03, 0.22).astype("float32") + rng.normal(0, 0.01, (h, w)).astype("float32")
        scl = np.full((h, w), 5, "uint8")
        if clouds:
            cm = ndimage.gaussian_filter(rng.random((h, w)), 25) > 0.5 + 0.5 * (1 - clouds) * 0.1
            scl[cm] = 9
        rgb = base.copy()
        rgb[water] = (60, 85, 95)
        rgb = np.clip(rgb + rng.normal(0, 6, rgb.shape), 0, 255).astype("uint8")
        return green, swir, scl, rgb

    g0, s0, c0, r0 = scene(9.0, 0)  # pre: dry
    pre = {"date": "2024-04-11", "scenes": ["TEST-PRE"], "green": g0, "swir": s0, "scl": c0, "rgb_png": r0}
    posts = []
    for k, (d, level, cl) in enumerate([(1, 0.12, 0), (6, 0.35, 0.1), (11, 0.6, 0), (16, 0.9, 0), (26, 1.25, 0.05)]):
        gg, ss, cc, rr = scene(level, cl)
        posts.append({"date": (ev + timedelta(days=d)).isoformat(), "scenes": [f"TEST-POST-{k}"],
                      "green": gg, "swir": ss, "scl": cc, "rgb_png": rr})

    # buildings: rectangles inside street blocks
    to_ll = Transformer.from_crs(g.epsg, 4326, always_xy=True)
    t = g.transform; blds = []
    uses = ["warehouse", "industrial", "commercial", "residential", "office", "retail", "unknown"]
    for by in range(1, h // 18 - 1):
        for bx in range(1, w // 18 - 1):
            if rng.random() < 0.25:
                continue
            for sub in range(rng.integers(1, 4)):
                x0 = bx * 18 + 3 + rng.integers(0, 6); y0 = by * 18 + 3 + rng.integers(0, 6)
                bw = rng.integers(3, 8); bh = rng.integers(3, 8)
                pts = [(x0, y0), (x0 + bw, y0), (x0 + bw, y0 + bh), (x0, y0 + bh), (x0, y0)]
                ring = [list(map(lambda v: round(v, 6), to_ll.transform(t.c + px * t.a, t.f + py * t.e))) for px, py in pts]
                use = uses[int(rng.integers(0, len(uses)))]
                blds.append({"id": f"test-{aoi_id}-{len(blds)}", "use": use, "building_tag": use, "name": "",
                             "height": float(rng.choice([6, 9, 12, 18, 24, 36])), "height_src": "TEST", "area_m2": int(bw * bh * 100),
                             "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return {"pre": pre, "posts": posts, "dem": dem, "buildings": blds}


def main():
    config.OUT.mkdir(parents=True, exist_ok=True)
    blds = {}
    for i, aoi_id in enumerate(config.AOIS):
        g = gridmod.make_grid(config.AOIS[aoi_id]["bbox"])
        raw = synth(aoi_id, g, 100 + i)
        analyze.analyze_aoi(aoi_id, g, raw, "TEST", log, notes=["TEST DATA: procedurally generated. Not satellite observations. Run python3 -m pipeline.run_all for real data."])
        blds[aoi_id] = [{"id": b["id"], "use": b["use"], "height": b["height"], "area_m2": b["area_m2"]} for b in raw["buildings"]]
    from . import gov_data
    gov = gov_data.load_dld()
    if gov:
        (config.OUT / "gov_prices.json").write_text(json.dumps(gov, indent=1))
    elif (config.OUT / "gov_prices.json").exists():
        (config.OUT / "gov_prices.json").unlink()
    loans = loanmod.make_loans(blds, gov=gov, label="SYNTHETIC LOAN ON TEST BUILDING")
    loanmod.write(loans)
    (config.OUT / "manifest.json").write_text(json.dumps({
        "mode": "TEST", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event_date": config.EVENT_DATE, "aois": list(config.AOIS), "log": LOG}, indent=1))
    print("TEST data written to", config.OUT)


if __name__ == "__main__":
    main()
