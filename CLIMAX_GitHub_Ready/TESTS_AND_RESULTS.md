# Verification record · CLIMAX GitHub-ready demo

The included `data/generated/manifest.json` is **TEST**. The independent `evidence/REAL_run_audit_REFERENCE.json` describes a separate REAL run, which is not spatially interchangeable with bundled layers.

```bash
python -m unittest discover -s tests -p "test_*.py"
python tests/browser_check.py  # optional, needs Playwright / Chromium
```

- **Python tests:** 23 passed on the inspected archive before public packaging; rerun against the prepared package below.
- **Server smoke:** `/api/health`, `/api/config`, `/api/stress`, `/api/ask`, static assets, and blocked local secret routes checked in the prepared package.
- **Rendering:** JavaScript syntax checks passed. Full Chromium rendering could not be verified because the container browser blocked loopback navigation (`ERR_BLOCKED_BY_ADMINISTRATOR`); test in Chrome on Windows before sharing the site.
- **Not yet verified:** fetching live Sentinel scenes / gov CSV for this prepared package, actual Cesium ion imagery under a valid token, and a live Render deployment.

Known limitations: optical measurements are cloud-limited; depth is indicative; 140-reference-audit loans and all demo loans are synthetic; forecast IoU in the separate REAL audit is low (0.051–0.111), so this is a decision-support exploration, not a verified forecast.
