"""List user-scoped memories for the admin UI."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mongomcp.memory.memservice import COLLECTION_EPISODIC, COLLECTION_SEMANTIC
from mongomcp.memory.mongo_helpers import strip_embedding
from mongomcp.mongodb_client import MongoDBClient

from dataset_service import sanitize_display_data
from local_settings import settings

VALID_COLLECTIONS = frozenset({"all", "episodic", "semantic"})


def _memory_db_name() -> str:
    return getattr(settings, "memory_db", "mcp_config")


def _get_db():
    client = MongoDBClient(settings)
    client.sync_connect_to_mongodb()
    return client.client[_memory_db_name()]


def _created_at_sort_key(value: Any) -> float:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1_000_000_000_000:
            return ts / 1000.0
        return ts
    return 0.0


def _serialize_memory(doc: Dict[str, Any], collection_name: str) -> Dict[str, Any]:
    cleaned = strip_embedding(doc, collection_name)
    return sanitize_display_data(cleaned)


def list_user_memories(
    username: str,
    *,
    page: int = 1,
    limit: int = 20,
    collection: str = "all",
    memory_type: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return paginated memories owned by *username* across episodic/semantic stores."""
    if not username:
        raise ValueError("username required")

    page = max(1, page)
    limit = max(1, min(limit, 100))
    collection = collection if collection in VALID_COLLECTIONS else "all"

    mongo_filter: Dict[str, Any] = {"username": username}
    if memory_type:
        mongo_filter["memory_type"] = memory_type
    if session_id:
        mongo_filter["session_id"] = session_id

    if collection == "episodic":
        target_collections = [COLLECTION_EPISODIC]
    elif collection == "semantic":
        target_collections = [COLLECTION_SEMANTIC]
    else:
        target_collections = [COLLECTION_EPISODIC, COLLECTION_SEMANTIC]

    db = _get_db()
    all_docs: List[Dict[str, Any]] = []
    for coll_name in target_collections:
        col = db[coll_name]
        for doc in col.find(mongo_filter, projection={"embedding": 0}):
            doc["_src_col"] = coll_name
            all_docs.append(doc)

    all_docs.sort(
        key=lambda d: _created_at_sort_key(d.get("created_at")),
        reverse=True,
    )

    total = len(all_docs)
    total_pages = max(1, math.ceil(total / limit)) if total else 1
    start = (page - 1) * limit
    page_docs = all_docs[start : start + limit]

    records = []
    for idx, doc in enumerate(page_docs):
        coll_name = doc.pop("_src_col", COLLECTION_EPISODIC)
        records.append({
            "row_index": start + idx,
            "collection": coll_name,
            "data": _serialize_memory(doc, coll_name),
        })

    return {
        "username": username,
        "records": records,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "filters": {
            "collection": collection,
            "memory_type": memory_type or "",
            "session_id": session_id or "",
        },
    }
