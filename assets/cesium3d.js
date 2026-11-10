/* CLIMAX · CesiumJS + Cesium ion renderer (cinematic 3D).
   - ion: Bing Maps aerial imagery (asset 2) + Cesium OSM Buildings for city context outside the analysed areas.
   - Ours: Sentinel-2 passes, water / persistence / depth / forecast layers (lon/lat-aligned PNGs from the pipeline),
     and the analysed OSM footprints as one per-instance-coloured Primitive per area (fast recolouring).
   - Swipe uses Cesium's native imagery splitDirection.
   If ion is unreachable the globe still shows our own Sentinel-2 imagery, so nothing breaks offline. */
'use strict';
(function () {
  const C = window.Cesium;
  const CS = { viewer: null, layers: {}, prims: {}, feats: {}, colors: {}, entities: [], tween: new Map(), ionOk: false, onPick: null };
  const col = (hex, a = 1) => C.Color.fromCssColorString(hex).withAlpha(a);

  CS.init = async function (container, token, aois) {
    if (token) C.Ion.defaultAccessToken = token;
    const credit = document.createElement('div'); credit.className = 'cs-credits';
    document.getElementById('app').appendChild(credit);
    const v = new C.Viewer(container, {
      baseLayer: false, animation: false, timeline: false, baseLayerPicker: false, geocoder: false, homeButton: false,
      sceneModePicker: false, navigationHelpButton: false, fullscreenButton: false, infoBox: false, selectionIndicator: false,
      creditContainer: credit, msaaSamples: 4, terrainProvider: new C.EllipsoidTerrainProvider(),
    });
    CS.viewer = v;
    const sc = v.scene;
    sc.globe.baseColor = col('#071a14');
    sc.backgroundColor = col('#04100d');
    sc.globe.showGroundAtmosphere = true; sc.skyAtmosphere.show = true; sc.fog.enabled = true;
    sc.globe.depthTestAgainstTerrain = false;
    sc.highDynamicRange = false;
    v.clock.currentTime = C.JulianDate.fromIso8601('2024-04-17T09:30:00Z');   // ~13:30 Dubai: soft afternoon light
    v.clock.shouldAnimate = false;
    sc.screenSpaceCameraController.minimumZoomDistance = 120;

    if (token) {
      try {
        const base = C.ImageryLayer.fromProviderAsync(C.IonImageryProvider.fromAssetId(2));
        base.brightness = 0.62; base.saturation = 0.55; base.contrast = 1.1; base.gamma = 1.05;
        v.imageryLayers.add(base, 0);
        base.readyEvent.addEventListener(() => { CS.ionOk = true; });
        base.errorEvent.addEventListener(() => { CS.ionOk = false; });
      } catch (e) { console.warn('ion imagery unavailable', e); }
      // city context: Cesium OSM Buildings, hidden inside our analysed areas (we draw those ourselves, coloured by data)
      C.createOsmBuildingsAsync().then(ts => {
        const inside = aois.map(r => `(\${feature['cesium#longitude']} > ${r[0]} && \${feature['cesium#longitude']} < ${r[2]} && \${feature['cesium#latitude']} > ${r[1]} && \${feature['cesium#latitude']} < ${r[3]})`).join(' || ');
        ts.style = new C.Cesium3DTileStyle({ color: "color('#36504a', 0.92)", show: inside ? `!(${inside})` : 'true' });
        sc.primitives.add(ts); CS.osm = ts;
      }).catch(e => console.warn('OSM Buildings unavailable', e));
    }
    const h = new C.ScreenSpaceEventHandler(sc.canvas);
    h.setInputAction(m => {
      const p = sc.pick(m.position);
      if (p && CS.onPick) CS.onPick(p.id && p.id.id ? p.id.id : p.id);
    }, C.ScreenSpaceEventType.LEFT_CLICK);
    sc.preRender.addEventListener(tick);
    return CS;
  };

  /* ---------- imagery layers with alpha tweening ---------- */
  function tick() {
    const now = performance.now();
    for (const [layer, t] of CS.tween) {
      const p = Math.min(1, (now - t.t0) / t.dur);
      layer.alpha = t.from + (t.to - t.from) * p;
      if (p >= 1) { CS.tween.delete(layer); if (t.to === 0) layer.show = false; }
    }
    if (CS.tween.size) CS.viewer.scene.requestRender();
  }
  CS.fade = function (layer, to, dur = 600) {
    if (!layer) return;
    const cur = CS.tween.get(layer);
    const target = cur ? cur.to : (layer.show ? layer.alpha : 0);
    if (Math.abs(target - to) < 1e-3) return;
    if (to > 0) layer.show = true;
    CS.tween.set(layer, { from: layer.show ? layer.alpha : 0, to, t0: performance.now(), dur });
  };

  CS.addArea = async function (a, md, fc, colorOf) {
    const v = CS.viewer, r = md.rect, rect = C.Rectangle.fromDegrees(r[0], r[1], r[2], r[3]);
    const L = CS.layers[a] = {};
    const add = async (key, file) => {
      const prov = await C.SingleTileImageryProvider.fromUrl(md.base + 'll/' + file, { rectangle: rect });
      const layer = v.imageryLayers.addImageryProvider(prov);
      layer.alpha = 0; layer.show = false; L[key] = layer;
    };
    await add('pre', 'rgb_pre.jpg');
    for (const d of md.dates) if (d.rgb) await add('post' + d.index, d.rgb);
    await add('persist', 'persistence.png'); await add('depth', 'depth.png'); await add('pred', 'pred.png');
    for (const d of md.dates) await add('water' + d.index, d.water);

    // buildings: one Primitive, per-instance colour
    const inst = []; CS.feats[a] = fc.features;
    for (const f of fc.features) {
      const ring = f.geometry.coordinates[0]; const flat = [];
      for (let i = 0; i < ring.length - 1; i++) flat.push(ring[i][0], ring[i][1]);
      if (flat.length < 6) continue;
      inst.push(new C.GeometryInstance({
        id: f.properties.id,
        geometry: new C.PolygonGeometry({ polygonHierarchy: new C.PolygonHierarchy(C.Cartesian3.fromDegreesArray(flat)),
          height: 0, extrudedHeight: Math.max(3, f.properties.height || 8), vertexFormat: C.PerInstanceColorAppearance.VERTEX_FORMAT }),
        attributes: { color: C.ColorGeometryInstanceAttribute.fromColor(col(colorOf(f))), show: new C.ShowGeometryInstanceAttribute(false) },
      }));
    }
    const prim = new C.Primitive({ geometryInstances: inst, appearance: new C.PerInstanceColorAppearance({ closed: true, translucent: false }),
      asynchronous: true, releaseGeometryInstances: true, allowPicking: true });
    v.scene.primitives.add(prim); CS.prims[a] = prim; CS.colors[a] = {};
  };

  /* ---------- per-frame state ---------- */
  CS.render = function (st) {
    // st: {aoi, aois, rgbIndex, waterIndex, persist, depth, swipe, colorOf, visibleArea}
    for (const a of st.aois) {
      const L = CS.layers[a]; if (!L) continue; const act = a === st.aoi;
      CS.fade(L.pre, act ? 1 : 0);
      for (const k of Object.keys(L)) {
        if (k.startsWith('post')) CS.fade(L[k], act && st.rgbIndex === +k.slice(4) ? 1 : 0);
        if (k.startsWith('water')) CS.fade(L[k], act && st.waterIndex === +k.slice(5) ? 0.9 : 0, 450);
      }
      CS.fade(L.persist, act && st.persist ? 0.92 : 0);
      CS.fade(L.depth, act && st.depth ? 0.9 : 0);
      CS.fade(L.pred, act && st.swipe ? 0.9 : 0);
      L.pred.splitDirection = st.swipe ? C.SplitDirection.LEFT : C.SplitDirection.NONE;
      L.persist.splitDirection = st.swipe ? C.SplitDirection.RIGHT : C.SplitDirection.NONE;
      CS.recolor(a, act, st.colorOf);
    }
  };

  CS.recolor = function (a, show, colorOf) {
    const prim = CS.prims[a]; if (!prim) return;
    if (!prim.ready) { prim.readyPromise ? prim.readyPromise.then(() => CS.recolor(a, show, colorOf)) : setTimeout(() => CS.recolor(a, show, colorOf), 300); return; }
    const cache = CS.colors[a];
    for (const f of CS.feats[a]) {
      const at = prim.getGeometryInstanceAttributes(f.properties.id); if (!at) continue;
      at.show = C.ShowGeometryInstanceAttribute.toValue(show);
      if (!show) continue;
      const hex = colorOf(f);
      if (cache[f.properties.id] !== hex) { at.color = C.ColorGeometryInstanceAttribute.toValue(col(hex)); cache[f.properties.id] = hex; }
    }
  };

  CS.split = function (pos) { CS.viewer.scene.splitPosition = pos / 100; };

  /* ---------- loan markers ---------- */
  const CH = { DUAL: '#ff4d6d', OPERATIONS: '#ff8c42', COLLATERAL: '#4dabf7', HL: '#7cffcb' };
  CS.markers = function (items) {
    const v = CS.viewer;
    CS.entities.forEach(e => v.entities.remove(e)); CS.entities = [];
    const t0 = performance.now();
    for (const m of items) {
      const c = col(CH[m.kind] || '#ffffff');
      const e = v.entities.add({
        id: 'loan:' + m.id, position: C.Cartesian3.fromDegrees(m.lon, m.lat, (m.h || 10) + 6),
        point: { pixelSize: new C.CallbackProperty(() => 9 + 4 * (0.5 + 0.5 * Math.sin((performance.now() - t0) / 260)), false),
          color: c, outlineColor: C.Color.WHITE, outlineWidth: 2, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        label: m.label ? { text: m.label, font: '600 12px "JetBrains Mono", monospace', fillColor: C.Color.WHITE, showBackground: true,
          backgroundColor: col('#04100d', 0.85), backgroundPadding: new C.Cartesian2(6, 4), pixelOffset: new C.Cartesian2(14, -14),
          horizontalOrigin: C.HorizontalOrigin.LEFT, disableDepthTestDistance: Number.POSITIVE_INFINITY } : undefined,
        polyline: { positions: C.Cartesian3.fromDegreesArrayHeights([m.lon, m.lat, 0, m.lon, m.lat, (m.h || 10) + 6]), width: 1.5, material: c.withAlpha(0.8) },
      });
      CS.entities.push(e);
    }
  };

  /* ---------- camera ---------- */
  CS.flyRect = function (r, opt = {}) {
    const lon = (r[0] + r[2]) / 2, lat = (r[1] + r[3]) / 2;
    const w = C.Cartesian3.distance(C.Cartesian3.fromDegrees(r[0], lat), C.Cartesian3.fromDegrees(r[2], lat));
    const range = (opt.range || 1.05) * w;
    CS.viewer.camera.flyToBoundingSphere(new C.BoundingSphere(C.Cartesian3.fromDegrees(lon + (opt.dx || 0) * (r[2] - r[0]), lat, 0), 10), {
      offset: new C.HeadingPitchRange(C.Math.toRadians(opt.heading ?? -18), C.Math.toRadians(opt.pitch ?? -36), range),
      duration: (opt.duration ?? 2600) / 1000 });
  };
  CS.flyPoint = function (lon, lat, opt = {}) {
    CS.viewer.camera.flyToBoundingSphere(new C.BoundingSphere(C.Cartesian3.fromDegrees(lon, lat, 0), 10), {
      offset: new C.HeadingPitchRange(C.Math.toRadians(opt.heading ?? -25), C.Math.toRadians(opt.pitch ?? -32), opt.range || 650),
      duration: (opt.duration ?? 1800) / 1000 });
  };
  CS.status = () => ({ ion: CS.ionOk, osm: !!CS.osm });
  window.CS3D = CS;
})();
