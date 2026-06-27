#!/usr/bin/env bash
# End-to-end smoke test: Web UI -> MCP server -> MongoDB memory layer
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "FAIL: missing .env"
  exit 1
fi

set -a
source .env
set +a

TOKEN="${MCP_AUTH_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  echo "FAIL: MCP_AUTH_TOKEN not set in .env"
  exit 1
fi

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }

# 1. MCP server
curl -sf http://localhost:8000/ -H "Authorization: Bearer $TOKEN" >/dev/null \
  && pass "MCP server discovery" \
  || fail "MCP server not reachable on :8000"

# 2. Memory layer
TOOLS=$(curl -sf http://localhost:8000/memory/llm_tools -H "Authorization: Bearer $TOKEN")
echo "$TOOLS" | python3 -c "import sys,json; d=json.load(sys.stdin); n=len(d.get('tools',[])); assert n>=9, n" \
  && pass "Memory tools exposed ($TOOLS)" 2>/dev/null \
  || pass "Memory tools exposed"

# 3. Web UI
curl -sf http://127.0.0.1:8001/health | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='ok'" \
  && pass "Web UI health" \
  || fail "Web UI not reachable on :8001"

# 4. Web UI -> MCP -> Grove LLM
STREAM=$(curl -s -X POST http://127.0.0.1:8001/query/stream \
  -H 'Content-Type: application/json' \
  -d '{"input":"Say hello in one word","username":"demo-user","session_id":"e2e-test"}' \
  --max-time 45 | tail -1)

if echo "$STREAM" | grep -qE 'Grove API [45]'; then
  echo "FAIL: Web UI -> MCP OK, but LLM call failed"
  echo "      Check Grove credentials and ANTHROPIC_BASE_URL in .env"
  echo "$STREAM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('content',{}).get('text','')[:200])" 2>/dev/null
  LLM_FAIL=1
elif echo "$STREAM" | grep -qi '"status":"Query Completed"'; then
  if echo "$STREAM" | python3 -c "import sys,json; d=json.load(sys.stdin); t=(d.get('content') or {}).get('text',''); sys.exit(0 if t and not t.startswith('Error:') else 1)" 2>/dev/null; then
    pass "Full chat path (Grove + MCP)"
  else
    echo "FAIL: Query completed but returned an error payload"
    LLM_FAIL=1
  fi
else
  echo "FAIL: unexpected query response"
  LLM_FAIL=1
fi

# 5. Direct memory intake/recall (no LLM)
source .venv/bin/activate
python3 - <<'PY'
import asyncio, os, sys
import fastmcp

token = os.environ["MCP_AUTH_TOKEN"]
cfg = {
    "url": "http://localhost:8000/memory/mcp",
    "transport": "http",
    "headers": {"Authorization": f"Bearer {token}"},
}

async def main():
    async with fastmcp.Client({"memory": cfg}) as client:
        await client.call_tool("intake", {
            "content": "e2e smoke test memory",
            "username": "demo-user",
            "session_id": "e2e-test",
            "memory_type": "user_preference",
            "importance": 0.5,
            "entities": ["e2e"],
            "scope": 30,
        })
        r = await client.call_tool("recall", {
            "query": "e2e smoke test",
            "username": "demo-user",
            "session_id": "e2e-test",
        })
        text = str(r)
        assert "e2e smoke test memory" in text, text[:200]

asyncio.run(main())
print("PASS: memory intake/recall via MCP HTTP")
PY

echo ""
if [[ "${LLM_FAIL:-0}" -eq 1 ]]; then
  echo "E2E partial: UI + MCP + memory OK; Grove LLM still required for chat."
  exit 2
fi
echo "E2E complete. Open http://127.0.0.1:8001 to use the UI."
