#!/usr/bin/env python3
"""Idempotently seed training_mode_instructions strategy (scope=0) in memory_semantic."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_settings import settings  # noqa: E402
from mongomcp.llm_factory import create_webui_llm_client  # noqa: E402
from mongomcp.memory.memservice import COLLECTION_STRATEGIES, MemoryService  # noqa: E402
from mongomcp.mongodb_client import MongoDBClient  # noqa: E402

STRATEGY_NAME = "training_mode_instructions"
STRATEGY_CONTENT = """# Training mode instructions

When training mode is active, the user speaks on behalf of the entire organization.

Rules:
- Generalize all strategies and playbooks for every user — never optimize for one person.
- Replace PII with typed placeholders ([person name], [location], [email], etc.).
- Do not store user_preference or other per-user episodic memories during training.
- Prefer memory_strategy_store with scope=0 for durable org-wide playbooks.
- Use clear, reusable steps and tool-call patterns that transfer across sessions.
"""


async def seed(*, dry_run: bool = False) -> None:
    llm_client = create_webui_llm_client(settings)
    memory_db = getattr(settings, "memory_db", "mcp_config")
    query_model = getattr(settings, "QUERY_EMBEDDING_MODEL_ID", None)
    agent_instructions = getattr(settings, "agent_instructions", "")
    db_client = MongoDBClient(settings)
    svc = MemoryService(
        db_client=db_client,
        llm_client=llm_client,
        memory_db_name=memory_db,
        query_embedding_model_id=query_model,
        agent_instructions=agent_instructions,
    )
    await svc._ensure_connected()
    col = svc._col(COLLECTION_STRATEGIES)
    existing = await col.find_one({"strategy_key": STRATEGY_NAME, "scope": 0})
    if existing:
        print(f"Strategy {STRATEGY_NAME!r} already exists (_id={existing['_id']}) — skipping.")
        return
    if dry_run:
        print(f"Would insert strategy {STRATEGY_NAME!r} (scope=0).")
        return
    result = await svc.strategy_store(
        name=STRATEGY_NAME,
        context=STRATEGY_CONTENT,
        scope=0,
        importance=0.98,
        decay_rate=0.001,
        memory_type="strategy",
        username="seed-script",
    )
    print(f"Inserted {STRATEGY_NAME!r}: {result}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Check only; do not write.")
    args = parser.parse_args()
    asyncio.run(seed(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
