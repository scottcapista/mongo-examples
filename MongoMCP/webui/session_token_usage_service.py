"""Time-series session token usage — one document per LLM API call."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from local_settings import settings
from mongomcp.mongodb_client import MongoDBClient

logger = logging.getLogger(__name__)

SESSION_TOKEN_USAGE_COL = "session_token_usage"
LLM_HISTORY_COL = "llm_history"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_db() -> MongoDBClient:
    client = MongoDBClient(settings)
    client.sync_connect_to_mongodb()
    return client


def ensure_session_token_usage_collection() -> None:
    """Create the time-series collection if it does not exist."""
    try:
        client = _get_db()
        db = client.db
        if SESSION_TOKEN_USAGE_COL in db.list_collection_names():
            return
        db.create_collection(
            SESSION_TOKEN_USAGE_COL,
            timeseries={
                "timeField": "timestamp",
                "metaField": "meta",
                "granularity": "seconds",
            },
        )
        logger.info("Created time-series collection %s", SESSION_TOKEN_USAGE_COL)
    except Exception:
        logger.warning("Could not ensure session_token_usage collection", exc_info=True)


def save_llm_history(
    *,
    user_id: Optional[str],
    username: Optional[str],
    session_id: Optional[str],
    source: str,
    model_id: str,
    user_input: str,
    response_text: Optional[str],
    jsondata: Any,
    history: Optional[List[Any]],
    usage: Optional[Dict[str, Any]],
    usage_calls: Optional[List[Dict[str, Any]]],
    status: str,
    error: Optional[str] = None,
) -> Optional[str]:
    """Persist a conversation snapshot to llm_history; return its string _id."""
    try:
        client = _get_db()
        coll = client.get_collection(LLM_HISTORY_COL)
        doc: Dict[str, Any] = {
            "source": source,
            "user_id": user_id,
            "username": username,
            "session_id": session_id,
            "model_id": model_id,
            "input": user_input,
            "response_text": response_text,
            "jsondata": jsondata,
            "history": history,
            "usage": usage,
            "usage_calls": usage_calls or [],
            "status": status,
            "agent_id": source,
            "tool_name": source,
            "prompt_name": "chat",
            "timestamp": _utcnow().isoformat(),
        }
        if error:
            doc["error"] = error
        result = coll.insert_one(doc)
        return str(result.inserted_id)
    except Exception:
        logger.warning("Failed to save llm_history snapshot", exc_info=True)
        return None


def record_session_token_usage(
    *,
    llm_history_id: Optional[str],
    user_id: Optional[str],
    username: Optional[str],
    session_id: Optional[str],
    model_id: str,
    source: str,
    usage_calls: Optional[List[Dict[str, Any]]],
    turn_error: Optional[str] = None,
) -> int:
    """Insert one time-series document per LLM API call. Returns rows inserted."""
    ensure_session_token_usage_collection()
    calls = list(usage_calls or [])
    if not calls and turn_error:
        calls = [{
            "iteration": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0,
            "status": "error",
            "error": turn_error,
        }]

    if not calls:
        return 0

    meta = {
        "username": username or "anonymous",
        "user_id": user_id or "",
        "session_id": session_id or "",
        "model_id": model_id,
        "source": source,
    }
    now = _utcnow()
    docs = []
    for call in calls:
        docs.append({
            "timestamp": now,
            "meta": meta,
            "llm_history_id": llm_history_id,
            "iteration": int(call.get("iteration", 0) or 0),
            "input_tokens": int(call.get("input_tokens", 0) or 0),
            "output_tokens": int(call.get("output_tokens", 0) or 0),
            "total_tokens": int(call.get("total_tokens", 0) or 0),
            "latency_ms": float(call.get("latency_ms", 0) or 0),
            "status": call.get("status") or "success",
            "error": call.get("error"),
        })

    try:
        client = _get_db()
        coll = client.get_collection(SESSION_TOKEN_USAGE_COL)
        if len(docs) == 1:
            coll.insert_one(docs[0])
        else:
            coll.insert_many(docs)
        return len(docs)
    except Exception:
        logger.warning("Failed to record session token usage", exc_info=True)
        return 0


def list_session_token_usage(
    *,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    llm_history_id: Optional[str] = None,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """Paginated query of per-LLM-call usage records."""
    ensure_session_token_usage_collection()
    filt: Dict[str, Any] = {}
    if username:
        filt["meta.username"] = username
    if user_id:
        filt["meta.user_id"] = user_id
    if session_id:
        filt["meta.session_id"] = session_id
    if llm_history_id:
        filt["llm_history_id"] = llm_history_id
    if from_ts or to_ts:
        ts_filt: Dict[str, Any] = {}
        if from_ts:
            ts_filt["$gte"] = from_ts
        if to_ts:
            ts_filt["$lte"] = to_ts
        filt["timestamp"] = ts_filt

    page = max(1, page)
    limit = max(1, min(limit, 200))
    skip = (page - 1) * limit

    client = _get_db()
    coll = client.get_collection(SESSION_TOKEN_USAGE_COL)
    total = coll.count_documents(filt)
    cursor = (
        coll.find(filt)
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
    )
    records = []
    for doc in cursor:
        row = dict(doc)
        if "_id" in row:
            row["id"] = str(row.pop("_id"))
        if "timestamp" in row and hasattr(row["timestamp"], "isoformat"):
            row["timestamp"] = row["timestamp"].isoformat()
        records.append(row)

    total_pages = max(1, (total + limit - 1) // limit)
    return {
        "records": records,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "filters": {
            "username": username,
            "user_id": user_id,
            "session_id": session_id,
            "llm_history_id": llm_history_id,
        },
    }


def aggregate_token_usage(
    *,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    bucket: str = "day",
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Roll up token usage over time buckets for a user."""
    ensure_session_token_usage_collection()
    unit = bucket if bucket in ("hour", "day", "month") else "day"

    match: Dict[str, Any] = {}
    if username:
        match["meta.username"] = username
    if user_id:
        match["meta.user_id"] = user_id
    if from_ts or to_ts:
        ts_filt: Dict[str, Any] = {}
        if from_ts:
            ts_filt["$gte"] = from_ts
        if to_ts:
            ts_filt["$lte"] = to_ts
        match["timestamp"] = ts_filt

    pipeline: List[Dict[str, Any]] = []
    if match:
        pipeline.append({"$match": match})
    pipeline.extend([
        {
            "$group": {
                "_id": {
                    "bucket": {"$dateTrunc": {"date": "$timestamp", "unit": unit}},
                    "username": "$meta.username",
                    "model_id": "$meta.model_id",
                },
                "input_tokens": {"$sum": "$input_tokens"},
                "output_tokens": {"$sum": "$output_tokens"},
                "total_tokens": {"$sum": "$total_tokens"},
                "call_count": {"$sum": 1},
                "error_count": {
                    "$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]},
                },
                "avg_latency_ms": {"$avg": "$latency_ms"},
            }
        },
        {"$sort": {"_id.bucket": -1}},
    ])

    client = _get_db()
    coll = client.get_collection(SESSION_TOKEN_USAGE_COL)
    buckets = []
    for row in coll.aggregate(pipeline):
        bucket_id = row.get("_id") or {}
        ts = bucket_id.get("bucket")
        buckets.append({
            "bucket": ts.isoformat() if hasattr(ts, "isoformat") else ts,
            "username": bucket_id.get("username"),
            "model_id": bucket_id.get("model_id"),
            "input_tokens": row.get("input_tokens", 0),
            "output_tokens": row.get("output_tokens", 0),
            "total_tokens": row.get("total_tokens", 0),
            "call_count": row.get("call_count", 0),
            "error_count": row.get("error_count", 0),
            "avg_latency_ms": round(row.get("avg_latency_ms") or 0, 1),
        })

    return {"buckets": buckets, "bucket_unit": unit, "filters": {"username": username, "user_id": user_id}}


def get_llm_history(llm_history_id: str) -> Optional[Dict[str, Any]]:
    """Fetch full llm_history document by id."""
    try:
        client = _get_db()
        coll = client.get_collection(LLM_HISTORY_COL)
        doc = coll.find_one({"_id": ObjectId(llm_history_id)})
        if not doc:
            return None
        out = dict(doc)
        out["id"] = str(out.pop("_id"))
        return out
    except Exception:
        logger.warning("Failed to fetch llm_history %s", llm_history_id, exc_info=True)
        return None
