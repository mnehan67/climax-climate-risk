# CLIMAX · Satellite / 3D map fix (November 2026)

This is a drop-in fix for the existing GitHub repository `mnehan67/climax-climate-risk`.

## What was wrong

- The previous MapLibre map was a flat green background with only small, synthetic beige image overlays; it had no city or UAE aerial basemap.
- The Cesium view previously loaded background imagery only when a Cesium ion token was configured. Without a token it rendered the isolated synthetic geometry.
- The ZIP bundled TEST data, while the reference screenshot showed an earlier REAL run. An audit JSON without the corresponding georeferenced raster/footprint outputs cannot recreate the original real satellite split view.

## Fix

- Added a real UAE aerial basemap, using browser-requested World Imagery tiles (attributed to Esri and imagery partners).
- Added real OSM 3D building context using OpenFreeMap tiles in the normal MapLibre map. OSM height coverage is imperfect.
- Kept the full UAE visible when zoomed out: use the **UAE ↗** button. Areas default to DXB to match the desired reference framing.
- Disabled **synthetic beige RGB and fake building extrusions** when displaying the TEST demo over the real aerial basemap.
- Updated the token-free Cesium 3D globe to use the aerial basemap rather than a blank background. Cesium OSM Buildings still needs your own ion token.
- Preserved all existing API endpoints, loan calculations, sliders, audit export, and story controls.

**This does NOT upgrade TEST hazard maps to measured real floods.** Simulated water masks and synthetic loan results remain, with explicit warnings. For the original measured satellite images and matching flood boundaries, recover and upload the original `data/generated/` from the earlier REAL pipeline run, or generate again if it is not saved. Do not substitute `evidence/REAL_run_audit_REFERENCE.json` for raster files.

## Windows — update existing GitHub project (do not rerun pipeline)

1. Download `CLIMAX_Satellite_3D_PATCH.zip` and **Extract All**.
2. Open that extracted directory. Copy `index.html`, `README.md`, `assets` and `MAP_FIX_DEPLOY.md` into your existing Git project `C:\Users\muham\Downloads\CLIMAX_GitHub_Ready\CLIMAX_GitHub_Ready`. Choose **Replace files** when prompted. (The patch `assets/` directory only contains modified files; it does not delete your other assets.)
3. In your Git project folder, click the File Explorer address bar, type `cmd`, press Enter, and paste:

```cmd
git add index.html README.md assets/app.js assets/cesium3d.js assets/style.css MAP_FIX_DEPLOY.md
git commit -m "Restore UAE aerial imagery and 3D building map"
git push origin main
```

4. Render will normally redeploy after GitHub receives the commit. Open the Render website and press **Ctrl + Shift + R** for a hard refresh.
5. Click **UAE ↗** for the national aerial view, or pick an area. You need browser internet access to Esri imagery and OpenFreeMap 3D tiles.

## What is verified

- `node --check assets/app.js` and `node --check assets/cesium3d.js`: PASS.
- `python -m unittest discover -s tests -p 'test_*.py'`: 23 PASS.
- `GET /api/health`: returned success in a local HTTP check.
- Full remote tile rendering: **not verified** in this workspace, due to network access restrictions; validate on your Render deployment.

## External services and attribution

- Aerial map: World Imagery tiles © Esri, Maxar, Earthstar Geographics and the GIS User Community. Terms: https://www.esri.com/en-us/legal/terms/web-site-service
- 3D OSM buildings: OpenFreeMap tiles, © OpenStreetMap contributors (ODbL). Website: https://openfreemap.org/

Satellite context imagery is not storm-date evidence.
