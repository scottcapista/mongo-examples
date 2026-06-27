#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Run scripts/local-setup.sh first."
  exit 1
fi

"$ROOT/scripts/stop-local.sh"

source .venv/bin/activate
set -a
source .env
set +a

export IS_LOCAL="${IS_LOCAL:-true}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export FASTMCP_STATELESS_HTTP=1

echo "==> Checking Atlas connectivity (port 27017)..."
python3 - <<'PY'
import os
import sys

from pymongo import MongoClient

user = os.environ["MONGO_USERNAME"]
pwd = os.environ["MONGO_PASSWORD"]
host = os.environ["MONGO_URL"]
uri = f"mongodb+srv://{user}:{pwd}@{host}/?serverSelectionTimeoutMS=10000"

try:
    MongoClient(uri).admin.command("ping")
except Exception as exc:
    print(f"ERROR: Cannot reach Atlas cluster ({host}): {exc}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Common fixes:", file=sys.stderr)
    print("  - Disable Cloudflare WARP / VPN (blocks outbound :27017)", file=sys.stderr)
    print("  - Atlas → Network Access → add your current public IP", file=sys.stderr)
    print("  - Resume the cluster if it is paused", file=sys.stderr)
    sys.exit(1)

print("Atlas connectivity OK")
PY

echo "==> Starting MCP server on :8000"
fastapi run mongo_mcp.py --host 0.0.0.0 --port 8000 &
MCP_PID=$!

cleanup() {
  kill "$MCP_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Waiting for MCP health on :8000 (up to 120s)..."
deadline=$((SECONDS + 120))
until curl -sf --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; do
  if ! kill -0 "$MCP_PID" 2>/dev/null; then
    echo "ERROR: MCP server exited during startup. Check logs above."
    exit 1
  fi
  if (( SECONDS >= deadline )); then
    echo "ERROR: MCP server did not become healthy within 120s."
    echo "       If MongoDB is slow, retry after fixing network access."
    exit 1
  fi
  sleep 2
done
echo "MCP server ready"

echo "==> Starting Web UI on :8001"
cd webui
# Avoid Flask debug reloader spawning a second process on the same port.
export FLASK_DEBUG="${FLASK_DEBUG:-0}"
python app.py
