"""Runs the REAL download + analysis code path (pipeline.run_all.download) against local fake GeoTIFFs and
a mocked STAC search / Overpass response. Proves the network code reprojects, mosaics, applies
scale/offset and parses buildings correctly - without internet.   python3 -m unittest tests.test_pipeline_offline -v
"""
import io, json, sys, tempfile, unittest, pathlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

import numpy as np
import rasterio
from rasterio.transform import from_origin

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import config, fetch, grid as gridmod, analyze, run_all  # noqa: E402


def write_tif(path, arr, crs="EPSG:32640", transform=None, dtype=None):
    arr = np.asarray(arr)
    bands = arr if arr.ndim == 3 else arr[None]
    with rasterio.open(path, "w", driver="GTiff", height=bands.shape[1], width=bands.shape[2], count=bands.shape[0],
                       dtype=dtype or bands.dtype, crs=crs, transform=transform, nodata=0) as dst:
        dst.write(bands)


class OfflinePipeline(unittest.TestCase):
    def test_download_and_analyze(self):
        aoi = "alquoz"; bbox = config.AOIS[aoi]["bbox"]
        g = gridmod.make_grid(bbox)
        tmp = pathlib.Path(tempfile.mkdtemp())
        # source rasters at 20 m on a slightly larger extent (forces real reprojection/resampling)
        x0, y1 = g.transform.c - 200, g.transform.f + 200
        W, H = g.width // 2 + 30, g.height // 2 + 30
        T = from_origin(x0, y1, 20, 20)
        yy, xx = np.mgrid[0:H, 0:W]
        lake = (yy - H / 2) ** 2 + (xx - W / 2) ** 2 < (H / 6) ** 2

        def scene(date, wet):
            d = tmp / date; d.mkdir()
            # DN with Earth Search offset convention: reflectance = DN*1e-4 - 0.1
            green = np.where(wet, 1900, 2200).astype("uint16")
            swir = np.where(wet, 1300, 3200).astype("uint16")
            scl = np.full((H, W), 5, "uint8")
            vis = np.stack([np.where(wet, 60, 200)] * 3).astype("uint8")
            for n, a in (("green", green), ("swir16", swir), ("scl", scl), ("visual", vis)):
                write_tif(d / f"{n}.tif", a, transform=T)
            rb = [{"scale": 0.0001, "offset": -0.1}]
            assets = {n: SimpleNamespace(href=str(d / f"{n}.tif"), extra_fields={"raster:bands": rb}) for n in ("green", "swir16", "scl", "visual")}
            return SimpleNamespace(id=f"S2A_TEST_{date}", assets=assets, datetime=datetime.fromisoformat(date).replace(tzinfo=timezone.utc))

        items = {"2024-04-11": [scene("2024-04-11", np.zeros_like(lake))], "2024-04-17": [scene("2024-04-17", lake)],
                 "2024-04-22": [scene("2024-04-22", lake & (xx < W / 2))]}
        # DEM in geographic coordinates (like Copernicus) -> must be warped to UTM
        dem_arr = (10 + np.random.default_rng(0).random((400, 400))).astype("float32")
        write_tif(tmp / "dem.tif", dem_arr, crs="EPSG:4326", transform=from_origin(55.1, 25.25, 0.0005, 0.0005), dtype="float32")
        lon0, lat0 = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        overpass = {"elements": [{"type": "way", "id": 1, "tags": {"building": "warehouse", "building:levels": "2"},
                                  "geometry": [{"lat": lat0, "lon": lon0}, {"lat": lat0, "lon": lon0 + 0.0006}, {"lat": lat0 + 0.0005, "lon": lon0 + 0.0006},
                                               {"lat": lat0 + 0.0005, "lon": lon0}, {"lat": lat0, "lon": lon0}]},
                                 {"type": "way", "id": 2, "tags": {"building": "yes"}, "geometry": [{"lat": 25.12, "lon": 55.21}] * 3}]}

        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        cache = tmp / "cache"; out = tmp / "out"
        with mock.patch.object(fetch, "search_s2", return_value=items), \
             mock.patch.object(config, "DEM_URL", str(tmp / "dem.tif")), \
             mock.patch.object(run_all, "CACHE", cache), mock.patch.object(config, "OUT", out), \
             mock.patch("urllib.request.urlopen", return_value=Resp(json.dumps(overpass).encode())):
            raw = run_all.download(aoi, g)
            self.assertEqual(raw["pre"]["date"], "2024-04-11")
            self.assertEqual([p["date"] for p in raw["posts"]], ["2024-04-17", "2024-04-22"])
            self.assertAlmostEqual(float(np.nanmedian(raw["pre"]["green"])), 0.12, places=2)   # scale+offset applied
            self.assertEqual(raw["pre"]["green"].shape, g.shape)                                # reprojected to grid
            self.assertEqual(len(raw["buildings"]), 1)                                          # degenerate way dropped
            self.assertAlmostEqual(raw["buildings"][0]["height"], 6.6, places=1)
            meta = analyze.analyze_aoi(aoi, g, raw, "REAL", lambda *a: None)
            # lake ~ pi*(H/6)^2 px at 20 m
            expected = np.pi * (H / 6) ** 2 * 400 / 1e6
            self.assertAlmostEqual(meta["stats"]["flooded_km2"], expected, delta=expected * 0.25)
            self.assertEqual([d["day"] for d in meta["dates"]], [1, 6])
            self.assertTrue((out / aoi / "buildings.geojson").exists())
            cached = run_all.load_cache(aoi)
            self.assertEqual(len(cached["posts"]), 2)


if __name__ == "__main__":
    unittest.main()
