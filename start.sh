#!/bin/bash
# Claude Chat Viewer — Launcher
cd "$(dirname "$0")"
echo "Starting Claude Chat Viewer..."
python3 server.py "$@"
