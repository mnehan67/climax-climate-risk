"""Pure-numpy algorithms used by the CLIMAX pipeline. No network, fully unit-tested.

Methods (all citable):
- MNDWI water index ............ Xu (2006), Int. J. Remote Sensing 27(14).
- Otsu thresholding ............ Otsu (1979), IEEE SMC.
- Priority-Flood depression fill  Barnes, Lehman & Mulla (2014), Computers & Geosciences.
- Flood depth from extent + DEM  FwDET, Cohen et al. (2018), JAWRA - simplified (per-patch boundary median).
- Depth-damage curve ........... JRC global depth-damage functions, Huizinga, de Moel & Szewczyk (2017).
"""
from __future__ import annotations
import heapq
import numpy as np
from scipy import ndimage


# ---------------------------------------------------------------- water detection
def mndwi(green: np.ndarray, swir: np.ndarray) -> np.ndarray:
    g = green.astype("float32"); s = swir.astype("float32")
    den = g + s
    out = np.where(den > 0, (g - s) / np.where(den == 0, 1, den), np.nan)
    return out.astype("float32")


def otsu(values: np.ndarray, bins: int = 256) -> float:
    v = values[np.isfinite(values)]
    if v.size < 10:
        return 0.0
    hist, edges = np.histogram(v, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist); w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centers) / np.maximum(w0, 1)
    m1 = (np.sum(hist * centers) - np.cumsum(hist * centers)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(centers[int(np.argmax(between))])


def water_mask(index: np.ndarray, valid: np.ndarray, clamp=(0.0, 0.3), threshold: float | None = None):
    t = otsu(index[valid]) if threshold is None else threshold
    t = float(min(max(t, clamp[0]), clamp[1]))
    return (index > t) & valid, t


def despeckle(mask: np.ndarray, min_px: int) -> np.ndarray:
    lab, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool); keep[1:] = sizes >= min_px
    return keep[lab]


# ---------------------------------------------------------------- persistence
def persistence(pre_water, pre_valid, wet_stack, valid_stack, day_offsets):
    """Per pixel: was it flooded after the storm, and on which day was it LAST seen wet?

    pre_water/pre_valid: (H,W) bool.  wet_stack/valid_stack: (T,H,W) bool.  day_offsets: (T,) days after event.
    Returns dict of arrays. `last_wet_day` is a LOWER BOUND on how long water stayed (satellite revisit gaps).
    """
    wet = np.asarray(wet_stack, bool) & np.asarray(valid_stack, bool)
    newly = wet & ~(pre_water & pre_valid)            # exclude permanent / pre-existing water
    flooded = newly.any(axis=0) & pre_valid
    days = np.asarray(day_offsets, "float32")[:, None, None]
    last = np.where(newly, days, -1).max(axis=0)
    last = np.where(flooded, last, 0).astype("float32")
    still_wet_at_end = np.zeros_like(flooded)
    if wet.shape[0]:
        # wet at the last valid observation for that pixel => duration is right-censored
        vs = np.asarray(valid_stack, bool)
        idx_last_valid = np.where(vs.any(0), vs.shape[0] - 1 - np.argmax(vs[::-1], axis=0), -1)
        rows, cols = np.indices(flooded.shape)
        lv = np.clip(idx_last_valid, 0, None)
        still_wet_at_end = flooded & (idx_last_valid >= 0) & newly[lv, rows, cols]
    return {"flooded": flooded, "last_wet_day": last, "censored": still_wet_at_end}


# ---------------------------------------------------------------- terrain
def priority_flood(dem: np.ndarray) -> np.ndarray:
    """Fill depressions (Barnes et al. 2014). Edges drain. Returns filled surface."""
    h, w = dem.shape
    filled = dem.astype("float64").copy()
    closed = np.zeros((h, w), bool)
    pq: list = []
    for r in range(h):
        for c in (0, w - 1):
            heapq.heappush(pq, (filled[r, c], r, c)); closed[r, c] = True
    for c in range(1, w - 1):
        for r in (0, h - 1):
            heapq.heappush(pq, (filled[r, c], r, c)); closed[r, c] = True
    nbrs = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
    while pq:
        z, r, c = heapq.heappop(pq)
        for dr, dc in nbrs:
            rr, cc = r + dr, c + dc
            if 0 <= rr < h and 0 <= cc < w and not closed[rr, cc]:
                closed[rr, cc] = True
                if filled[rr, cc] < z:
                    filled[rr, cc] = z
                heapq.heappush(pq, (filled[rr, cc], rr, cc))
    return filled.astype("float32")


def tpi(dem: np.ndarray, size_px: int = 51) -> np.ndarray:
    """Topographic position index: elevation minus neighbourhood mean (negative = low spot)."""
    return (dem - ndimage.uniform_filter(dem.astype("float32"), size=size_px)).astype("float32")


def fwdet_depth(flood: np.ndarray, dem: np.ndarray, cap: float = 2.5) -> np.ndarray:
    """Simplified FwDET: each connected flood patch gets a flat water surface equal to the median
    DEM elevation on its boundary; depth = surface - ground, clipped to [0, cap]."""
    depth = np.zeros(dem.shape, "float32")
    lab, n = ndimage.label(flood, structure=np.ones((3, 3)))
    if n == 0:
        return depth
    boundary = flood & ~ndimage.binary_erosion(flood, structure=np.ones((3, 3)))
    # boundary DEM per patch: use the ring of dry pixels just OUTSIDE the patch (more robust)
    outer = ndimage.binary_dilation(flood, structure=np.ones((3, 3))) & ~flood
    lab_outer = ndimage.grey_dilation(lab, size=(3, 3)) * outer
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is None:
            continue
        sl2 = tuple(slice(max(s.start - 1, 0), s.stop + 1) for s in sl)
        ring = dem[sl2][lab_outer[sl2] == i]
        if ring.size == 0:
            ring = dem[sl][boundary[sl] & (lab[sl] == i)]
        if ring.size == 0:
            continue
        surface = float(np.median(ring))
        m = lab[sl] == i
        depth[sl][m] = np.clip(surface - dem[sl][m], 0, cap)
    return depth


# ---------------------------------------------------------------- prediction + validation
def confusion(pred: np.ndarray, obs: np.ndarray, valid: np.ndarray):
    p = pred & valid; o = obs & valid
    tp = int((p & o).sum()); fp = int((p & ~o).sum()); fn = int((~p & o).sum())
    tn = int((~p & ~o & valid).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    iou = tp / (tp + fp + fn) if tp + fp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(f1, 3), "iou": round(iou, 3)}


def calibrate_predictor(dep_depth, tpi_map, obs, valid, calib_cols):
    """Grid-search a 2-parameter terrain-only flood predictor on the calibration half (columns < split),
    then report on the untouched holdout half. Prediction = (depression depth >= a) OR (TPI <= -b)."""
    h, w = obs.shape
    cal = np.zeros((h, w), bool); cal[:, :calib_cols] = True
    hold = ~cal
    best = None
    for a in (0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 99):
        for b in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 99):
            if a == 99 and b == 99:
                continue
            pred = (dep_depth >= a) | (tpi_map <= -b)
            m = confusion(pred, obs, valid & cal)
            if best is None or m["f1"] > best[0]["f1"]:
                best = (m, a, b)
    m_cal, a, b = best
    pred = (dep_depth >= a) | (tpi_map <= -b)
    m_hold = confusion(pred, obs, valid & hold)
    # naive baseline: random map with the same flooded share as the prediction (expected IoU)
    rng = np.random.default_rng(0)
    share = float(pred[valid & hold].mean()) if (valid & hold).any() else 0.0
    rand = rng.random(obs.shape) < share
    m_rand = confusion(rand, obs, valid & hold)
    return pred, {"params": {"depression_depth_m": a if a != 99 else None, "tpi_below_m": b if b != 99 else None},
                  "calibration": m_cal, "holdout": m_hold, "random_baseline_holdout": m_rand,
                  "split": "west half calibrates, east half is held out (spatial holdout)"}


# ---------------------------------------------------------------- damage + buildings
# JRC global depth-damage function (Asia, residential), digitised approximately from Huizinga et al. 2017.
# Replace with the exact JRC table / a UAE-specific curve before any real use.
JRC_DEPTH = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0])
JRC_DAMAGE = np.array([0.0, 0.33, 0.49, 0.62, 0.72, 0.87, 0.93, 0.98, 1.0])


def damage_fraction(depth_m):
    return np.interp(np.asarray(depth_m, float), JRC_DEPTH, JRC_DAMAGE)


def building_metrics(ring_labels: np.ndarray, n_buildings: int, flooded, last_wet_day, depth, pred,
                     min_wet_frac: float = 0.10):
    """Aggregate pixel layers over each building's surrounding ring (label i -> building index i-1)."""
    lab = ring_labels.ravel(); idx = np.arange(1, n_buildings + 1)
    px = np.bincount(lab, minlength=n_buildings + 1)[1:]
    fl = flooded.ravel()
    wet = np.bincount(lab, weights=fl, minlength=n_buildings + 1)[1:]
    pr = np.bincount(lab, weights=pred.ravel(), minlength=n_buildings + 1)[1:]
    days = ndimage.maximum(np.where(flooded, last_wet_day, 0).ravel(), lab, idx) if n_buildings else []
    dep = ndimage.maximum(np.where(flooded, depth, 0).ravel(), lab, idx) if n_buildings else []
    out = []
    for i in range(n_buildings):
        frac = float(wet[i] / px[i]) if px[i] else 0.0
        flooded_b = frac >= min_wet_frac
        out.append({"ring_px": int(px[i]), "wet_frac": round(frac, 3), "flooded": bool(flooded_b),
                    "days": int(days[i]) if flooded_b else 0,
                    "depth_m": round(float(dep[i]), 2) if flooded_b else 0.0,
                    "pred_frac": round(float(pr[i] / px[i]) if px[i] else 0.0, 3)})
    return out


# ---------------------------------------------------------------- rendering helpers
def rgba_mask(mask, color=(0, 229, 255), alpha=170):
    h, w = mask.shape
    img = np.zeros((h, w, 4), "uint8")
    img[mask] = (*color, alpha)
    return img


def rgba_ramp(values, mask, stops):
    """stops: list of (value, (r,g,b,a)). Linear interpolation per channel."""
    h, w = values.shape
    img = np.zeros((h, w, 4), "uint8")
    xs = np.array([s[0] for s in stops], float)
    for ch in range(4):
        ys = np.array([s[1][ch] for s in stops], float)
        img[..., ch] = np.where(mask, np.interp(values, xs, ys), 0).astype("uint8")
    return img


def stretch_rgb(rgb, lo=2, hi=98):
    out = np.zeros_like(rgb, dtype="uint8")
    for c in range(3):
        band = rgb[..., c].astype("float32")
        v = band[band > 0]
        if v.size == 0:
            continue
        a, b = np.percentile(v, lo), np.percentile(v, hi)
        out[..., c] = np.clip((band - a) / max(b - a, 1e-6) * 255, 0, 255).astype("uint8")
    return out
