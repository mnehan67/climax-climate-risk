"""Network access: Sentinel-2 L2A (Earth Search STAC), Copernicus DEM (AWS), OSM buildings (Overpass).
All sources are free and keyless. Everything read is cached in data/cache so the demo runs offline.
"""
from __future__ import annotations
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from . import config

GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES",
                GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF,.tiff", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2",
                VSI_CACHE="TRUE")


# ------------------------------------------------------------------ Sentinel-2
def search_s2(bbox, start, end):
    from pystac_client import Client
    client = Client.open(config.STAC_URL)
    search = client.search(collections=[config.S2_COLLECTION], bbox=list(bbox), datetime=f"{start}/{end}",
                           query={"eo:cloud_cover": {"lt": config.MAX_SCENE_CLOUD}}, max_items=500)
    items = list(search.items())
    by_date = defaultdict(list)
    for it in items:
        by_date[it.datetime.strftime("%Y-%m-%d")].append(it)
    return dict(sorted(by_date.items()))


ASSET_KEYS = {"green": ("green", "B03"), "swir": ("swir16", "B11"), "scl": ("scl", "SCL"), "rgb": ("visual", "TCI")}


def _asset(item, kind):
    for k in ASSET_KEYS[kind]:
        if k in item.assets:
            return item.assets[k]
    raise KeyError(f"{item.id} has no {kind} asset ({list(item.assets)})")


def _scale_offset(asset):
    rb = (asset.extra_fields or {}).get("raster:bands") or [{}]
    return float(rb[0].get("scale", 1.0) or 1.0), float(rb[0].get("offset", 0.0) or 0.0)


def _read_on_grid(href, g, bands=1, resampling=Resampling.bilinear):
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(href) as src, WarpedVRT(src, crs=f"EPSG:{g.epsg}", transform=g.transform, width=g.width,
                                                   height=g.height, resampling=resampling, nodata=0) as vrt:
            return vrt.read(bands)


def read_s2_layer(items, g, kind):
    """Mosaic one layer from all items of a date onto the grid (first non-zero wins)."""
    out = None
    for it in items:
        a = _asset(it, kind)
        if kind == "rgb":
            arr = np.moveaxis(_read_on_grid(a.href, g, bands=[1, 2, 3]), 0, -1)
            filled = arr.sum(-1) > 0
        elif kind == "scl":
            arr = _read_on_grid(a.href, g, resampling=Resampling.nearest)
            filled = arr > 0
        else:
            raw = _read_on_grid(a.href, g).astype("float32")
            filled = raw > 0
            scale, offset = _scale_offset(a)
            arr = np.where(filled, raw * scale + offset, np.nan).astype("float32")
        if out is None:
            out = arr.copy(); have = filled.copy()
        else:
            need = filled & ~have
            out[need] = arr[need]; have |= filled
    return out


# ------------------------------------------------------------------ DEM
def read_dem(g):
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(config.DEM_URL) as src, WarpedVRT(src, crs=f"EPSG:{g.epsg}", transform=g.transform,
                                                             width=g.width, height=g.height,
                                                             resampling=Resampling.bilinear) as vrt:
            return vrt.read(1).astype("float32")


# ------------------------------------------------------------------ OSM buildings
DEFAULT_HEIGHT = {"warehouse": 9, "industrial": 9, "hangar": 14, "commercial": 14, "retail": 10, "office": 24,
                  "apartments": 24, "residential": 14, "house": 7, "villa": 7, "detached": 7, "terrace": 7,
                  "hotel": 30, "school": 10, "hospital": 18, "mosque": 12, "garage": 4, "roof": 5}

USE_GROUP = {"warehouse": "warehouse", "industrial": "industrial", "hangar": "industrial", "factory": "industrial",
             "manufacture": "industrial", "commercial": "commercial", "retail": "retail", "supermarket": "retail",
             "office": "office", "apartments": "residential", "residential": "residential", "house": "residential",
             "villa": "residential", "detached": "residential", "terrace": "residential", "dormitory": "residential",
             "hotel": "hospitality", "school": "public", "hospital": "public", "mosque": "public",
             "university": "public", "garage": "other", "roof": "other"}


def _parse_height(tags):
    try:
        if "height" in tags:
            return float(str(tags["height"]).split()[0].replace("m", "")), "osm height"
    except ValueError:
        pass
    try:
        if "building:levels" in tags:
            return float(tags["building:levels"]) * 3.3, "osm levels x 3.3 m"
    except ValueError:
        pass
    return float(DEFAULT_HEIGHT.get(tags.get("building", ""), 8)), "default by type (estimate)"


def fetch_buildings(bbox, min_area_m2=30):
    s, w, n, e = bbox[1], bbox[0], bbox[3], bbox[2]
    q = f'[out:json][timeout:180];(way["building"]({s},{w},{n},{e}););out tags geom;'
    last = None
    for url in config.OVERPASS_URLS:
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": "CLIMAX-hackathon-pipeline/2.0"})
            with urllib.request.urlopen(req, timeout=200) as r:
                data = json.loads(r.read())
            break
        except Exception as ex:  # try the next mirror
            last = ex; time.sleep(2)
    else:
        raise RuntimeError(f"All Overpass mirrors failed: {last}")
    out = []
    lat0 = (s + n) / 2
    for el in data.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 4:
            continue
        ring = [[round(p["lon"], 6), round(p["lat"], 6)] for p in geom]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        # rough area check (equirectangular)
        xs = np.array([p[0] for p in ring]) * 111320 * np.cos(np.radians(lat0)); ys = np.array([p[1] for p in ring]) * 110540
        area = 0.5 * abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))
        if area < min_area_m2:
            continue
        tags = el.get("tags", {})
        h, src = _parse_height(tags)
        btype = tags.get("building", "yes")
        out.append({"id": f"osm-w{el['id']}", "use": USE_GROUP.get(btype, "unknown"), "building_tag": btype,
                    "name": tags.get("name:en") or tags.get("name") or "", "height": round(min(max(h, 3), 400), 1),
                    "height_src": src, "area_m2": round(float(area)),
                    "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return out
