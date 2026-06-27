#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Run scripts/local-setup.sh first."
  exit 1
fi

source .venv/bin/activate
set -a
source .env
set +a

export IS_LOCAL="${IS_LOCAL:-true}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export FASTMCP_STATELESS_HTTP=1

echo "==> Starting MCP server on :8000"
fastapi run mongo_mcp.py --host 0.0.0.0 --port 8000 &
MCP_PID=$!

cleanup() {
  kill "$MCP_PID" 2>/dev/null || true
}
trap cleanup EXIT

sleep 3
echo "==> Starting Web UI on :8001"
cd webui
python app.py
