"""CLIMAX local server. Python standard library only. Serves the app, pipeline outputs and the API."""
from __future__ import annotations
import json
import os
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import engine  # noqa: E402

BLOCKED_DIRS = {"private", "tests", "__pycache__", ".git", "pipeline", "cache", "legacy", "evidence"}


def env():
    vals = {}
    p = ROOT / "private" / ".env.local"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def params_from(q):
    return {k: q[k][0] for k in engine.DEFAULTS if k in q}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *a):
        pass

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def send_body(self, body: bytes, ctype: str, status=200, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, o, status=200, extra=None):
        self.send_body(json.dumps(o, ensure_ascii=False).encode(), "application/json; charset=utf-8", status, extra)

    def api(self, path, q, body=None):
        import agent, memo
        if path == "/api/health":
            return self.send_json({"ok": True, "service": "CLIMAX", "data": engine.available()})
        if not engine.available():
            return self.send_json({"error": "No data yet. Run: python3 -m pipeline.make_test_data (test) or python3 -m pipeline.run_all (real)."}, 503)
        if path == "/api/config":
            m = engine.manifest()
            return self.send_json({"mode": m.get("mode"), "generated_at": m.get("generated_at"), "aois": m.get("aois", []),
                                   "llm": agent.llm_available(), "model": (os.environ.get("CLIMAX_MODEL") or env().get("CLIMAX_MODEL") or "claude-sonnet-5-5") if agent.llm_available() else None,
                                   "defaults": engine.DEFAULTS, "limits": engine.LIMITS, "sources": engine.SOURCES,
                                   "cesiumToken": os.environ.get("CESIUM_ION_TOKEN") or env().get("CESIUM_ION_TOKEN", ""),
                                   "gov": engine.gov(), "detection": {a: engine.detection(a) for a in m.get("aois", [])}})
        if path == "/api/log":
            return self.send_json(engine.manifest().get("log", []))
        if path.startswith("/api/aoi/"):
            a = path.rsplit("/", 1)[1]
            if a not in engine.manifest().get("aois", []):
                return self.send_json({"error": "unknown area"}, 404)
            return self.send_json({**engine.meta(a), "base": f"data/generated/{a}/"})
        if path == "/api/stress":
            return self.send_json(engine.stress(params_from(q), q.get("aoi", [None])[0]))
        if path.startswith("/api/loan/"):
            r = engine.explain(path.rsplit("/", 1)[1], params_from(q))
            return self.send_json(r or {"error": "unknown loan"}, 200 if r else 404)
        if path == "/api/memo":
            html = memo.build(params_from(q), q.get("aoi", [None])[0]).encode()
            return self.send_body(html, "text/html; charset=utf-8",
                                  extra={"Content-Disposition": 'inline; filename="CLIMAX_risk_memo.html"'})
        if path == "/api/export":
            s = engine.stress(params_from(q))
            out = {"manifest": {k: v for k, v in engine.manifest().items() if k != "log"},
                   "areas": {a: engine.meta(a) for a in engine.manifest().get("aois", [])}, "stress": s, "sources": engine.SOURCES,
                   "gov_open_data": engine.gov(), "proposed_asset_hazard_record": engine.ASSET_HAZARD_SCHEMA}
            return self.send_json(out, extra={"Content-Disposition": 'attachment; filename="CLIMAX_audit.json"'})
        if path == "/api/ask" and body is not None:
            return self.send_json(agent.ask(body.get("q", ""), body.get("aoi", "alquoz"), body.get("params")))
        return self.send_json({"error": "not found"}, 404)

    def do_GET(self):
        p = urlsplit(self.path); q = parse_qs(p.query)
        if p.path.startswith("/api/"):
            try:
                return self.api(p.path, q)
            except ValueError as ex:
                return self.send_json({"error": str(ex)}, 400)
            except Exception as ex:
                return self.send_json({"error": f"{type(ex).__name__}: {ex}"}, 500)
        # Serve only the application and prebuilt public mapping assets. In
        # particular, no source files, keys, notebooks, docs, or directory listings.
        decoded = unquote(p.path)
        parts = decoded.split("/")
        permitted = decoded in ("/", "/index.html") or (
            not decoded.endswith("/") and
            (decoded.startswith("/assets/") or decoded.startswith("/data/generated/"))
        )
        if (not permitted or any(x in BLOCKED_DIRS or x.startswith(".") or x == ".." for x in parts if x)):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        p = urlsplit(self.path)
        try:
            n = min(int(self.headers.get("Content-Length", 0)), 20000)
            body = json.loads(self.rfile.read(n) or b"{}")
            return self.api(p.path, {}, body)
        except ValueError as ex:
            return self.send_json({"error": str(ex)}, 400)
        except Exception as ex:
            return self.send_json({"error": f"{type(ex).__name__}: {ex}"}, 500)


def main():
    port = int(os.environ.get("PORT", "5173"))
    if not engine.available():
        print("No pipeline outputs found. Generating labelled TEST data first…", flush=True)
        from pipeline import make_test_data
        make_test_data.main()
    host = os.environ.get("HOST", "127.0.0.1")
    s = ThreadingHTTPServer((host, port), Handler)
    print(f"CLIMAX ready · {host}:{port}  (data mode: {engine.manifest().get('mode')})", flush=True)
    if "--no-browser" not in sys.argv:
        threading.Timer(0.7, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        s.server_close()


if __name__ == "__main__":
    main()
