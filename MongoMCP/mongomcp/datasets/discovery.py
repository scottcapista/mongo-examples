"""Discover cluster collections and register them as admin datasets."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import json_util

from ..mongodb_client import MongoDBClient
from .constants import (
    DATASETS_COL,
    DISCOVERY_OWNER,
    EXCLUDED_COLLECTION_PREFIXES,
    EXCLUDED_DATABASES,
    SOURCE_CLUSTER,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _should_skip_database(db_name: str) -> bool:
    return db_name.lower() in EXCLUDED_DATABASES


def _should_skip_collection(coll_name: str) -> bool:
    if coll_name.startswith(EXCLUDED_COLLECTION_PREFIXES):
        return True
    return False


def _classify_search_index(index_doc: Dict[str, Any]) -> str:
    """Return search | vector | unknown for an Atlas search index definition."""
    definition = index_doc.get("latestDefinition") or index_doc.get("definition") or {}
    mappings = definition.get("mappings") or {}
    fields = mappings.get("fields") or {}
    for field_def in fields.values():
        if not isinstance(field_def, dict):
            continue
        if field_def.get("type") == "vector":
            return "vector"
        if field_def.get("type") in ("string", "autocomplete", "token", "document"):
            return "search"
    name = (index_doc.get("name") or "").lower()
    if "vector" in name:
        return "vector"
    return "search"


def collect_index_metadata(collection) -> Dict[str, Any]:
    """List database, search, and vector indexes for a collection."""
    database_indexes: List[Dict[str, Any]] = []
    search_indexes: List[Dict[str, Any]] = []
    vector_indexes: List[Dict[str, Any]] = []

    try:
        for idx in collection.list_indexes():
            database_indexes.append(
                {
                    "name": idx.get("name"),
                    "key": dict(idx.get("key") or {}),
                    "unique": bool(idx.get("unique")),
                    "sparse": bool(idx.get("sparse")),
                    "type": idx.get("type", "standard"),
                }
            )
    except Exception as exc:
        logger.warning("list_indexes failed for %s: %s", collection.full_name, exc)

    try:
        for sidx in collection.list_search_indexes():
            cleaned = json.loads(json_util.dumps(sidx))
            cleaned.pop("statusDetail", None)
            cleaned.pop("latestDefinitionVersion", None)
            kind = _classify_search_index(cleaned)
            entry = {
                "name": cleaned.get("name"),
                "type": cleaned.get("type"),
                "status": cleaned.get("status"),
                "kind": kind,
                "definition": cleaned.get("latestDefinition") or cleaned.get("definition"),
            }
            search_indexes.append(entry)
            if kind == "vector":
                vector_indexes.append(entry)
    except Exception as exc:
        logger.debug("list_search_indexes unavailable for %s: %s", collection.full_name, exc)

    summary = {
        "database_indexes": database_indexes,
        "search_indexes": search_indexes,
        "vector_indexes": vector_indexes,
        "database_index_count": len(database_indexes),
        "search_index_count": len(search_indexes),
        "vector_index_count": len(vector_indexes),
    }
    logger.info(
        "Indexes for %s: db=%s search=%s vector=%s",
        collection.full_name,
        summary["database_index_count"],
        summary["search_index_count"],
        summary["vector_index_count"],
    )
    return summary


def _sample_schema(collection, limit: int = 3) -> Dict[str, Any]:
    samples = []
    try:
        for doc in collection.find({}, limit=limit):
            samples.append(json.loads(json_util.dumps(doc)))
    except Exception:
        pass
    fields: Dict[str, str] = {}
    for doc in samples:
        if not isinstance(doc, dict):
            continue
        for key, value in doc.items():
            if key not in fields:
                fields[key] = type(value).__name__
    return {"fields": [{"name": k, "type": v} for k, v in sorted(fields.items())], "samples": samples}


def discover_cluster_datasets(
    settings,
    *,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Scan the connected cluster and upsert admin_datasets for each eligible collection.

    Skips databases: admin, local, config, mcp_config.
    """
    client_wrapper = MongoDBClient(settings)
    client_wrapper.sync_connect_to_mongodb()
    motor_client = client_wrapper.client

    config_db = getattr(settings, "mcp_config_db", "mcp_config")
    datasets_col = motor_client[config_db][DATASETS_COL]

    created = 0
    updated = 0
    skipped = 0
    errors: List[str] = []
    discovered: List[Dict[str, Any]] = []

    for db_name in sorted(motor_client.list_database_names()):
        if _should_skip_database(db_name):
            skipped += 1
            logger.info("Skipping excluded database: %s", db_name)
            continue

        db = motor_client[db_name]
        for coll_name in sorted(db.list_collection_names()):
            if _should_skip_collection(coll_name):
                continue

            full_name = f"{db_name}.{coll_name}"
            try:
                collection = db[coll_name]
                indexes = collect_index_metadata(collection)
                record_count = collection.estimated_document_count()
                schema = _sample_schema(collection)

                existing = datasets_col.find_one(
                    {
                        "source_type": SOURCE_CLUSTER,
                        "database": db_name,
                        "collection": coll_name,
                    }
                )
                if existing and not force_refresh:
                    # Still refresh indexes + counts on rediscovery passes.
                    pass

                now = _utcnow()
                doc = {
                    "name": full_name,
                    "description": (
                        f"Auto-discovered collection {full_name} "
                        f"({record_count} docs, {indexes['database_index_count']} db indexes, "
                        f"{indexes['vector_index_count']} vector, {indexes['search_index_count']} search)"
                    ),
                    "category": "config",
                    "owner": DISCOVERY_OWNER,
                    "source_type": SOURCE_CLUSTER,
                    "database": db_name,
                    "collection": coll_name,
                    "schema": schema,
                    "indexes": indexes,
                    "record_count": record_count,
                    "updated_at": now,
                }
                if existing:
                    datasets_col.update_one({"_id": existing["_id"]}, {"$set": doc})
                    updated += 1
                    doc["id"] = str(existing["_id"])
                else:
                    doc["created_at"] = now
                    result = datasets_col.insert_one(doc)
                    created += 1
                    doc["id"] = str(result.inserted_id)

                discovered.append(
                    {
                        "id": doc["id"],
                        "name": full_name,
                        "database": db_name,
                        "collection": coll_name,
                        "record_count": record_count,
                        "indexes": {
                            "database": indexes["database_index_count"],
                            "search": indexes["search_index_count"],
                            "vector": indexes["vector_index_count"],
                        },
                    }
                )
            except Exception as exc:
                msg = f"{full_name}: {exc}"
                logger.error("Discovery failed for %s", full_name, exc_info=True)
                errors.append(msg)

    summary = {
        "databases_scanned": len(motor_client.list_database_names()),
        "created": created,
        "updated": updated,
        "skipped_databases": skipped,
        "datasets": discovered,
        "errors": errors,
    }
    logger.info("Cluster dataset discovery complete: %s", json.dumps(summary, default=str))
    return summary


def index_context_for_query(indexes: Optional[Dict[str, Any]]) -> str:
    """Format index metadata as LLM-readable context for query construction."""
    if not indexes:
        return "No index metadata available for this dataset."

    lines = [
        "Use these indexes when building queries:",
        f"- Database indexes ({indexes.get('database_index_count', 0)}):",
    ]
    for idx in indexes.get("database_indexes") or []:
        lines.append(f"  - {idx.get('name')}: keys={idx.get('key')}")

    vectors = indexes.get("vector_indexes") or []
    if vectors:
        lines.append(f"- Vector search indexes ({len(vectors)}):")
        for idx in vectors:
            lines.append(f"  - {idx.get('name')}: use $vectorSearch or $search with vector mapping")

    vector_names = {v.get("name") for v in vectors}
    searches = [
        i for i in (indexes.get("search_indexes") or [])
        if i.get("name") not in vector_names
    ]
    if searches:
        lines.append(f"- Atlas Search indexes ({len(searches)}):")
        for idx in searches:
            lines.append(f"  - {idx.get('name')}: use $search stage")

    return "\n".join(lines)


def ensure_dataset_indexes(settings) -> None:
    """Ensure admin_datasets indexes including cluster discovery uniqueness."""
    from .constants import RECORDS_COL

    client_wrapper = MongoDBClient(settings)
    client_wrapper.sync_connect_to_mongodb()
    config_db = getattr(settings, "mcp_config_db", "mcp_config")
    col = client_wrapper.client[config_db][DATASETS_COL]
    col.create_index([("category", 1)])
    col.create_index([("owner", 1)])
    col.create_index([("source_type", 1)])
    col.create_index(
        [("database", 1), ("collection", 1)],
        unique=True,
        partialFilterExpression={"source_type": SOURCE_CLUSTER},
        name="cluster_dataset_unique",
    )
    records = client_wrapper.client[config_db][RECORDS_COL]
    records.create_index([("dataset_id", 1), ("row_index", 1)])
