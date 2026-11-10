"""CLIMAX agent: answers questions about the flood + loan book by calling verifiable tools.

Pattern follows tool-augmented geospatial agents (e.g. MBZUAI's OpenEarthAgent, 2026): the language model never
invents numbers, it calls tools over the pipeline outputs and every answer carries the tool trace.
- With ANTHROPIC_API_KEY set (private/.env.local), Claude plans the tool calls.
- Without it, a transparent offline parser (English + Arabic) maps the question to the same tools.
"""
from __future__ import annotations
import json
import os
import re
import urllib.request

import engine

AOI_WORDS = {"alquoz": ["quoz", "barsha", "القوز", "البرشاء"], "jebelali": ["jebel", "furjan", "discovery", "جبل علي", "الفرجان", "ديسكفري"],
             "dxb": ["dxb", "airport", "garhoud", "rashidiya", "المطار", "القرهود", "الراشدية"]}

TOOLS = [
    {"name": "get_flood_stats", "description": "Satellite-measured flood statistics for an area: flooded km², area still wet on each observation day, buildings with water around them, dates and scene ids.",
     "input_schema": {"type": "object", "properties": {"aoi": {"type": "string", "enum": ["alquoz", "jebelali", "dxb"]}}, "required": ["aoi"]}},
    {"name": "find_buildings", "description": "Find real OpenStreetMap buildings by flood metrics measured in a 15 m ring around each footprint.",
     "input_schema": {"type": "object", "properties": {
         "aoi": {"type": "string", "enum": ["alquoz", "jebelali", "dxb"]}, "min_days": {"type": "number"}, "min_depth_m": {"type": "number"},
         "use": {"type": "string", "enum": ["warehouse", "industrial", "commercial", "retail", "office", "residential", "hospitality", "public", "unknown"]},
         "limit": {"type": "integer"}}, "required": ["aoi"]}},
    {"name": "query_loans", "description": "Filter and rank the (synthetic) loan book by flood exposure and stressed expected-loss change. channel OPERATIONS/COLLATERAL include DUAL. min_days applies to the longer of operating-site or collateral persistence. ops_use matches the operating OR collateral building type.",
     "input_schema": {"type": "object", "properties": {
         "aoi": {"type": "string", "enum": ["alquoz", "jebelali", "dxb", "all"]},
         "channel": {"type": "string", "enum": ["DUAL", "OPERATIONS", "COLLATERAL", "ANY"]},
         "min_days": {"type": "number"}, "uninsured_only": {"type": "boolean"}, "ops_use": {"type": "string"},
         "limit": {"type": "integer"}}, "required": []}},
    {"name": "explain_loan", "description": "Full evidence chain for one loan id (e.g. SME-012).",
     "input_schema": {"type": "object", "properties": {"loan_id": {"type": "string"}}, "required": ["loan_id"]}},
    {"name": "run_scenario", "description": "Re-run the portfolio stress with different assumptions: persist_mult (water stays longer), depth_mult (deeper water), beta (PD uplift per interruption day).",
     "input_schema": {"type": "object", "properties": {"persist_mult": {"type": "number"}, "depth_mult": {"type": "number"}, "beta": {"type": "number"}}, "required": []}},
    {"name": "get_validation", "description": "How well a terrain-only (before-the-storm) flood forecast matched what the satellite saw: IoU, precision, recall on a spatial holdout.",
     "input_schema": {"type": "object", "properties": {"aoi": {"type": "string", "enum": ["alquoz", "jebelali", "dxb"]}}, "required": ["aoi"]}},
]


# ------------------------------------------------------------------ tool implementations
def t_get_flood_stats(aoi, **_):
    m = engine.meta(aoi)
    return {"aoi": aoi, "name": m["name"], "mode": m["mode"], "stats": m["stats"],
            "observations": [{"date": d["date"], "day": d["day"], "wet_km2": d["wet_km2"], "cloud_free": d["valid_frac"]} for d in m["dates"]],
            "pre_storm_reference": m["pre"]["date"]}


def t_find_buildings(aoi, min_days=0, min_depth_m=0, use=None, limit=40, **_):
    rows = [b for b in engine.buildings_index(aoi).values()
            if b["flooded"] and b["days"] >= (min_days or 0) and b["depth_m"] >= (min_depth_m or 0) and (not use or b["use"] == use)]
    rows.sort(key=lambda b: (b["days"], b["depth_m"]), reverse=True)
    return {"aoi": aoi, "count": len(rows), "buildings": [{k: b[k] for k in ("id", "use", "name", "days", "depth_m", "wet_frac")} for b in rows[:limit or 40]],
            "_highlight_buildings": [b["id"] for b in rows[:400]]}


def t_query_loans(aoi="all", channel="ANY", min_days=0, uninsured_only=False, ops_use=None, limit=8, params=None, **_):
    s = engine.stress(params, aoi if aoi and aoi != "all" else None)
    want = {None: {"DUAL", "OPERATIONS", "COLLATERAL"}, "ANY": {"DUAL", "OPERATIONS", "COLLATERAL"}, "DUAL": {"DUAL"},
            "OPERATIONS": {"DUAL", "OPERATIONS"}, "COLLATERAL": {"DUAL", "COLLATERAL"}}.get(channel, {channel})
    rows = [r for r in s["loans"] if r["channel"] in want
            and max(r["ops_days"], r["coll_days"]) >= (min_days or 0)
            and (not uninsured_only or r["insurance_cover"] == 0)
            and (not ops_use or ops_use in (r["ops_use"], r["coll_use"]))]
    keep = ("loan_id", "borrower", "sector", "channel", "ops_days", "coll_depth_m", "ead_aed", "pd_pct", "pd_stress_pct", "lgd_pct", "lgd_stress_pct", "insurance_cover", "delta_el")
    return {"matches": len(rows), "ead_aed": sum(r["ead_aed"] for r in rows), "delta_el_aed": sum(r["delta_el"] for r in rows),
            "top": [{k: r[k] for k in keep} for r in rows[:limit or 8]], "synthetic": True,
            "_highlight_loans": [r["loan_id"] for r in rows],
            "_highlight_buildings": sorted({r["ops_building"] for r in rows} | {r["coll_building"] for r in rows})}


def t_explain_loan(loan_id, params=None, **_):
    r = engine.explain(loan_id, params)
    if not r:
        return {"error": f"unknown loan {loan_id}"}
    return {**{k: r[k] for k in ("loan_id", "borrower", "sector", "channel", "ops_aoi", "ops_building", "coll_aoi", "coll_building", "coll_type",
                                 "ead_aed", "collateral_value_aed", "pd_pct", "pd_stress_pct", "lgd_pct", "lgd_stress_pct", "insurance_cover",
                                 "interruption_days", "damage_frac", "value_loss_aed", "delta_el", "why", "data_class")},
            "_highlight_loans": [r["loan_id"]], "_highlight_buildings": [r["ops_building"], r["coll_building"]]}


def t_run_scenario(persist_mult=1.0, depth_mult=1.0, beta=None, params=None, **_):
    base = engine.stress(params)["portfolio"]
    p = dict(params or {}); p.update({"persist_mult": persist_mult, "depth_mult": depth_mult})
    if beta is not None:
        p["beta"] = beta
    new = engine.stress(p)["portfolio"]
    return {"assumptions": engine.clean_params(p), "baseline_delta_el": base["delta_el"], "scenario_delta_el": new["delta_el"],
            "increase_aed": new["delta_el"] - base["delta_el"], "flagged": new["flagged"], "_scenario": engine.clean_params(p)}


def t_get_validation(aoi, **_):
    m = engine.meta(aoi)
    return {"aoi": aoi, "mode": m["mode"], **m["validation"]}


IMPL = {"get_flood_stats": t_get_flood_stats, "find_buildings": t_find_buildings, "query_loans": t_query_loans,
        "explain_loan": t_explain_loan, "run_scenario": t_run_scenario, "get_validation": t_get_validation}


def call_tool(name, args, params):
    fn = IMPL.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**args, params=params)
    except Exception as ex:  # surfaced to the model / UI, never hidden
        return {"error": str(ex)}


def _public(result):
    return {k: v for k, v in result.items() if not k.startswith("_")}


def _summary(result):
    s = json.dumps(_public(result), ensure_ascii=False)
    return s[:220] + ("…" if len(s) > 220 else "")


# ------------------------------------------------------------------ Claude planner
SYSTEM = """You are CLIMAX, a climate-credit risk analyst for UAE banks and the CBUAE.
You answer ONLY with numbers returned by tools; never estimate or invent figures. Use tools first.
Data facts: flood extent and persistence come from Sentinel-2 (MNDWI) over Dubai after the 16 April 2024 storm;
depth is an indicative DEM-based estimate; buildings are real OpenStreetMap footprints; LOANS ARE SYNTHETIC.
If manifest mode is TEST, say clearly the data is test data. Reply in the user's language (Arabic if they write Arabic).
Be brief: 2-4 sentences, then at most 5 bullet points. Mention loan ids so the map can highlight them."""


def _env(key):
    from server import env  # lazy import, avoids cycle at module load
    return os.environ.get(key) or env().get(key, "")


def llm_available():
    # Public demos use the auditable offline parser unless explicitly opted in.
    if os.environ.get("CLIMAX_PUBLIC", "0") == "1" and os.environ.get("CLIMAX_ENABLE_PUBLIC_LLM", "0") != "1":
        return False
    return bool(_env("ANTHROPIC_API_KEY"))


def ask_claude(question, aoi, params):
    key = _env("ANTHROPIC_API_KEY"); model = _env("CLIMAX_MODEL") or "claude-sonnet-5-5"
    msgs = [{"role": "user", "content": f"Current map area: {aoi}. Data mode: {engine.manifest().get('mode')}.\nQuestion: {question}"}]
    steps, hl_b, hl_l, scenario = [], set(), set(), None
    for _ in range(6):
        body = json.dumps({"model": model, "max_tokens": 900, "system": SYSTEM, "tools": TOOLS, "messages": msgs}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read())
        msgs.append({"role": "assistant", "content": resp["content"]})
        uses = [c for c in resp["content"] if c["type"] == "tool_use"]
        if not uses:
            text = "".join(c.get("text", "") for c in resp["content"] if c["type"] == "text")
            return {"answer": text, "steps": steps, "highlight": {"buildings": sorted(hl_b)[:600], "loans": sorted(hl_l)},
                    "scenario": scenario, "engine": f"claude · {model}"}
        results = []
        for u in uses:
            res = call_tool(u["name"], u["input"], params)
            hl_b.update(res.get("_highlight_buildings", [])); hl_l.update(res.get("_highlight_loans", []))
            scenario = res.get("_scenario", scenario)
            steps.append({"tool": u["name"], "input": u["input"], "result": _summary(res)})
            results.append({"type": "tool_result", "tool_use_id": u["id"], "content": json.dumps(_public(res), ensure_ascii=False)[:12000]})
        msgs.append({"role": "user", "content": results})
    return {"answer": "Stopped after 6 tool rounds.", "steps": steps, "highlight": {"buildings": sorted(hl_b), "loans": sorted(hl_l)},
            "scenario": scenario, "engine": f"claude · {model}"}


# ------------------------------------------------------------------ offline parser (EN + AR)
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _aed(x):
    return f"AED {x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"AED {x:,.0f}"


def ask_offline(question, aoi, params):
    q = question.translate(AR_DIGITS); ql = q.lower()
    test = engine.manifest().get("mode") == "TEST"
    NOTE_AR = "تنبيه: بيانات اختبار وليست رصداً فضائياً." if test else "القروض اصطناعية؛ المباني والمياه مقاسة من القمر الصناعي."
    NOTE_EN = "Warning: TEST data, not satellite observations." if test else "Loans are synthetic; buildings and water are satellite-measured."
    ar = bool(re.search(r"[؀-ۿ]", q))
    for a, words in AOI_WORDS.items():
        if any(w in ql for w in words):
            aoi = a
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:days?|d\b|يوم|أيام|ايام)", ql)
    min_days = float(m.group(1)) if m else 0
    uninsured = bool(re.search(r"uninsur|no insurance|without insurance|غير مؤمن|بدون تأمين|غير المؤمن", ql))
    use = "warehouse" if re.search(r"warehouse|مستودع|مخزن", ql) else "industrial" if re.search(r"industr|factory|مصنع|صناعي", ql) else None
    channel = "DUAL" if re.search(r"dual|both|كلا|القناتين", ql) else "COLLATERAL" if re.search(r"collateral|pledg|رهن|مرهون|ضمان", ql) else None
    steps, results = [], []

    def run(name, args):
        res = call_tool(name, args, params); steps.append({"tool": name, "input": args, "result": _summary(res)})
        results.append(res); return res

    loan_m = re.search(r"sme-?\s?(\d{1,3})", ql)
    if loan_m:
        res = run("explain_loan", {"loan_id": f"SME-{int(loan_m.group(1)):03d}"})
        if "error" in res:
            ans = res["error"]
        else:
            head = (f"{res['loan_id']} ({res['sector']}, قناة {res['channel']}): التغير في الخسارة المتوقعة {_aed(res['delta_el'])}." if ar else
                    f"{res['loan_id']} ({res['sector']}, {res['channel']} channel): stressed expected-loss change {_aed(res['delta_el'])}.")
            ans = head + "\n" + "\n".join("• " + w for w in res["why"])
    elif re.search(r"accura|iou|valid|predict|forecast|دقة|التنبؤ|توقع", ql):
        v = run("get_validation", {"aoi": aoi}); h = v["holdout"]; r = v["random_baseline_holdout"]
        ans = (f"توقع التضاريس فقط مقابل ما رآه القمر الصناعي (منطقة اختبار منفصلة): IoU {h['iou']:.2f}، الدقة {h['precision']:.2f}، الاستدعاء {h['recall']:.2f}. خريطة عشوائية: IoU {r['iou']:.2f}." if ar else
               f"Terrain-only forecast vs what the satellite saw, on a held-out half of the map: IoU {h['iou']:.2f}, precision {h['precision']:.2f}, recall {h['recall']:.2f}. A random map scores IoU {r['iou']:.2f}. That gap is why we measure, not just model.")
    elif re.search(r"scenario|next storm|1\.\d|stress|longer|العاصفة القادمة|سيناريو|أطول", ql):
        mult = re.search(r"(\d\.\d+)\s*[x×]?", ql); k = float(mult.group(1)) if mult else 1.3
        res = run("run_scenario", {"persist_mult": k, "depth_mult": k})
        ans = (f"إذا بقيت المياه {k}× أطول وأعمق: تتغير الخسارة المتوقعة من {_aed(res['baseline_delta_el'])} إلى {_aed(res['scenario_delta_el'])} (+{_aed(res['increase_aed'])})." if ar else
               f"If water stays {k}× longer and {k}× deeper than April 2024, the stressed expected-loss change moves from {_aed(res['baseline_delta_el'])} to {_aed(res['scenario_delta_el'])} (+{_aed(res['increase_aed'])}).")
    elif re.search(r"loan|exposure|portfolio|loss|bank|قرض|قروض|محفظة|خسارة|تمويل|مرهون|رهن|ضمان", ql) or uninsured or channel:
        res = run("query_loans", {"aoi": aoi, "channel": channel or "ANY", "min_days": min_days, "uninsured_only": uninsured, "ops_use": use})
        tops = ", ".join(f"{t['loan_id']} ({_aed(t['delta_el'])})" for t in res["top"][:4])
        ans = (f"{res['matches']} قرضاً تطابق (تعرض {_aed(res['ead_aed'])}). التغير في الخسارة المتوقعة: {_aed(res['delta_el_aed'])}. الأعلى: {tops}. {NOTE_AR}" if ar else
               f"{res['matches']} loans match (exposure {_aed(res['ead_aed'])}); stressed expected-loss change {_aed(res['delta_el_aed'])}. Top: {tops}. {NOTE_EN}")
    else:
        res = run("find_buildings", {"aoi": aoi, "min_days": min_days, "use": use})
        st = run("get_flood_stats", {"aoi": aoi})["stats"]
        ans = (f"{res['count']} مبنى {('(' + use + ') ') if use else ''}كانت المياه حولها{(' ' + str(int(min_days)) + ' يوماً على الأقل') if min_days else ''}. إجمالي المساحة المغمورة {st['flooded_km2']} كم²." if ar else
               f"{res['count']} {use + ' ' if use else ''}buildings had water around them{(' for ≥ ' + str(int(min_days)) + ' days') if min_days else ''}. Total flooded area {st['flooded_km2']} km².")
    hl_b, hl_l, scen = set(), set(), None
    for res in results:
        hl_b.update(res.get("_highlight_buildings", [])); hl_l.update(res.get("_highlight_loans", []))
        scen = res.get("_scenario") or scen
    return {"answer": ans, "steps": steps, "highlight": {"buildings": sorted(hl_b)[:600], "loans": sorted(hl_l)},
            "scenario": scen, "engine": "offline parser (no API key)", "aoi": aoi}


def ask(question, aoi="alquoz", params=None):
    question = (question or "").strip()[:500]
    if not question:
        return {"answer": "Ask a question.", "steps": [], "highlight": {"buildings": [], "loans": []}, "engine": "none"}
    if llm_available():
        try:
            return ask_claude(question, aoi, params)
        except Exception as ex:
            out = ask_offline(question, aoi, params)
            out["engine"] = f"offline parser (Claude call failed: {type(ex).__name__})"
            return out
    return ask_offline(question, aoi, params)
