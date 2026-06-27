#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  /opt/homebrew/bin/python3.12 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -q --upgrade pip setuptools wheel
pip install -q -e ./mongomcp
pip install -q -r requirements.txt

if [[ ! -f .env ]]; then
  echo "Create .env from .env.example first, then re-run."
  exit 1
fi

set -a
source .env
set +a

echo "==> Seeding mcp_config (memory indexes only; no Airbnb sample data)..."
python tools/mongosetup.py --load-tools --skip-airbnb | tee /tmp/mongosetup.log

TOKEN_LINE="$(rg 'AUTH_TOKEN = ' /tmp/mongosetup.log | tail -1 || true)"
if [[ -n "$TOKEN_LINE" ]]; then
  TOKEN="${TOKEN_LINE#AUTH_TOKEN = }"
  TOKEN="${TOKEN%\"}"
  TOKEN="${TOKEN#\"}"
  if rg -q '^MCP_AUTH_TOKEN=' .env; then
    sed -i '' "s|^MCP_AUTH_TOKEN=.*|MCP_AUTH_TOKEN=${TOKEN}|" .env
  else
    echo "MCP_AUTH_TOKEN=${TOKEN}" >> .env
  fi
  echo "==> Updated MCP_AUTH_TOKEN in .env"
fi

echo "==> Setup complete (memory layer ready on mcp_config)."
