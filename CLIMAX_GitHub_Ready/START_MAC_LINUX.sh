#!/bin/sh
# Start the CLIMAX app (no installs needed). Opens http://127.0.0.1:5173
cd "$(dirname "$0")"
python3 server.py
