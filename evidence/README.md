# Reference audit (not wired into the demo)

`REAL_run_audit_REFERENCE.json` was provided separately with this project. Its manifest describes an April 2024 Sentinel-2-based REAL pipeline run across Al Quoz, DXB, and Jebel Ali, with synthetic loans linked to real building footprints.

**Do not swap it into `data/generated/manifest.json` or present the shipped dashboard as REAL.** The ZIP shipped with TEST imagery, TEST building layers, and TEST loan data, which are not spatially consistent with this standalone audit. To obtain a genuinely REAL dashboard, rerun `RUN_PIPELINE_WINDOWS.bat` on a Windows machine with internet and publish the full newly generated `data/generated/` directory together.

The audit is supplied for independent examination, not an independently reproduced result of this checkout.
