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

echo "==> Ensuring admin dataset indexes..."
python tools/setup_admin_datasets.py

echo "==> Creating local agent identity and JWT..."
python tools/generate_jwt_token.py --agent-name webui_chatuser | tee /tmp/local-setup-jwt.log

TOKEN_LINE="$(rg 'AUTH_TOKEN = ' /tmp/local-setup-jwt.log | tail -1 || true)"
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

echo "==> Setup complete (agent identity + dataset indexes on mcp_config)."
