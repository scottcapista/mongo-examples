"""Time-series session token usage — one document per LLM API call."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from local_settings import settings
from mongomcp.model_pricing import estimate_cost_usd
from mongomcp.mongodb_client import MongoDBClient

logger = logging.getLogger(__name__)

SESSION_TOKEN_USAGE_COL = "session_token_usage"
SESSION_EVENTS_COL = "session_events"
LLM_HISTORY_COL = "llm_history"

EVENT_STRATEGY_RECALL = "strategy_recall"
EVENT_STRATEGY_STORE = "strategy_store"
EVENT_TOOL_CACHE_HIT = "tool_cache_hit"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row_estimated_cost_usd(
    *,
    model_id: Optional[str],
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> Optional[float]:
    cost = estimate_cost_usd(
        model_id=model_id or "",
        input_tokens=int(input_tokens or 0),
        output_tokens=int(output_tokens or 0),
        cache_read_input_tokens=int(cache_read_input_tokens or 0),
        cache_creation_input_tokens=int(cache_creation_input_tokens or 0),
    )
    if cost is None:
        return None
    return round(cost, 6)


def _attach_record_cost(row: Dict[str, Any]) -> None:
    meta = row.get("meta") or {}
    row["estimated_cost_usd"] = _row_estimated_cost_usd(
        model_id=meta.get("model_id"),
        input_tokens=row.get("input_tokens", 0),
        output_tokens=row.get("output_tokens", 0),
        cache_read_input_tokens=row.get("cache_read_input_tokens", 0),
        cache_creation_input_tokens=row.get("cache_creation_input_tokens", 0),
    )


def _sum_costs(costs: List[Optional[float]]) -> Optional[float]:
    values = [c for c in costs if c is not None]
    if not values:
        return None
    return round(sum(values), 6)


def _get_db() -> MongoDBClient:
    client = MongoDBClient(settings)
    client.sync_connect_to_mongodb()
    return client


def ensure_session_events_collection() -> None:
    """Create the session events time-series collection if it does not exist."""
    try:
        client = _get_db()
        db = client.db
        if SESSION_EVENTS_COL in db.list_collection_names():
            return
        db.create_collection(
            SESSION_EVENTS_COL,
            timeseries={
                "timeField": "timestamp",
                "metaField": "meta",
                "granularity": "seconds",
            },
        )
        logger.info("Created time-series collection %s", SESSION_EVENTS_COL)
    except Exception:
        logger.warning("Could not ensure session_events collection", exc_info=True)


def ensure_session_metrics_collections() -> None:
    ensure_session_token_usage_collection()
    ensure_session_events_collection()


def record_session_event(
    *,
    event_type: str,
    user_id: Optional[str],
    username: Optional[str],
    session_id: Optional[str],
    source: str = "webui",
    tool_name: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Record a single session-scoped event (strategy recall/store, tool cache hit, etc.)."""
    ensure_session_events_collection()
    meta = {
        "username": username or "anonymous",
        "user_id": user_id or "",
        "session_id": session_id or "",
        "event_type": event_type,
        "source": source,
    }
    doc: Dict[str, Any] = {
        "timestamp": _utcnow(),
        "meta": meta,
    }
    if tool_name:
        doc["tool_name"] = tool_name
    if detail:
        doc["detail"] = detail
    try:
        client = _get_db()
        client.get_collection(SESSION_EVENTS_COL).insert_one(doc)
    except Exception:
        logger.warning("Failed to record session event %s", event_type, exc_info=True)


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
            "cache_read_input_tokens": int(call.get("cache_read_input_tokens", 0) or 0),
            "cache_creation_input_tokens": int(call.get("cache_creation_input_tokens", 0) or 0),
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
        _attach_record_cost(row)
        records.append(row)

    page_cost = _sum_costs([r.get("estimated_cost_usd") for r in records])
    total_pages = max(1, (total + limit - 1) // limit)
    return {
        "records": records,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "totals": {"estimated_cost_usd": page_cost},
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
    session_id: Optional[str] = None,
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
    if session_id:
        match["meta.session_id"] = session_id
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
                "cache_read_input_tokens": {"$sum": "$cache_read_input_tokens"},
                "cache_creation_input_tokens": {"$sum": "$cache_creation_input_tokens"},
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
    bucket_costs: List[Optional[float]] = []
    for row in coll.aggregate(pipeline):
        bucket_id = row.get("_id") or {}
        ts = bucket_id.get("bucket")
        model_id = bucket_id.get("model_id")
        entry = {
            "bucket": ts.isoformat() if hasattr(ts, "isoformat") else ts,
            "username": bucket_id.get("username"),
            "model_id": model_id,
            "input_tokens": row.get("input_tokens", 0),
            "output_tokens": row.get("output_tokens", 0),
            "total_tokens": row.get("total_tokens", 0),
            "cache_read_input_tokens": row.get("cache_read_input_tokens", 0),
            "cache_creation_input_tokens": row.get("cache_creation_input_tokens", 0),
            "call_count": row.get("call_count", 0),
            "error_count": row.get("error_count", 0),
            "avg_latency_ms": round(row.get("avg_latency_ms") or 0, 1),
        }
        entry["estimated_cost_usd"] = _row_estimated_cost_usd(
            model_id=model_id,
            input_tokens=entry["input_tokens"],
            output_tokens=entry["output_tokens"],
            cache_read_input_tokens=entry["cache_read_input_tokens"],
            cache_creation_input_tokens=entry["cache_creation_input_tokens"],
        )
        bucket_costs.append(entry["estimated_cost_usd"])
        buckets.append(entry)

    return {
        "buckets": buckets,
        "bucket_unit": unit,
        "filters": {"username": username, "user_id": user_id, "session_id": session_id},
        "totals": {"estimated_cost_usd": _sum_costs(bucket_costs)},
    }


def list_recent_sessions(
    *,
    username: str,
    limit: int = 20,
) -> Dict[str, Any]:
    """Distinct session_ids with latest activity for a user."""
    ensure_session_metrics_collections()
    client = _get_db()
    usage_coll = client.get_collection(SESSION_TOKEN_USAGE_COL)
    pipeline = [
        {"$match": {"meta.username": username, "meta.session_id": {"$ne": ""}}},
        {"$group": {
            "_id": {
                "session_id": "$meta.session_id",
                "model_id": "$meta.model_id",
            },
            "last_seen": {"$max": "$timestamp"},
            "llm_calls": {"$sum": 1},
            "total_tokens": {"$sum": "$total_tokens"},
            "input_tokens": {"$sum": "$input_tokens"},
            "output_tokens": {"$sum": "$output_tokens"},
            "cache_read_input_tokens": {"$sum": "$cache_read_input_tokens"},
            "cache_creation_input_tokens": {"$sum": "$cache_creation_input_tokens"},
        }},
        {"$sort": {"last_seen": -1}},
    ]
    by_session: Dict[str, Dict[str, Any]] = {}
    for row in usage_coll.aggregate(pipeline):
        sid = (row.get("_id") or {}).get("session_id")
        if not sid:
            continue
        model_id = (row.get("_id") or {}).get("model_id")
        last = row.get("last_seen")
        cost = _row_estimated_cost_usd(
            model_id=model_id,
            input_tokens=row.get("input_tokens", 0),
            output_tokens=row.get("output_tokens", 0),
            cache_read_input_tokens=row.get("cache_read_input_tokens", 0),
            cache_creation_input_tokens=row.get("cache_creation_input_tokens", 0),
        )
        entry = by_session.setdefault(sid, {
            "session_id": sid,
            "last_seen": last,
            "llm_calls": 0,
            "total_tokens": 0,
            "estimated_cost_usd": None,
            "_cost_parts": [],
        })
        if last and (entry["last_seen"] is None or last > entry["last_seen"]):
            entry["last_seen"] = last
        entry["llm_calls"] += row.get("llm_calls", 0)
        entry["total_tokens"] += row.get("total_tokens", 0)
        entry["_cost_parts"].append(cost)

    sessions = []
    for entry in by_session.values():
        entry["estimated_cost_usd"] = _sum_costs(entry.pop("_cost_parts", []))
        last = entry.get("last_seen")
        entry["last_seen"] = last.isoformat() if hasattr(last, "isoformat") else last
        sessions.append(entry)
    sessions.sort(key=lambda s: s.get("last_seen") or "", reverse=True)
    return {"sessions": sessions[: max(1, min(limit, 50))]}


def aggregate_session_timeline(
    *,
    username: str,
    session_id: Optional[str] = None,
    bucket: str = "hour",
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Merge token usage and session events into one timeline for charting."""
    ensure_session_metrics_collections()
    unit = bucket if bucket in ("hour", "day", "month") else "hour"

    usage_match: Dict[str, Any] = {"meta.username": username}
    if session_id:
        usage_match["meta.session_id"] = session_id
    ts_filt: Optional[Dict[str, Any]] = None
    if from_ts or to_ts:
        ts_filt = {}
        if from_ts:
            ts_filt["$gte"] = from_ts
        if to_ts:
            ts_filt["$lte"] = to_ts
        usage_match["timestamp"] = ts_filt

    event_match: Dict[str, Any] = {"meta.username": username}
    if session_id:
        event_match["meta.session_id"] = session_id
    if ts_filt:
        event_match["timestamp"] = ts_filt

    client = _get_db()
    usage_coll = client.get_collection(SESSION_TOKEN_USAGE_COL)
    events_coll = client.get_collection(SESSION_EVENTS_COL)

    usage_pipeline: List[Dict[str, Any]] = [
        {"$match": usage_match},
        {"$group": {
            "_id": {
                "bucket": {"$dateTrunc": {"date": "$timestamp", "unit": unit}},
                "model_id": "$meta.model_id",
            },
            "total_tokens": {"$sum": "$total_tokens"},
            "input_tokens": {"$sum": "$input_tokens"},
            "output_tokens": {"$sum": "$output_tokens"},
            "cache_read_input_tokens": {"$sum": "$cache_read_input_tokens"},
            "cache_creation_input_tokens": {"$sum": "$cache_creation_input_tokens"},
            "llm_calls": {"$sum": 1},
        }},
    ]
    events_pipeline: List[Dict[str, Any]] = [
        {"$match": event_match},
        {"$group": {
            "_id": {
                "bucket": {"$dateTrunc": {"date": "$timestamp", "unit": unit}},
                "event_type": "$meta.event_type",
            },
            "count": {"$sum": 1},
        }},
    ]

    by_bucket: Dict[str, Dict[str, Any]] = {}

    def _bucket_key(ts: Any) -> str:
        if hasattr(ts, "isoformat"):
            return ts.isoformat()
        return str(ts)

    for row in usage_coll.aggregate(usage_pipeline):
        bucket_id = row.get("_id") or {}
        key = _bucket_key(bucket_id.get("bucket"))
        model_id = bucket_id.get("model_id")
        by_bucket.setdefault(key, {"bucket": key, "_cost_parts": []})
        pt = by_bucket[key]
        for field in (
            "total_tokens", "input_tokens", "output_tokens",
            "cache_read_input_tokens", "cache_creation_input_tokens", "llm_calls",
        ):
            pt[field] = pt.get(field, 0) + int(row.get(field, 0) or 0)
        pt["_cost_parts"].append(_row_estimated_cost_usd(
            model_id=model_id,
            input_tokens=row.get("input_tokens", 0),
            output_tokens=row.get("output_tokens", 0),
            cache_read_input_tokens=row.get("cache_read_input_tokens", 0),
            cache_creation_input_tokens=row.get("cache_creation_input_tokens", 0),
        ))

    for row in events_coll.aggregate(events_pipeline):
        bucket_id = row.get("_id") or {}
        key = _bucket_key(bucket_id.get("bucket"))
        event_type = bucket_id.get("event_type") or "unknown"
        by_bucket.setdefault(key, {"bucket": key})
        by_bucket[key][event_type] = by_bucket[key].get(event_type, 0) + row.get("count", 0)

    points = []
    for key in sorted(by_bucket.keys()):
        pt = by_bucket[key]
        cost_parts = pt.pop("_cost_parts", [])
        points.append({
            "bucket": pt.get("bucket", key),
            "total_tokens": pt.get("total_tokens", 0),
            "input_tokens": pt.get("input_tokens", 0),
            "output_tokens": pt.get("output_tokens", 0),
            "cache_read_input_tokens": pt.get("cache_read_input_tokens", 0),
            "cache_creation_input_tokens": pt.get("cache_creation_input_tokens", 0),
            "llm_calls": pt.get("llm_calls", 0),
            "estimated_cost_usd": _sum_costs(cost_parts),
            "strategy_recall": pt.get(EVENT_STRATEGY_RECALL, 0),
            "strategy_store": pt.get(EVENT_STRATEGY_STORE, 0),
            "tool_cache_hit": pt.get(EVENT_TOOL_CACHE_HIT, 0),
        })

    return {
        "points": points,
        "bucket_unit": unit,
        "filters": {"username": username, "session_id": session_id},
    }


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
