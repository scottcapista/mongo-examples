"""Dataset list and query operations (upload + cluster-backed)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Union

from bson import ObjectId, json_util

from ..mongodb_client import MongoDBClient
from .constants import DATASETS_COL, RECORDS_COL, SOURCE_CLUSTER, SOURCE_UPLOAD
from .discovery import index_context_for_query

logger = logging.getLogger(__name__)


def _get_client(settings) -> MongoDBClient:
    client = MongoDBClient(settings)
    client.sync_connect_to_mongodb()
    return client


def _serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(doc)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    for key in ("created_at", "updated_at", "discovered_at"):
        if key in out and hasattr(out[key], "isoformat"):
            out[key] = out[key].isoformat()
    if "dataset_id" in out and isinstance(out["dataset_id"], ObjectId):
        out["dataset_id"] = str(out["dataset_id"])
    return out


def _resolve_dataset(datasets_col, dataset_id: Optional[str], dataset_name: Optional[str]) -> Optional[Dict[str, Any]]:
    if dataset_id:
        try:
            doc = datasets_col.find_one({"_id": ObjectId(dataset_id)})
        except Exception:
            doc = None
        if doc:
            return doc
    if dataset_name:
        doc = datasets_col.find_one({"name": dataset_name})
        if doc:
            return doc
        doc = datasets_col.find_one({"name": {"$regex": f"^{dataset_name}$", "$options": "i"}})
        if doc:
            return doc
    return None


def list_datasets(settings, *, source_type: Optional[str] = None) -> List[Dict[str, Any]]:
    client = _get_client(settings)
    config_db = getattr(settings, "mcp_config_db", "mcp_config")
    col = client.client[config_db][DATASETS_COL]
    query: Dict[str, Any] = {}
    if source_type:
        query["source_type"] = source_type
    docs = list(col.find(query).sort("name", 1))
    results = []
    for doc in docs:
        ser = _serialize_doc(doc)
        ser["index_summary"] = {
            "database": (doc.get("indexes") or {}).get("database_index_count", 0),
            "search": (doc.get("indexes") or {}).get("search_index_count", 0),
            "vector": (doc.get("indexes") or {}).get("vector_index_count", 0),
        }
        results.append(ser)
    return results


def query_dataset(
    settings,
    *,
    dataset_id: Optional[str] = None,
    dataset_name: Optional[str] = None,
    pipeline: Optional[List[Dict[str, Any]]] = None,
    filter: Optional[Dict[str, Any]] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Run a read query against a dataset.

    - cluster datasets: aggregate/find on database.collection
    - upload datasets: aggregate on admin_dataset_records scoped by dataset_id
    """
    if not dataset_id and not dataset_name:
        raise ValueError("dataset_id or dataset_name is required")

    if isinstance(pipeline, str):
        pipeline = json.loads(pipeline)
    if isinstance(filter, str):
        filter = json.loads(filter)

    limit = max(1, min(int(limit), 1000))

    client = _get_client(settings)
    config_db = getattr(settings, "mcp_config_db", "mcp_config")
    datasets_col = client.client[config_db][DATASETS_COL]

    ds = _resolve_dataset(datasets_col, dataset_id, dataset_name)
    if not ds:
        raise ValueError(f"Dataset not found: {dataset_id or dataset_name}")

    ds_id = str(ds["_id"])
    source_type = ds.get("source_type", SOURCE_UPLOAD)
    index_context = index_context_for_query(ds.get("indexes"))

    if source_type == SOURCE_CLUSTER:
        db_name = ds["database"]
        coll_name = ds["collection"]
        collection = client.client[db_name][coll_name]

        if pipeline:
            if not isinstance(pipeline, list):
                raise ValueError("pipeline must be a list of aggregation stages")
            final_pipeline = list(pipeline)
            if not any("$limit" in stage for stage in final_pipeline):
                final_pipeline.append({"$limit": limit})
            cursor = collection.aggregate(final_pipeline)
            results = json.loads(json_util.dumps(list(cursor)))
            mode = "aggregate"
        else:
            q = filter if isinstance(filter, dict) else {}
            cursor = collection.find(q).limit(limit)
            results = json.loads(json_util.dumps(list(cursor)))
            mode = "find"

        return {
            "dataset_id": ds_id,
            "dataset_name": ds.get("name"),
            "source_type": source_type,
            "database": db_name,
            "collection": coll_name,
            "mode": mode,
            "result_count": len(results),
            "results": results,
            "index_context": index_context,
            "query_hints": _query_hints(ds),
        }

    # Upload-backed dataset — query normalized records collection
    records_col = client.client[config_db][RECORDS_COL]
    ds_oid = ds["_id"]

    if pipeline:
        scoped = [{"$match": {"dataset_id": ds_oid}}] + list(pipeline)
        if not any("$limit" in stage for stage in scoped):
            scoped.append({"$limit": limit})
        cursor = records_col.aggregate(scoped)
        results = json.loads(json_util.dumps(list(cursor)))
        mode = "aggregate"
    else:
        q: Dict[str, Any] = {"dataset_id": ds_oid}
        if isinstance(filter, dict):
            q.update(filter)
        cursor = records_col.find(q).sort("row_index", 1).limit(limit)
        results = json.loads(json_util.dumps(list(cursor)))
        mode = "find"

    return {
        "dataset_id": ds_id,
        "dataset_name": ds.get("name"),
        "source_type": source_type,
        "mode": mode,
        "result_count": len(results),
        "results": results,
        "index_context": index_context,
        "query_hints": _query_hints(ds),
    }


def _query_hints(ds: Dict[str, Any]) -> List[str]:
    hints: List[str] = []
    indexes = ds.get("indexes") or {}
    if indexes.get("vector_index_count"):
        hints.append("Vector indexes available — prefer $vectorSearch or $search vector mapping for semantic queries.")
    if indexes.get("search_index_count"):
        hints.append("Atlas Search indexes available — use $search for full-text queries.")
    for idx in indexes.get("database_indexes") or []:
        key = idx.get("key") or {}
        if key:
            hints.append(f"Consider filtering/sorting on indexed fields: {key}")
    schema_fields = (ds.get("schema") or {}).get("fields") or []
    if schema_fields:
        names = [f.get("name") for f in schema_fields if f.get("name")][:12]
        if names:
            hints.append(f"Sample fields: {', '.join(names)}")
    return hints
