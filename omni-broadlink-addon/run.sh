#!/bin/sh
echo "[Omni Broadlink Add-on] Starting service..."

# Ensure data directory exists
mkdir -p /data

# Run FastAPI server with Uvicorn
exec python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000
