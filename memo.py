"""Risk-committee memo (printable HTML) generated from the same engine outputs the UI shows."""
from __future__ import annotations
import html
from datetime import datetime, timezone

import engine


def _aed(x):
    return f"AED {x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"AED {x:,.0f}"


def build(params=None, aoi=None) -> str:
    s = engine.stress(params, aoi)
    m = engine.manifest()
    mode = m.get("mode")
    aois = m.get("aois", [])
    metas = [engine.meta(a) for a in aois]
    e = html.escape
    p = s["params"]; sm = s["summary"]
    top = [r for r in s["loans"] if r["channel"] != "NONE"][:12]
    banner = ("<div class='warn'>TEST DATA. Procedurally generated rasters, not satellite observations. Run the pipeline before presenting.</div>"
              if mode == "TEST" else "")
    area_rows = "".join(
        f"<tr><td>{e(x['name'])}</td><td>{x['pre']['date']}</td><td>{', '.join(d['date'] for d in x['dates'])}</td>"
        f"<td>{x['stats']['flooded_km2']}</td><td>{x['stats']['buildings_flooded']:,} / {x['stats']['buildings']:,}</td>"
        f"<td>{x['stats']['buildings_flooded_7d']:,}</td><td>{x['validation']['holdout']['iou']:.2f} <span class='mut'>(random {x['validation']['random_baseline_holdout']['iou']:.2f})</span></td></tr>"
        for x in metas)
    loan_rows = "".join(
        f"<tr><td>{r['loan_id']}</td><td>{e(r['sector'])}</td><td>{r['channel']}</td><td>{r['ops_days']}</td><td>{r['coll_depth_m']:.2f}</td>"
        f"<td>{r['pd_pct']:.2f}% → {r['pd_stress_pct']:.2f}%</td><td>{r['lgd_pct']:.0f}% → {r['lgd_stress_pct']:.0f}%</td>"
        f"<td>{int(r['insurance_cover'] * 100)}%</td><td class='num'>{_aed(r['delta_el'])}</td></tr>" for r in top)
    scenes = "".join(f"<li>{e(x['name'])}: pre {x['pre']['date']} ({', '.join(x['pre']['scenes'][:2])}); post "
                     + "; ".join(f"{d['date']} ({', '.join(d['scenes'][:1])})" for d in x["dates"]) + "</li>" for x in metas)
    src = "".join(f"<li><a href='{e(x['url'])}'>{e(x['name'])}</a></li>" for x in engine.SOURCES)
    sup_rows = ""
    for x in metas:
        a = x["aoi"]; ss = engine.stress(params, a)["summary"]; det = engine.detection(a)
        sup_rows += (f"<tr><td>{e(x['name'])}</td><td>{det['first_clear_pass']} (day {det['days_after_event']})</td><td>{ss['loans']}</td>"
                     f"<td>{ss['flagged']}</td><td>{_aed(ss['ead_flagged'])}</td><td class='num'>{_aed(ss['delta_el'])}</td></tr>")
    g = engine.gov()
    gov_line = (f"{g['source']} — {g['rows_used']:,} sales since {g['since_year']}; median AED/m² by area: "
                + ", ".join(f"{a} {d['all']:,}" for a, d in g['by_aoi'].items())) if g else \
               "synthetic (DLD transactions file not provided; see data/gov/ in the README)."
    schema_rows = "".join(f"<tr><td><code>{e(r['field'])}</code></td><td>{e(r['type'])}</td><td>{e(r['example'])}</td><td>{e(r.get('note', ''))}</td></tr>"
                          for r in engine.ASSET_HAZARD_SCHEMA)
    now = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CLIMAX risk memo</title>
<style>
body{{font:14px/1.55 -apple-system,Segoe UI,Inter,Arial,sans-serif;color:#10231c;max-width:900px;margin:40px auto;padding:0 24px}}
h1{{font-size:26px;margin:0}} h2{{font-size:16px;margin:28px 0 8px;border-bottom:1px solid #cfe0d7;padding-bottom:4px}}
.k{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}} .k div{{background:#eef6f1;border-radius:8px;padding:10px}}
.k b{{display:block;font-size:20px}} table{{border-collapse:collapse;width:100%;font-size:12.5px}} td,th{{border-bottom:1px solid #e3ece7;padding:5px 6px;text-align:left}}
.num{{text-align:right}} .mut{{color:#6b7f76}} .warn{{background:#ffe8e3;color:#8a1c0a;padding:10px 12px;border-radius:6px;font-weight:700;margin:12px 0}}
.tag{{font-size:11px;letter-spacing:.12em;color:#3d7a5d;font-weight:700}} code{{background:#f1f5f3;padding:1px 4px;border-radius:3px}}
@media print{{a{{color:inherit}}}}
</style></head><body>
<div class="tag">CLIMAX · CLIMATE-CREDIT TRIAGE MEMO · {now}</div>
<h1>April 2024 Dubai flood: portfolio exposure review</h1>
<p class="mut">Prepared automatically from Sentinel-2 flood persistence, Copernicus DEM depth estimates and OpenStreetMap footprints. Loan data: <b>synthetic</b>.</p>
{banner}
<div class="k"><div><span class="mut">Loans flagged</span><b>{sm['flagged']} / {sm['loans']}</b></div><div><span class="mut">Dual-channel</span><b>{sm['dual']}</b></div>
<div><span class="mut">Exposure flagged</span><b>{_aed(sm['ead_flagged'])}</b></div><div><span class="mut">Δ expected loss</span><b>{_aed(sm['delta_el'])}</b></div></div>
<h2>1. Key finding</h2>
<p>Water persistence, not only depth, drives the credit impact: {sm['ops_only'] + sm['dual']} loans have an operating site where water was still visible days after the storm,
which a damage-cost-only stress test (as described in the CBUAE Climate Forum Report 2025, which excludes foregone revenue) would not capture.
{sm['missed_by_terrain_forecast']} flagged loans sit where a terrain-only forecast predicted <i>no</i> flooding.</p>
<h2>2. What the satellite measured</h2>
<table><tr><th>Area</th><th>Pre-storm ref.</th><th>Post-storm passes</th><th>Flooded km²</th><th>Buildings with water</th><th>≥ 7 days</th><th>Terrain forecast IoU</th></tr>{area_rows}</table>
<h2>3. Loans requiring review (top {len(top)})</h2>
<table><tr><th>Loan</th><th>Sector</th><th>Channel</th><th>Ops days wet</th><th>Coll. depth m</th><th>PD</th><th>LGD</th><th>Insured</th><th class="num">Δ EL</th></tr>{loan_rows}</table>
<h2>4. Supervisory view (CBUAE)</h2>
<table><tr><th>Area</th><th>First clear pass (detection)</th><th>Loans touching area</th><th>Flagged</th><th>Exposure flagged</th><th class="num">Δ EL</th></tr>{sup_rows}</table>
<p class="mut">Detection time is the gap between the storm and the first cloud-free satellite pass, compared with a quarterly credit review cycle of up to ~90 days.</p>
<h2>5. Method and assumptions</h2>
<pre style="white-space:pre-wrap;background:#f6faf8;padding:10px;border-radius:6px;font-size:12px">{e(s['formula'])}</pre>
<p>Parameters used: β = {p['beta']} per day, PD cap ×{p['pd_cap']}, persistence ×{p['persist_mult']}, depth ×{p['depth_mult']}.
Persistence is a <b>lower bound</b> (last clear pass a pixel was seen wet; 5-day revisit, clouds). Depth is indicative (30 m surface model incl. buildings).</p>
<p>Collateral values: {e(gov_line)}</p>
<h2>6. Limitations</h2>
<ul><li>Loans, PDs, LGDs, collateral values and insurance are synthetic; assignment to buildings was random by building type and blind to flood results.</li>
<li>Optical satellites cannot see under cloud or beneath roofs; water is measured in a 15 m ring around each footprint.</li>
<li>β (PD uplift per day of interruption) and the depth-damage curve must be calibrated on bank default and claims data.</li>
<li>This is a one-period expected-loss sensitivity for triage, not IFRS 9 ECL and not a capital figure.</li></ul>
<h2>7. Recommended actions</h2>
<ol><li>Request business-continuity evidence from DUAL-channel borrowers above.</li><li>Re-value collateral where indicative depth exceeds 0.5 m.</li>
<li>Pilot: replace synthetic loans with geocoded exposures under a data-sharing agreement; calibrate β on post-April-2024 arrears.</li></ol>
<h2>8. Proposed asset-level physical-risk record (addresses root causes R1–R3)</h2>
<table><tr><th>Field</th><th>Type</th><th>Example</th><th>Note</th></tr>{schema_rows}</table>
<h2>Data provenance</h2><ul>{scenes}</ul>
<h2>Sources</h2><ul>{src}</ul>
</body></html>"""
