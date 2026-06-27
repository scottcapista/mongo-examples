#!/usr/bin/env bash
# Stop MongoMCP local dev servers bound to :8000 (MCP) and :8001 (Web UI).
set -euo pipefail

for port in 8000 8001; do
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "Stopping process(es) on :$port -> $pids"
    kill $pids 2>/dev/null || true
    sleep 1
    still=$(lsof -ti :"$port" 2>/dev/null || true)
    if [[ -n "$still" ]]; then
      kill -9 $still 2>/dev/null || true
    fi
  else
    echo "No process on :$port"
  fi
done
