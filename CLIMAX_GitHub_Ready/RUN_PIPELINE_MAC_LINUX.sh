#!/bin/sh
# One-time: download real Sentinel-2 / DEM / OSM data and compute everything (needs internet, ~5-15 min).
# Usage:  sh RUN_PIPELINE_MAC_LINUX.sh            (all three areas)
#         sh RUN_PIPELINE_MAC_LINUX.sh alquoz     (one area)
#         sh RUN_PIPELINE_MAC_LINUX.sh --offline  (re-analyse from the cache, no internet)
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements-pipeline.txt
python -m pipeline.run_all "$@"
python -m unittest discover -s tests -p "test_*.py"
echo ""
echo "Real data ready. Start the app with:  sh START_MAC_LINUX.sh"
