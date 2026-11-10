"""Analysis grid (UTM 40N, 10 m) + writing the app-ready outputs for one area of interest."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_bounds, from_origin
from rasterio.warp import reproject, Resampling
from shapely.geometry import Polygon, mapping, shape
import shapely

from . import config, core


@dataclass
class Grid:
    epsg: int
    transform: object
    width: int
    height: int
    res: float

    @property
    def shape(self):
        return (self.height, self.width)


def make_grid(bbox, res=config.RES_M, epsg=config.UTM_EPSG) -> Grid:
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = to_utm.transform([bbox[0], bbox[2], bbox[0], bbox[2]], [bbox[1], bbox[1], bbox[3], bbox[3]])
    x0, x1 = min(xs), max(xs); y0, y1 = min(ys), max(ys)
    w = int(round((x1 - x0) / res)); h = int(round((y1 - y0) / res))
    return Grid(epsg, from_origin(x0, y1, res, res), w, h, res)


def corners_lonlat(g: Grid):
    """Four corners TL, TR, BR, BL in lon/lat (what MapLibre image sources need)."""
    t = g.transform
    pts = [(t.c, t.f), (t.c + g.width * t.a, t.f), (t.c + g.width * t.a, t.f + g.height * t.e), (t.c, t.f + g.height * t.e)]
    to_ll = Transformer.from_crs(g.epsg, 4326, always_xy=True)
    return [[round(x, 6), round(y, 6)] for x, y in (to_ll.transform(px, py) for px, py in pts)]


def ring_labels(g: Grid, buildings_ll, ring_m=config.BUILDING_RING_M):
    """Rasterise a ring (footprint buffer minus footprint) for each building; value = index+1."""
    tr = Transformer.from_crs(4326, g.epsg, always_xy=True)
    to_utm = lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1]))
    shapes = []
    for i, b in enumerate(buildings_ll):
        poly = shapely.transform(shape(b["geometry"]), to_utm)
        if poly.is_empty or not poly.is_valid:
            poly = poly.buffer(0)
            if poly.is_empty:
                continue
        ring = poly.buffer(ring_m).difference(poly)
        if not ring.is_empty:
            shapes.append((mapping(ring), i + 1))
    if not shapes:
        return np.zeros(g.shape, "int32")
    return rasterize(shapes, out_shape=g.shape, transform=g.transform, fill=0, dtype="int32")


def ll_target(g: Grid):
    """A lon/lat-aligned grid covering the UTM grid (for CesiumJS imagery layers, which need lat/lon rectangles)."""
    co = corners_lonlat(g)
    w, e = min(c[0] for c in co), max(c[0] for c in co)
    s, n = min(c[1] for c in co), max(c[1] for c in co)
    W = int(g.width * 1.02); H = int(g.height * 1.02)
    return [w, s, e, n], from_bounds(w, s, e, n, W, H), W, H


def to_lonlat(arr, g: Grid, nearest: bool):
    rect, t, W, H = ll_target(g)
    bands = arr[..., None] if arr.ndim == 2 else arr
    out = np.zeros((H, W, bands.shape[2]), dtype=bands.dtype)
    for b in range(bands.shape[2]):
        reproject(bands[..., b], out[..., b], src_transform=g.transform, src_crs=f"EPSG:{g.epsg}", dst_transform=t,
                  dst_crs="EPSG:4326", resampling=Resampling.nearest if nearest else Resampling.bilinear)
    return out


def save_png(arr, path: Path):
    Image.fromarray(arr).save(path, optimize=True)


def save_jpg(rgb, path: Path):
    Image.fromarray(rgb).save(path, quality=86)


PERSIST_STOPS = [(0, (255, 214, 102, 210)), (3, (255, 140, 66, 220)), (8, (240, 62, 92, 230)),
                 (15, (184, 50, 200, 235)), (30, (120, 40, 220, 240))]
DEPTH_STOPS = [(0, (120, 220, 255, 120)), (0.5, (40, 160, 255, 190)), (1.2, (20, 90, 230, 220)), (2.5, (40, 20, 160, 240))]


def export_aoi(aoi_id: str, g: Grid, *, rgb_pre, rgb_posts, pre_valid, post_dates, wet_stack, valid_stack,
               thresholds, scene_ids, pre_meta, persist, depth, pred, pred_report, buildings_ll, metrics,
               dem_stats, mode: str, notes: list[str]):
    aoi = config.AOIS[aoi_id]
    d = config.OUT / aoi_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "ll").mkdir(exist_ok=True)
    for old in list(d.glob("*.*")) + list((d / "ll").glob("*.*")):
        old.unlink()

    def png(arr, name):   # UTM-aligned (MapLibre quad) + lon/lat-aligned copy (CesiumJS imagery layer)
        save_png(arr, d / name); save_png(to_lonlat(arr, g, nearest=True), d / "ll" / name)

    def jpg(arr, name):
        save_jpg(arr, d / name); save_jpg(to_lonlat(arr, g, nearest=False), d / "ll" / name)

    jpg(rgb_pre, "rgb_pre.jpg")
    dates_out = []
    for k, (date, day) in enumerate(post_dates):
        wet_new = wet_stack[k] & persist["flooded"]
        png(core.rgba_mask(wet_new), f"water_{k:02d}.png")
        rgb_file = None
        if rgb_posts[k] is not None:
            rgb_file = f"rgb_post_{k:02d}.jpg"; jpg(rgb_posts[k], rgb_file)
        dates_out.append({"index": k, "date": date, "day": int(day), "water": f"water_{k:02d}.png", "rgb": rgb_file,
                          "valid_frac": round(float(valid_stack[k].mean()), 3),
                          "wet_km2": round(float(wet_new.sum()) * g.res ** 2 / 1e6, 3),
                          "mndwi_threshold": round(float(thresholds[k]), 3), "scenes": scene_ids[k]})
    png(core.rgba_ramp(persist["last_wet_day"], persist["flooded"], PERSIST_STOPS), "persistence.png")
    png(core.rgba_ramp(depth, persist["flooded"] & (depth > 0), DEPTH_STOPS), "depth.png")
    png(core.rgba_mask(pred, color=(255, 92, 205), alpha=150), "pred.png")

    feats = []
    for i, (b, m) in enumerate(zip(buildings_ll, metrics)):
        props = {"id": b["id"], "use": b["use"], "name": b.get("name") or "", "height": b["height"],
                 "height_src": b["height_src"], "area_m2": b.get("area_m2"), **m}
        feats.append({"type": "Feature", "id": i, "properties": props, "geometry": b["geometry"]})
    (d / "buildings.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))

    flooded = persist["flooded"]
    px_km2 = g.res ** 2 / 1e6
    hist_days = {}
    for day in sorted({x[1] for x in post_dates}):
        hist_days[int(day)] = round(float((flooded & (persist["last_wet_day"] >= day)).sum()) * px_km2, 3)
    nb = len(metrics); nf = sum(m["flooded"] for m in metrics)
    meta = {
        "aoi": aoi_id, "name": aoi["name"], "short": aoi["short"], "why": aoi["why"], "bbox": aoi["bbox"],
        "corners": corners_lonlat(g), "rect": [round(x, 6) for x in ll_target(g)[0]], "grid": {"w": g.width, "h": g.height, "res_m": g.res, "epsg": g.epsg},
        "mode": mode, "event_date": config.EVENT_DATE, "pre": pre_meta, "dates": dates_out,
        "stats": {
            "aoi_km2": round(g.width * g.height * px_km2, 2),
            "flooded_km2": round(float(flooded.sum()) * px_km2, 3),
            "still_wet_at_last_obs_km2": round(float(persist["censored"].sum()) * px_km2, 3),
            "area_wet_on_or_after_day_km2": hist_days,
            "buildings": nb, "buildings_flooded": nf,
            "buildings_flooded_7d": sum(m["days"] >= 7 for m in metrics),
            "median_depth_m": round(float(np.median(depth[flooded & (depth > 0)])) if (flooded & (depth > 0)).any() else 0.0, 2),
            "dem": dem_stats,
        },
        "validation": pred_report,
        "notes": notes,
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta
