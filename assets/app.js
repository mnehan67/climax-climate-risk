/* CLIMAX v2 — satellite-measured flood persistence → credit risk.
   Every number on screen comes from /api (pipeline outputs + engine). Loans are synthetic and labelled.
   When the pipeline has not been run, TEST data is loaded and the UI says so everywhere. */
'use strict';
const $ = id => document.getElementById(id), $$ = s => [...document.querySelectorAll(s)];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const aed = x => { const n = +x || 0, a = Math.abs(n); return a >= 1e9 ? 'AED ' + (n / 1e9).toFixed(2) + 'B' : a >= 1e6 ? 'AED ' + (n / 1e6).toFixed(2) + 'M' : a >= 1e3 ? 'AED ' + (n / 1e3).toFixed(0) + 'K' : 'AED ' + Math.round(n) };
const fmtDate = d => new Date(d + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
async function api(path, opt) { const r = await fetch(path, { cache: 'no-store', ...opt }); const j = await r.json(); if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status); return j; }
function toast(t, ms = 3500) { const n = $('toast'); n.textContent = t; n.classList.remove('hidden'); clearTimeout(toast.t); toast.t = setTimeout(() => n.classList.add('hidden'), ms); }

const S = {
  cfg: null, log: [], meta: {}, bld: {}, bIndex: {}, stress: null, aoi: null, k: -1,
  layers: { water: true, persist: false, depth: false, swipe: false, loans: true }, loansOn: false,
  params: { beta: 0.10, persist_mult: 1.0, depth_mult: 1.0 }, scenario: false,
  hlB: new Set(), hlL: new Set(), markers: [], mapB: null, swipePos: 50, story: false, skip: false, loanState: {},
};
let CS = null;   // CesiumJS renderer (assets/cesium3d.js) when available; MapLibre otherwise
const RAMP = [[0, '#ffd666'], [3, '#ff8c42'], [8, '#f03e5c'], [15, '#b832c8'], [30, '#7828dc']];
function rampColor(v) {
  const h = x => [1, 3, 5].map(i => parseInt(x.slice(i, i + 2), 16));
  if (v <= RAMP[0][0]) return RAMP[0][1];
  for (let i = 1; i < RAMP.length; i++) if (v <= RAMP[i][0]) {
    const t = (v - RAMP[i - 1][0]) / (RAMP[i][0] - RAMP[i - 1][0]), a = h(RAMP[i - 1][1]), b = h(RAMP[i][1]);
    return '#' + a.map((x, j) => Math.round(x + (b[j] - x) * t).toString(16).padStart(2, '0')).join('');
  }
  return RAMP[RAMP.length - 1][1];
}
function jsColor(f) {   // same logic as the MapLibre expression bColor(), for the Cesium primitives
  const p = f.properties;
  if (S.hlB.has(p.id)) return '#7cffcb';
  const ch = S.loanState[p.id];
  if (S.layers.loans && S.loansOn && !S.layers.swipe && ch) return { DUAL: '#ff4d6d', OPERATIONS: '#ff8c42', COLLATERAL: '#4dabf7', NONE: '#e9efe9' }[ch];
  const day = S.layers.swipe ? 0 : dayOf(S.k);
  if ((S.layers.water || S.layers.persist || S.layers.swipe) && S.k >= 0 && p.flooded && p.days >= day) return rampColor(p.days);
  return '#1f3a31';
}
const PERSIST_RAMP = ['interpolate', ['linear'], ['get', 'days'], 0, '#ffd666', 3, '#ff8c42', 8, '#f03e5c', 15, '#b832c8', 30, '#7828dc'];

/* ------------------------------------------------------------------ boot */
let map;
boot().catch(e => { console.error(e); toast('Could not load data: ' + e.message, 9000); });

async function boot() {
  S.cfg = await api('/api/config');
  S.log = await api('/api/log');
  for (const a of S.cfg.aois) S.meta[a] = await api('/api/aoi/' + a);
  S.aoi = S.cfg.aois.includes('alquoz') ? 'alquoz' : S.cfg.aois[0];
  const test = S.cfg.mode === 'TEST';
  $('prov').classList.toggle('test', test);
  const nPass = S.cfg.aois.reduce((s, a) => s + S.meta[a].dates.length, 0);
  $('provText').textContent = test ? 'TEST DATA · RUN PIPELINE FOR REAL' : `REAL · SENTINEL-2 L2A · ${nPass} PASSES · ${S.cfg.aois.length} AREAS`;
  $('testMark').classList.toggle('hidden', !test);
  if (test) $('qsub').textContent = 'synthetic loans · TEST buildings';
  $('aois').innerHTML = S.cfg.aois.map(a => `<button data-aoi="${a}">${esc(S.meta[a].short)}</button>`).join('');
  $$('#aois button').forEach(b => b.onclick = () => selectAoi(b.dataset.aoi, true));
  $('beta').value = S.cfg.defaults.beta; S.params.beta = S.cfg.defaults.beta;
  wireUi();
  await setupMap();
}

function wantCesium() {
  const q = new URLSearchParams(location.search).get('renderer');
  if (q === 'lite') return false;
  if (q !== 'cesium' && window.innerWidth < 900) return false;   // phones/tablets: lighter renderer by default
  return !!(window.Cesium && window.CS3D && (S.cfg.cesiumToken || q === 'cesium'));
}

async function setupMap() {
  if (wantCesium()) {
    try { await setupCesium(); return; }
    catch (e) { console.warn('Cesium failed, using MapLibre', e); toast('Cinematic 3D unavailable, switched to offline 3D'); CS = null; S.ready = false; $('map').innerHTML = ''; }
  }
  $('rendBtn').textContent = '3D · LITE';
  setupMapLibre();
}

async function setupCesium() {
  $('rendBtn').textContent = '3D · CESIUM';
  const cs = await CS3D.init('map', S.cfg.cesiumToken, S.cfg.aois.map(a => S.meta[a].rect));
  for (const a of S.cfg.aois) { await loadBuildings(a); await cs.addArea(a, S.meta[a], S.bld[a], jsColor); }
  CS = cs;
  CS.onPick = id => {
    if (!id) return;
    if (String(id).startsWith('loan:')) return openLoan(String(id).slice(5));
    const l = (S.stress?.loans || []).find(x => x.ops_building === id || x.coll_building === id);
    if (l) openLoan(l.loan_id);
  };
  S.ready = true;
  await refreshStress();
  selectAoi(S.aoi, true);
  renderConsoleLog();
  setTimeout(() => { if (CS && !CS.status().ion) toast('Cesium ion not reachable: showing our Sentinel-2 imagery only (still fully working).', 6000); }, 9000);
}

async function loadBuildings(a) {
  if (S.bld[a]) return;
  S.bld[a] = await (await fetch(S.meta[a].base + 'buildings.geojson')).json();
  for (const f of S.bld[a].features) S.bIndex[f.properties.id] = { aoi: a, p: f.properties, c: centroid(f.geometry) };
}

function setupMapLibre() {
  const m0 = S.meta[S.aoi], c = center(m0.bbox);
  map = new maplibregl.Map({
    container: 'map', attributionControl: false, antialias: true, maxPitch: 78,
    style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#04100d' } }] },
    center: c, zoom: 12.2, pitch: 30, bearing: -10,
  });
  map.on('load', async () => {
    for (const a of S.cfg.aois) await addArea(map, a, false);
    S.ready = true;
    await refreshStress();
    selectAoi(S.aoi, true);
    renderConsoleLog();
  });
  map.on('move', syncB);
}

function center(b) { return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]; }

function rasterLayer(m, id, url, coords, before) {
  m.addSource(id, { type: 'image', url, coordinates: coords });
  m.addLayer({ id, type: 'raster', source: id, layout: { visibility: 'none' },
    paint: { 'raster-opacity': 0, 'raster-opacity-transition': { duration: 650 }, 'raster-fade-duration': 0, 'raster-resampling': 'linear' } }, before);
}

async function addArea(m, a, forecastSide) {
  const md = S.meta[a], base = md.base, co = md.corners;
  rasterLayer(m, `pre-${a}`, base + 'rgb_pre.jpg', co);
  md.dates.forEach(d => { if (d.rgb) rasterLayer(m, `post-${a}-${d.index}`, base + d.rgb, co); });
  if (forecastSide) {
    rasterLayer(m, `pred-${a}`, base + 'pred.png', co);
  } else {
    rasterLayer(m, `persist-${a}`, base + 'persistence.png', co);
    rasterLayer(m, `depth-${a}`, base + 'depth.png', co);
    md.dates.forEach(d => rasterLayer(m, `water-${a}-${d.index}`, base + d.water, co));
  }
  await loadBuildings(a);
  m.addSource(`b-${a}`, { type: 'geojson', data: S.bld[a], promoteId: 'id' });
  m.addLayer({ id: `b-${a}`, type: 'fill-extrusion', source: `b-${a}`, layout: { visibility: 'none' },
    paint: { 'fill-extrusion-color': '#1f3a31', 'fill-extrusion-height': ['get', 'height'], 'fill-extrusion-base': 0,
      'fill-extrusion-opacity': 0.93, 'fill-extrusion-vertical-gradient': true } });
}

function centroid(g) {
  const r = g.coordinates[0]; let x = 0, y = 0; const n = r.length - 1 || 1;
  for (let i = 0; i < n; i++) { x += r[i][0]; y += r[i][1]; }
  return [x / n, y / n];
}

/* ------------------------------------------------------------------ rendering */
function setVis(m, id, on, opacity = 1, keep = false) {
  // keep=true: layer stays 'visible' and only its opacity animates -> smooth crossfades between passes
  if (!m.getLayer(id)) return;
  const raster = m.getLayer(id).type === 'raster';
  m.setLayoutProperty(id, 'visibility', on || (keep && raster) ? 'visible' : 'none');
  if (raster) m.setPaintProperty(id, 'raster-opacity', on ? opacity : 0);
}

function dayOf(k) { return k < 0 ? 1e9 : S.meta[S.aoi].dates[k].day; }

function bColor(forecast) {
  if (forecast) return ['case', ['>=', ['get', 'pred_frac'], 0.1], '#ff5ccd', '#22382f'];
  const day = S.layers.swipe ? 0 : dayOf(S.k), showW = (S.layers.water || S.layers.persist || S.layers.swipe) && S.k >= 0, showL = S.layers.loans && S.loansOn && !S.layers.swipe;
  return ['case',
    ['boolean', ['feature-state', 'hl'], false], '#7cffcb',
    showL ? ['==', ['feature-state', 'loan'], 'DUAL'] : false, '#ff4d6d',
    showL ? ['==', ['feature-state', 'loan'], 'OPERATIONS'] : false, '#ff8c42',
    showL ? ['==', ['feature-state', 'loan'], 'COLLATERAL'] : false, '#4dabf7',
    showL ? ['==', ['feature-state', 'loan'], 'NONE'] : false, '#e9efe9',
    showW ? ['all', ['get', 'flooded'], ['>=', ['get', 'days'], day]] : false, PERSIST_RAMP,
    '#1f3a31'];
}

function renderCesium() {
  const md = S.meta[S.aoi];
  const rgbK = S.k >= 0 ? [...md.dates.slice(0, S.k + 1)].reverse().find(d => d.rgb) : null;
  CS.render({ aoi: S.aoi, aois: S.cfg.aois, rgbIndex: rgbK ? rgbK.index : -1,
    waterIndex: S.layers.water && !S.layers.persist && !S.layers.swipe && S.k >= 0 ? S.k : -1,
    persist: (S.layers.persist || S.layers.swipe) && S.k >= 0, depth: S.layers.depth && S.k >= 0, swipe: S.layers.swipe, colorOf: jsColor });
}

function render() {
  if (!S.ready) return;
  if (CS) { renderCesium(); renderScrub(); renderDayStat(); renderMarkers(); return; }
  for (const a of S.cfg.aois) {
    const act = a === S.aoi, md = S.meta[a];
    const rgbK = act && S.k >= 0 ? [...md.dates.slice(0, S.k + 1)].reverse().find(d => d.rgb) : null;
    setVis(map, `pre-${a}`, act, 1, act);   // pre-storm image always underneath: no black gaps
    md.dates.forEach(d => {
      if (d.rgb) setVis(map, `post-${a}-${d.index}`, !!(act && rgbK && rgbK.index === d.index), 1, act);
      setVis(map, `water-${a}-${d.index}`, act && S.layers.water && !S.layers.persist && !S.layers.swipe && S.k === d.index, 0.88, act);
    });
    setVis(map, `persist-${a}`, act && (S.layers.persist || S.layers.swipe) && S.k >= 0, 0.92, act);
    setVis(map, `depth-${a}`, act && S.layers.depth && S.k >= 0, 0.9, act);
    setVis(map, `b-${a}`, act);
    if (act) map.setPaintProperty(`b-${a}`, 'fill-extrusion-color', bColor(false));
  }
  renderScrub(); renderDayStat(); renderMarkers();
  if (S.mapB) renderB();
}

function renderDayStat() {
  const md = S.meta[S.aoi];
  if (S.k < 0) { $('dayLabel').textContent = `BEFORE THE STORM · ${fmtDate(md.pre.date).toUpperCase()}`; $('dayStat').textContent = 'dry reference'; return; }
  const d = md.dates[S.k], n = S.bld[S.aoi].features.filter(f => f.properties.flooded && f.properties.days >= d.day).length;
  $('dayLabel').textContent = `DAY ${d.day} · ${fmtDate(d.date).toUpperCase()}`;
  $('dayStat').textContent = `${d.wet_km2.toFixed(2)} km² water · ${n.toLocaleString()} buildings still wet`;
}

function renderScrub() {
  const md = S.meta[S.aoi], n = md.dates.length, tr = $('track');
  tr.querySelectorAll('.tick').forEach(x => x.remove());
  const pos = i => (i + 1) / n * 100;
  const mk = (i, label) => { const b = document.createElement('button'); b.className = 'tick' + (i === S.k ? ' on' : i < S.k ? ' past' : '');
    b.style.left = (i < 0 ? 0 : pos(i)) + '%'; b.innerHTML = `<i></i><span>${label}</span>`; b.onclick = () => { setK(i); }; tr.appendChild(b); };
  mk(-1, 'PRE');
  md.dates.forEach((d, i) => mk(i, 'D' + d.day));
  $('trackFill').style.width = (S.k < 0 ? 0 : pos(S.k)) + '%';
}

function setK(k) { S.k = Math.max(-1, Math.min(k, S.meta[S.aoi].dates.length - 1)); render(); renderEvidence(); }

/* ------------------------------------------------------------------ areas + camera */
function selectAoi(a, fly) {
  if (S.aoi !== a) { S.hlB.clear(); S.hlL.clear(); }
  S.aoi = a;
  $$('#aois button').forEach(b => b.classList.toggle('on', b.dataset.aoi === a));
  if (S.k >= S.meta[a].dates.length) S.k = S.meta[a].dates.length - 1;
  applyLoanStates(); render(); renderEvidence(); renderImpact(); renderConsoleLog(); renderSugg();
  if (fly) flyArea(a);
  if (S.mapB) { rebuildB(); }
}

function flyArea(a, opt = {}) {
  if (CS) return CS.flyRect(S.meta[a].rect, { range: 1.25 / Math.pow(2, opt.zoom ?? 0.45), pitch: -(90 - (opt.pitch ?? 58)) - 6,
    heading: opt.bearing ?? -18, duration: opt.duration ?? 2600 });
  const b = S.meta[a].bbox;
  const cam = map.cameraForBounds([[b[0], b[1]], [b[2], b[3]]], { padding: { top: 90, bottom: 190, left: window.innerWidth > 900 ? 380 : 20, right: window.innerWidth > 900 ? 420 : 20 }, bearing: -18 });
  map.flyTo({ ...cam, zoom: cam.zoom + (opt.zoom || 0.45), pitch: opt.pitch ?? 58, bearing: opt.bearing ?? -18, duration: opt.duration ?? 2600, essential: true });
}

/* ------------------------------------------------------------------ stress + impact */
async function refreshStress() {
  const qs = new URLSearchParams({ ...S.params, aoi: S.aoi || 'all' });
  S.stress = await api('/api/stress?' + qs);
  if (S.scenario) {
    const base = await api('/api/stress?' + new URLSearchParams({ beta: S.params.beta, aoi: S.aoi || 'all' }));
    $('scenDelta').textContent = '+' + aed(S.stress.summary.delta_el - base.summary.delta_el);
  } else $('scenDelta').textContent = '';
  applyLoanStates(); renderImpact(); render();
}

function aoiLoans() { return (S.stress?.loans || []).filter(l => l.ops_aoi === S.aoi || l.coll_aoi === S.aoi); }

function applyLoanStates() {
  if (!S.stress) return;
  S.loanState = {};
  for (const l of S.stress.loans) { S.loanState[l.ops_building] = S.loanState[l.ops_building] && S.loanState[l.ops_building] !== 'NONE' ? S.loanState[l.ops_building] : l.channel;
    S.loanState[l.coll_building] = S.loanState[l.coll_building] && S.loanState[l.coll_building] !== 'NONE' ? S.loanState[l.coll_building] : l.channel; }
  if (CS || !map) return;
  for (const a of S.cfg.aois) if (map.getSource(`b-${a}`)) map.removeFeatureState({ source: `b-${a}` });
  for (const l of S.stress.loans) {
    for (const [aoi, bid] of [[l.ops_aoi, l.ops_building], [l.coll_aoi, l.coll_building]]) {
      if (map.getSource(`b-${aoi}`)) map.setFeatureState({ source: `b-${aoi}`, id: bid }, { loan: l.channel });
    }
  }
  for (const bid of S.hlB) { const b = S.bIndex[bid]; if (b && map.getSource(`b-${b.aoi}`)) map.setFeatureState({ source: `b-${b.aoi}`, id: bid }, { hl: true }); }
}

let countT = {};
function countUp(el, to, f = x => Math.round(x).toLocaleString()) {
  const from = +el.dataset.v || 0, t0 = performance.now(), dur = 900; el.dataset.v = to;
  cancelAnimationFrame(countT[el.id]);
  const step = t => { const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3); el.textContent = f(from + (to - from) * e); if (p < 1) countT[el.id] = requestAnimationFrame(step); };
  countT[el.id] = requestAnimationFrame(step);
}

function renderImpact() {
  if (!S.stress) return;
  const s = S.stress.summary;
  countUp($('kFlag'), s.flagged); $('kFlagSub').textContent = `of ${s.loans} loans touching ${S.meta[S.aoi].short}`;
  countUp($('kDual'), s.dual);
  countUp($('kDelta'), s.delta_el, aed);
  const pdPart = Math.max(0, s.delta_pd_channel), tot = Math.max(1, s.delta_el), lgdPart = Math.max(0, tot - pdPart);
  $('splitPD').style.width = (100 * pdPart / tot) + '%'; $('splitLGD').style.width = (100 * lgdPart / tot) + '%';
  $('kEad').textContent = `${aed(s.ead_flagged)} exposure flagged`;
  const rows = aoiLoans().filter(l => l.channel !== 'NONE').slice(0, 30);
  $('queue').innerHTML = rows.length ? rows.map(l => `<div class="row${S.hlL.has(l.loan_id) ? ' hl' : ''}" data-id="${l.loan_id}"><span class="dot ch-${l.channel}"></span>
    <div><b>${l.loan_id}</b> <small>${esc(l.sector)} · ${l.channel === 'DUAL' ? 'ops + collateral' : l.channel.toLowerCase()}${l.ops_days ? ' · wet ' + l.ops_days + 'd' : ''}${l.coll_depth_m ? ' · ' + l.coll_depth_m.toFixed(1) + ' m' : ''}${l.insurance_cover ? '' : ' · uninsured'}</small></div>
    <div class="amt">+${aed(l.delta_el)}<small>PD ${l.pd_pct.toFixed(1)}→${l.pd_stress_pct.toFixed(1)}%</small></div></div>`).join('')
    : '<p class="notes">No loans in this area had water around their buildings.</p>';
  $$('#queue .row').forEach(r => r.onclick = () => openLoan(r.dataset.id));
}

function renderMarkers() {
  S.markers.forEach(m => m.remove()); S.markers = [];
  if (!S.layers.loans || !S.loansOn || !S.stress || S.layers.swipe) { if (CS) CS.markers([]); return; }
  if (CS) {
    const seen = new Set(), items = [], list = aoiLoans().filter(l => l.channel !== 'NONE' || S.hlL.has(l.loan_id));
    const top = new Set(list.slice(0, 4).map(l => l.loan_id));
    for (const l of list) {
      const bid = l.ops_aoi === S.aoi ? l.ops_building : l.coll_building, b = S.bIndex[bid];
      if (!b || seen.has(bid)) continue; seen.add(bid);
      items.push({ id: l.loan_id, lon: b.c[0], lat: b.c[1], h: b.p.height, kind: S.hlL.has(l.loan_id) ? 'HL' : l.channel,
        label: top.has(l.loan_id) || S.hlL.has(l.loan_id) ? `${l.loan_id} · +${aed(l.delta_el)}` : '' });
    }
    return CS.markers(items);
  }
  const seen = new Set();
  const list = aoiLoans().filter(l => l.channel !== 'NONE' || S.hlL.has(l.loan_id));
  const top = new Set(list.slice(0, 4).map(l => l.loan_id));
  for (const l of list) {
    const bid = l.ops_aoi === S.aoi ? l.ops_building : l.coll_building, b = S.bIndex[bid];
    if (!b || seen.has(bid)) continue; seen.add(bid);
    const el = document.createElement('div');
    el.className = 'lm ' + (S.hlL.has(l.loan_id) ? 'HL' : l.channel);
    el.innerHTML = `<i></i>${top.has(l.loan_id) || S.hlL.has(l.loan_id) ? `<span>${l.loan_id} · +${aed(l.delta_el)}</span>` : ''}`;
    el.onclick = e => { e.stopPropagation(); openLoan(l.loan_id); };
    S.markers.push(new maplibregl.Marker({ element: el }).setLngLat(b.c).addTo(map));
  }
}

/* ------------------------------------------------------------------ evidence tab */
function renderEvidence() {
  const md = S.meta[S.aoi], st = md.stats;
  $('evArea').innerHTML = `${esc(md.name)}<br><small>${st.aoi_km2} km² analysed · pre-storm ref ${fmtDate(md.pre.date)}</small>`;
  $('evFlood').textContent = st.flooded_km2.toFixed(2) + ' km² flooded';
  const det = S.cfg.detection?.[S.aoi];
  if (det) $('evArea').insertAdjacentHTML('beforeend', `<br><small style="color:var(--water)">DETECTED DAY ${det.days_after_event} (${fmtDate(det.first_clear_pass)}) · vs quarterly review ≤ 90 days</small>`);
  const mx = Math.max(...md.dates.map(d => d.wet_km2), 0.001);
  $('bars').innerHTML = md.dates.map(d => `<div class="bar${d.index === S.k ? ' on' : ''}" data-k="${d.index}"><em>${d.wet_km2.toFixed(2)}</em><i style="height:${Math.max(3, 100 * d.wet_km2 / mx)}%"></i><span>D${d.day}</span></div>`).join('')
    + '';
  $('bars').insertAdjacentHTML('afterend', '');
  $$('#bars .bar').forEach(b => b.onclick = () => setK(+b.dataset.k));
  if (!$('barsCap')) $('bars').insertAdjacentHTML('afterend', '<div class="bars-cap" id="barsCap"></div>');
  $('barsCap').textContent = 'km² of new water seen on each clear Sentinel-2 pass after 16 Apr 2024';
  $('passes').innerHTML = md.dates.filter(d => d.rgb).map(d => `<div class="pass${d.index === S.k ? ' on' : ''}" data-k="${d.index}"><img src="${md.base + d.rgb}" alt="Sentinel-2 ${d.date}" loading="lazy"><div class="wm" style="background-image:url(${md.base + d.water})"></div><span>${d.date.slice(5)} · ${Math.round(d.valid_frac * 100)}% clear</span></div>`).join('');
  $$('#passes .pass').forEach(p => p.onclick = () => setK(+p.dataset.k));
  const v = md.validation, h = v.holdout, r = v.random_baseline_holdout;
  $('val').innerHTML = `<h4>FORECAST vs REALITY · SPATIAL HOLDOUT</h4>
    <div class="nums"><strong>${h.iou.toFixed(2)}</strong><span>IoU · terrain-only forecast</span></div>
    <p>Precision ${h.precision.toFixed(2)} · recall ${h.recall.toFixed(2)} · random map IoU ${r.iou.toFixed(2)}. Calibrated on the west half, scored on the untouched east half. ${h.iou < 0.5 ? '<b>Terrain alone misses most of what the satellite saw — that is the gap CLIMAX closes.</b>' : ''}</p>`;
  $('notes').innerHTML = md.notes.map(esc).join('<br>') + `<br>Depth median ${st.median_depth_m} m (indicative). Buildings: ${st.buildings.toLocaleString()} footprints, ${st.buildings_flooded.toLocaleString()} with water in their 15 m ring, ${st.buildings_flooded_7d.toLocaleString()} for ≥ 7 days.`;
}

/* ------------------------------------------------------------------ agent console */
function renderConsoleLog() {
  const c = $('console'); if (!c || !S.aoi) return;
  const rows = S.log.filter(l => l.aoi === S.aoi || l.aoi === 'all');
  c.innerHTML = `<div class="sys">PIPELINE RUN · ${esc(S.cfg.generated_at || '')} · ${S.cfg.mode}</div>` + rows.map(stepHtml).join('')
    + `<div class="sys">ASK ANYTHING · ${S.cfg.llm ? 'CLAUDE (' + esc(S.cfg.model) + ') PLANS THE TOOL CALLS' : 'OFFLINE PARSER · add ANTHROPIC_API_KEY for Claude'}</div>`;
}
function stepHtml(l) { return `<div class="step"><span class="t">${l.t_s != null ? l.t_s.toFixed(1) + 's' : '›'}</span><div><span class="tool">${esc(l.tool)}</span> <span class="args">${esc(JSON.stringify(l.args || l.input || {}))}</span></div><div class="res">${esc(l.result)}</div></div>`; }

async function streamLog(ms = 140) {
  const c = $('console'); const rows = S.log.filter(l => l.aoi === S.aoi || l.aoi === 'all');
  c.innerHTML = `<div class="sys">REPLAY OF LOGGED PIPELINE RUN · ${esc(S.cfg.generated_at || '')} · ${S.cfg.mode}</div>`;
  $('agentDot').classList.add('live');
  for (const l of rows) { if (S.skip) break; c.insertAdjacentHTML('beforeend', stepHtml(l)); c.parentElement.scrollTop = 1e9; await sleep(ms); }
  $('agentDot').classList.remove('live'); renderConsoleLog(); c.parentElement.scrollTop = 1e9;
}

async function ask(q) {
  q = (q || '').trim(); if (!q) return;
  showTab('agent');
  const c = $('console'), rtl = /[؀-ۿ]/.test(q) ? ' dir="rtl"' : '';
  c.insertAdjacentHTML('beforeend', `<div class="msg q"${rtl}>${esc(q)}</div>`);
  c.insertAdjacentHTML('beforeend', '<div class="sys" id="thinking">● CALLING TOOLS…</div>'); c.parentElement.scrollTop = 1e9;
  $('agentDot').classList.add('live');
  try {
    const r = await api('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ q, aoi: S.aoi, params: S.params }) });
    $('thinking')?.remove();
    for (const s of r.steps) { c.insertAdjacentHTML('beforeend', stepHtml(s)); await sleep(160); c.parentElement.scrollTop = 1e9; }
    const artl = /[؀-ۿ]/.test(r.answer) ? ' dir="rtl"' : '';
    c.insertAdjacentHTML('beforeend', `<div class="msg a"${artl}>${esc(r.answer)}<span class="eng">${esc(r.engine)} · ${r.steps.length} tool call(s)</span></div>`);
    c.parentElement.scrollTop = 1e9;
    if (r.aoi && r.aoi !== S.aoi) selectAoi(r.aoi, true);
    S.hlB = new Set(r.highlight.buildings || []); S.hlL = new Set(r.highlight.loans || []);
    if (S.hlL.size) { S.loansOn = true; S.layers.loans = true; }
    if (S.hlB.size && S.k < 0) S.k = 0;
    if (r.scenario) { Object.assign(S.params, { persist_mult: r.scenario.persist_mult, depth_mult: r.scenario.depth_mult, beta: r.scenario.beta }); S.scenario = r.scenario.persist_mult !== 1; $('scenBtn').classList.toggle('on', S.scenario); $('beta').value = S.params.beta; $('betaV').textContent = S.params.beta.toFixed(2); }
    syncLayerButtons();
    await refreshStress();
    zoomToHighlights();
  } catch (e) { $('thinking')?.remove(); c.insertAdjacentHTML('beforeend', `<div class="msg a">Error: ${esc(e.message)}</div>`); }
  $('agentDot').classList.remove('live');
}

function zoomToHighlights() {
  const pts = [...S.hlB].map(id => S.bIndex[id]).filter(b => b && b.aoi === S.aoi).map(b => b.c);
  if (!pts.length) return;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  if (CS) {
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) * 111000;
    return CS.flyPoint((Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2, { range: Math.min(6000, Math.max(700, span * 1.7)), pitch: -38 });
  }
  const cam = map.cameraForBounds([[Math.min(...xs) - 0.004, Math.min(...ys) - 0.004], [Math.max(...xs) + 0.004, Math.max(...ys) + 0.004]],
    { padding: { top: 120, bottom: 200, left: 420, right: 440 }, bearing: map.getBearing() });
  if (cam) map.flyTo({ ...cam, zoom: Math.min(cam.zoom, 16.2), pitch: 60, duration: 1800 });
}

/* ------------------------------------------------------------------ loan drawer */
async function openLoan(id) {
  const l = await api('/api/loan/' + id + '?' + new URLSearchParams(S.params));
  const b = S.bIndex[l.ops_aoi === S.aoi ? l.ops_building : l.coll_building];
  if (b) CS ? CS.flyPoint(b.c[0], b.c[1], { range: 560 }) : map.flyTo({ center: b.c, zoom: 16.4, pitch: 64, duration: 1500 });
  S.hlB = new Set([l.ops_building, l.coll_building]); S.hlL = new Set([l.loan_id]); applyLoanStates(); render(); renderImpact();
  $('drawerBody').innerHTML = `<div class="tagline">LOAN REVIEW · ${l.channel} CHANNEL</div><h2>${l.loan_id}</h2><div>${esc(l.borrower)}</div><span class="syn">${esc(l.data_class)}</span>
  <table>
   <tr><td>Exposure (EAD)</td><td>${aed(l.ead_aed)}</td></tr>
   <tr><td>PD baseline → stressed</td><td>${l.pd_pct.toFixed(2)}% → <b style="color:var(--pd)">${l.pd_stress_pct.toFixed(2)}%</b></td></tr>
   <tr><td>LGD baseline → stressed</td><td>${l.lgd_pct.toFixed(0)}% → <b style="color:var(--lgd)">${l.lgd_stress_pct.toFixed(1)}%</b></td></tr>
   <tr><td>Interruption days (ops site)</td><td>${l.interruption_days}</td></tr>
   <tr><td>Collateral (${esc(l.coll_type)})</td><td>${aed(l.collateral_value_aed)} · ${Math.round(l.insurance_cover * 100)}% insured</td></tr>
   <tr><td>Collateral value source</td><td>${esc(l.collateral_value_source || 'synthetic')}</td></tr>
   <tr><td>Indicative damage → value loss</td><td>${Math.round(l.damage_frac * 100)}% → ${aed(l.value_loss_aed)}</td></tr>
   <tr><td><b>Δ expected loss</b></td><td><b style="color:var(--cream)">+${aed(l.delta_el)}</b></td></tr>
  </table>
  <h3>EVIDENCE CHAIN</h3><ul class="why">${l.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul>
  <h3>BUILDINGS</h3><p class="notes">Operating site <code>${esc(l.ops_building)}</code> (${esc(l.ops_aoi)}, ${esc(l.ops_use)}) · Collateral <code>${esc(l.coll_building)}</code> (${esc(l.coll_aoi)}).<br>Forecast flagged ops: ${l.predicted_ops ? 'yes' : '<b>no</b>'} · collateral: ${l.predicted_coll ? 'yes' : '<b>no</b>'}.</p>
  <h3>NEXT STEP</h3><p class="notes">Request business-continuity evidence and insurance schedule; re-value collateral if indicative depth > 0.5 m. Human decision — CLIMAX ranks, it does not decide.</p>`;
  openDrawer();
}
function openDrawer() { $('drawer').classList.remove('hidden'); $('drawerBg').classList.remove('hidden'); }
function closeDrawer() { $('drawer').classList.add('hidden'); $('drawerBg').classList.add('hidden'); }

function openSources() {
  $('drawerBody').innerHTML = `<div class="tagline">EVIDENCE & METHOD</div><h2>Sources</h2>
  <p class="notes">Data mode: <b>${S.cfg.mode}</b>${S.cfg.mode === 'TEST' ? ' — procedurally generated, not satellite data. Run <code>python3 -m pipeline.run_all</code>.' : ' — generated ' + esc(S.cfg.generated_at)}.</p>
  <div class="src">${S.cfg.sources.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener">↗ ${esc(s.name)}</a>`).join('')}</div>
  <h3>FORMULA</h3><pre class="notes" style="white-space:pre-wrap">${esc(S.stress?.formula || '')}</pre><p class="notes">${esc(S.stress?.disclaimer || '')}</p>`;
  openDrawer();
}

/* ------------------------------------------------------------------ swipe (forecast vs reality) */
async function enableSwipe(on) {
  if (CS) {   // Cesium: native imagery split, no second map needed
    S.layers.swipe = on; $('swipe').classList.toggle('hidden', !on);
    if (on && S.k < 0) S.k = 0;
    setSwipe(S.swipePos); syncLayerButtons(); render(); return;
  }
  S.layers.swipe = on; $('swipe').classList.toggle('hidden', !on); $('mapB').classList.toggle('hidden', !on);
  if (on) { if (S.k < 0) S.k = 0; if (!S.mapB) await buildB(); else rebuildB(); setSwipe(S.swipePos); }
  syncLayerButtons(); render();
}
function buildB() {
  return new Promise(res => {
    S.mapB = new maplibregl.Map({ container: 'mapB', attributionControl: false, interactive: false, antialias: true, maxPitch: 78,
      style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#04100d' } }] },
      center: map.getCenter(), zoom: map.getZoom(), pitch: map.getPitch(), bearing: map.getBearing() });
    S.mapB.on('load', async () => { for (const a of S.cfg.aois) await addArea(S.mapB, a, true); S.readyB = true; applyStatesB(); renderB(); res(); });
  });
}
function rebuildB() { renderB(); }
function applyStatesB() { /* forecast side shows no loan colours, only the forecast */ }
function renderB() {
  const m = S.mapB; if (!m || !S.readyB) return;
  for (const a of S.cfg.aois) {
    const act = a === S.aoi;
    setVis(m, `pre-${a}`, act, 1);
    S.meta[a].dates.forEach(d => d.rgb && setVis(m, `post-${a}-${d.index}`, false));
    setVis(m, `pred-${a}`, act, 0.85);
    setVis(m, `b-${a}`, act); if (act) m.setPaintProperty(`b-${a}`, 'fill-extrusion-color', bColor(true));
  }
  syncB();
}
function syncB() { if (CS) return; if (S.mapB && S.layers.swipe) S.mapB.jumpTo({ center: map.getCenter(), zoom: map.getZoom(), pitch: map.getPitch(), bearing: map.getBearing() }); }
function setSwipe(p) {
  S.swipePos = Math.max(4, Math.min(96, p));
  if (CS) CS.split(S.swipePos);
  $('mapB').style.clipPath = `inset(0 ${100 - S.swipePos}% 0 0)`;
  $$('.swipe-line,.swipe-knob').forEach(e => e.style.left = S.swipePos + '%');
  $$('.swipe-tag').forEach(e => e.style.left = S.swipePos + '%');
}
(function dragSwipe() {
  let drag = false; const k = document.querySelector('.swipe-knob');
  k.addEventListener('pointerdown', e => { drag = true; k.setPointerCapture(e.pointerId); });
  k.addEventListener('pointermove', e => { if (drag) setSwipe(100 * e.clientX / window.innerWidth); });
  k.addEventListener('pointerup', () => drag = false);
})();

/* ------------------------------------------------------------------ rain */
const rain = { on: false, drops: [] };
function startRain(on) {
  const c = $('rain'); rain.on = on; c.style.opacity = on ? 1 : 0;
  if (!on) return;
  c.width = innerWidth; c.height = innerHeight; const g = c.getContext('2d');
  rain.drops = Array.from({ length: 520 }, () => ({ x: Math.random() * c.width, y: Math.random() * c.height, l: 10 + Math.random() * 22, v: 14 + Math.random() * 16 }));
  const tick = () => { g.clearRect(0, 0, c.width, c.height); g.strokeStyle = 'rgba(190,240,255,.45)'; g.lineWidth = 1.1; g.beginPath();
    for (const d of rain.drops) { g.moveTo(d.x, d.y); g.lineTo(d.x - d.l * .25, d.y + d.l); d.y += d.v; d.x -= d.v * .25; if (d.y > c.height) { d.y = -20; d.x = Math.random() * c.width * 1.2; } }
    g.stroke(); if (rain.on || +getComputedStyle(c).opacity > 0.02) requestAnimationFrame(tick); else g.clearRect(0, 0, c.width, c.height); };
  tick();
}
function flash() { const f = $('flash'); f.classList.remove('go'); void f.offsetWidth; f.classList.add('go'); }

/* ------------------------------------------------------------------ captions + story */
function caption(eye, title, sub, chips = []) {
  const c = $('caption'); c.classList.remove('swap'); void c.offsetWidth; c.classList.add('swap');
  $('capEye').textContent = eye; $('capTitle').innerHTML = title; $('capSub').textContent = sub;
  $('capChips').innerHTML = chips.map(([cls, k, v]) => `<span class="chip ${cls}">${esc(k)} <b>${esc(v)}</b></span>`).join('');
}
function defaultCaption() {
  const md = S.meta[S.aoi], t = S.cfg.mode === 'TEST';
  caption('CBUAE CHALLENGE #1 · CLIMATE RISK FOR BANKS', 'Floods in Dubai<br><em>don\'t just hit. They stay.</em>',
    'We measure how long water stayed around every building from free satellite data, and turn it into credit risk.',
    [[t ? 'test' : 'real', 'WATER', t ? 'TEST DATA' : 'SENTINEL-2 MEASURED'], [t ? 'test' : 'real', 'BUILDINGS', t ? 'TEST' : 'OSM REAL'], ['syn', 'LOANS', 'SYNTHETIC'], [S.cfg.gov ? 'real' : 'syn', 'COLLATERAL AED/m²', S.cfg.gov ? 'DLD · DATA.DUBAI' : 'SYNTHETIC'], ['', 'AREA', md.short]]);
}
async function wait(ms) { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (S.skip || !S.story) return; await sleep(60); } }

async function typeInto(el, text, ms = 38) { el.value = ''; for (const ch of text) { if (!S.story) break; el.value += ch; await sleep(ms); } }

async function story() {
  if (S.story) { S.story = false; return; }
  S.story = true; S.skip = false; $('storyBtn').textContent = '■ STOP'; closeDrawer();
  const md = S.meta[S.aoi], st = md.stats, v = md.validation.holdout, r = md.validation.random_baseline_holdout;
  const first = md.dates[0], last = md.dates[md.dates.length - 1];
  enableSwipe(false); S.loansOn = false; S.layers = { water: true, persist: false, depth: false, swipe: false, loans: true }; syncLayerButtons();
  S.hlB.clear(); S.hlL.clear(); applyLoanStates(); setK(-1);
  const stage = s => $('app').dataset.stage = s;
  try {
    // 0 · alert + agent wakes up
    stage('story-alert'); showTab('agent');
    if (CS) CS.flyRect(md.rect, { range: 3.4, pitch: -62, heading: 0, duration: 1500 });
    else map.flyTo({ center: center(md.bbox), zoom: 11.2, pitch: 20, bearing: 0, duration: 1500 });
    const al = document.createElement('div'); al.className = 'alert';
    al.innerHTML = `<div class="lvl">⚠ SEVERE WEATHER · UAE · 15–16 APRIL 2024</div><h3>Heaviest rainfall in 75 years of UAE records</h3><p>254.8 mm fell at Khatm Al Shakla in under 24 hours (NCM). Dubai airport cancelled 2,155 flights.</p><small>Agent wakes: search satellite archive → detect water → measure how long it stays → join buildings → stress loans.</small>`;
    $('app').appendChild(al);
    streamLog(Math.max(60, Math.min(160, 4200 / Math.max(1, S.log.length))));
    await wait(5200); al.remove();
    // 1 · before
    stage('story'); showTab('evidence');
    caption('01 · BEFORE', `${esc(md.name)}<br><em>${fmtDate(md.pre.date)}.</em>`, `${S.cfg.mode === 'TEST' ? 'TEST scene' : 'Sentinel-2 view'} before the storm. ${st.buildings.toLocaleString()} ${S.cfg.mode === 'TEST' ? 'test' : 'real OpenStreetMap'} building footprints. Dry.`, [['real', 'SCENE', (md.pre.scenes[0] || '').slice(0, 24) || '—']]);
    flyArea(S.aoi, { duration: 3200 }); await wait(3800);
    // 2 · storm
    caption('02 · THE STORM', '16 April 2024.<br><em>The sky opens.</em>', 'Animation for the moment of the storm only. From here on, everything you see is measured.');
    startRain(true); flash(); await wait(1500); flash(); await wait(1800); startRain(false);
    // 3 · reveal
    setK(0);
    caption('03 · WHAT THE SATELLITE SAW', `Day ${first.day}:<br><em>${first.wet_km2.toFixed(2)} km² of new water.</em>`, `Sentinel-2 pass ${fmtDate(first.date)}. Water = MNDWI change vs the pre-storm scene, ${Math.round(first.valid_frac * 100)}% cloud-free.`,
      [['real', 'BUILDINGS WITH WATER', st.buildings_flooded.toLocaleString()], ['real', 'DETECTED', `DAY ${first.day} · NOT NEXT QUARTER`]]);
    await wait(4200);
    // 4 · persistence
    caption('04 · THE PART NOBODY PRICES', 'Floods in Dubai<br><em>don\'t just hit. They stay.</em>', `We follow every clear pass until ${fmtDate(last.date)}. Buildings stay coloured while water is still around them.`);
    for (let i = 1; i < md.dates.length; i++) { if (!S.story) break; setK(i); await wait(1700); }
    caption('04 · THE PART NOBODY PRICES', `${st.buildings_flooded_7d.toLocaleString()} buildings<br><em>wet for 7+ days.</em>`, `${(st.still_wet_at_last_obs_km2).toFixed(2)} km² was still under water on the last clear pass. A damage-only stress test misses the weeks a business cannot open.`,
      [['real', 'FLOODED', st.flooded_km2.toFixed(2) + ' km²'], ['real', 'STILL WET', st.still_wet_at_last_obs_km2.toFixed(2) + ' km²']]);
    S.layers.persist = true; syncLayerButtons(); render(); await wait(4200); S.layers.persist = false; syncLayerButtons();
    // 5 · loans
    setK(0); S.loansOn = true; render(); showTab('impact');
    const s = S.stress.summary;
    caption('05 · TWO LOSSES', 'Duration → PD.<br><em>Depth → LGD.</em>', `${s.flagged} of ${s.loans} loans here sit on a building with water around it; ${s.dual} are hit on both the business and the collateral.`,
      [['syn', 'Δ EXPECTED LOSS', aed(s.delta_el)], ['syn', 'LOANS', S.cfg.mode === 'TEST' ? 'SYNTHETIC · TEST BUILDINGS' : 'SYNTHETIC · REAL BUILDINGS']]);
    flyArea(S.aoi, { zoom: 0.9, duration: 2600, bearing: -35 }); await wait(5600);
    // 6 · forecast vs reality
    caption('06 · FORECAST vs REALITY', `Terrain model alone:<br><em>IoU ${v.iou.toFixed(2)}.</em>`, `A before-the-storm terrain forecast (left) vs what Sentinel-2 saw (right), scored on a held-out half of the map. Random map: ${r.iou.toFixed(2)}. That is why we measure.`);
    showTab('evidence'); await enableSwipe(true);
    for (let p = 20; p <= 80 && S.story; p += 1.2) { setSwipe(p); await sleep(40); }
    for (let p = 80; p >= 50 && S.story; p -= 1.2) { setSwipe(p); await sleep(40); }
    await wait(2600); await enableSwipe(false);
    // 7 · ask in Arabic
    caption('07 · ASK IT', 'Any question.<br><em>English or Arabic.</em>', 'An agent answers only by calling verifiable tools over the pipeline outputs. Every number has a trace.');
    const q = 'أي القروض المرهونة بقيت مبانيها تحت الماء أكثر من ٥ أيام؟';
    await typeInto($('askInput'), q); await wait(400); if (S.story) { await ask(q); $('askInput').value = ''; }
    await wait(4800);
    // 8 · memo
    caption('08 · TO THE RISK COMMITTEE', 'From satellite pass<br><em>to review queue.</em>', 'One click: a cited memo with every scene id, assumption and limitation. CLIMAX ranks; humans decide.');
    showTab('impact'); $('memoBtn').classList.add('pulse'); await wait(4200); $('memoBtn').classList.remove('pulse');
  } finally {
    $$('.alert').forEach(a => a.remove()); startRain(false);
    S.story = false; S.skip = false; $('storyBtn').textContent = '▶ PLAY STORY'; stage('idle'); S.loansOn = true; render();
  }
}

/* ------------------------------------------------------------------ ui wiring */
function showTab(t) { $$('.tab').forEach(b => b.classList.toggle('on', b.dataset.tab === t)); $$('.tabbody').forEach(b => b.classList.toggle('hidden', b.id !== 'tab-' + t)); }
function syncLayerButtons() { $$('#layers button').forEach(b => b.classList.toggle('on', !!S.layers[b.dataset.layer])); }

function renderSugg() {
  const items = [
    'Which uninsured warehouses stayed wet 5+ days?',
    'أي القروض المرهونة بقيت تحت الماء أكثر من ٥ أيام؟',
    'How accurate is a terrain-only forecast here?',
    'Next storm: water stays 1.5x longer — impact?',
  ];
  $('sugg').innerHTML = items.map(t => `<button type="button">${esc(t)}</button>`).join('');
  $$('#sugg button').forEach(b => b.onclick = () => { $('askInput').value = b.textContent; ask(b.textContent); $('askInput').value = ''; });
  $('sugg').classList.add('hidden');
}

function wireUi() {
  defaultCaption();
  $$('.tab').forEach(b => b.onclick = () => showTab(b.dataset.tab));
  $('storyBtn').onclick = () => story();
  $('memoBtn').onclick = () => window.open('/api/memo?' + new URLSearchParams(S.params), '_blank');
  $('exportBtn').onclick = () => { location.href = '/api/export?' + new URLSearchParams(S.params); };
  $('sourcesBtn').onclick = openSources;
  $('rendBtn').onclick = () => { const u = new URL(location.href); u.searchParams.set('renderer', CS ? 'lite' : 'cesium'); location.href = u.toString(); };
  $('drawerX').onclick = closeDrawer; $('drawerBg').onclick = closeDrawer;
  $('beta').oninput = e => { S.params.beta = +e.target.value; $('betaV').textContent = S.params.beta.toFixed(2); clearTimeout(wireUi.t); wireUi.t = setTimeout(refreshStress, 180); };
  $('scenBtn').onclick = () => { S.scenario = !S.scenario; S.params.persist_mult = S.params.depth_mult = S.scenario ? 1.3 : 1.0; $('scenBtn').classList.toggle('on', S.scenario); refreshStress(); };
  $('playDays').onclick = async () => { S.loansOn = true; for (let i = -1; i < S.meta[S.aoi].dates.length; i++) { setK(i); await sleep(1200); } };
  $$('#layers button').forEach(b => b.onclick = () => {
    const l = b.dataset.layer;
    if (l === 'swipe') return enableSwipe(!S.layers.swipe);
    S.layers[l] = !S.layers[l];
    if (l === 'loans') S.loansOn = S.layers.loans;
    if ((l === 'persist' || l === 'depth' || l === 'water') && S.layers[l] && S.k < 0) S.k = 0;
    syncLayerButtons(); render();
  });
  $('askForm').onsubmit = e => { e.preventDefault(); const q = $('askInput').value; $('askInput').value = ''; $('sugg').classList.add('hidden'); ask(q); };
  $('askInput').onfocus = () => $('sugg').classList.remove('hidden');
  $('askInput').onblur = () => setTimeout(() => $('sugg').classList.add('hidden'), 200);
  addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowRight') setK(S.k + 1);
    if (e.key === 'ArrowLeft') setK(S.k - 1);
    if (e.key === ' ') { e.preventDefault(); if (S.story) S.skip = true, setTimeout(() => S.skip = false, 80); else story(); }
    if (e.key === 'Escape') closeDrawer();
  });
  addEventListener('resize', () => { if (rain.on) startRain(true); });
  S.loansOn = true; syncLayerButtons();
}
