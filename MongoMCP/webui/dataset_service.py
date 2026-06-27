"""Admin dataset upload, schema inference, and CRUD."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import random
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from bson import ObjectId

from local_settings import settings
from mongomcp.llm_factory import create_webui_llm_client
from mongomcp.mongodb_client import MongoDBClient

logger = logging.getLogger(__name__)

DATASETS_COL = "admin_datasets"
RECORDS_COL = "admin_dataset_records"
CATEGORIES = frozenset({"growth", "config", "personalization"})
MAX_RECORDS = 10_000
BATCH_SIZE = 100
SAMPLE_SIZE = 15
SAMPLE_TRUNCATE = 2048
FIELD_VALUE_MAX = 10_240

SCHEMA_SYSTEM = """You infer a normalized document schema for a dataset being loaded into MongoDB.
Return ONLY valid JSON with this shape (no markdown fences):
{
  "fields": [{"name": "string", "type": "string|number|boolean|array|object", "description": "string"}],
  "sample_records": [ { ... normalized objects using consistent field names ... } ]
}
Rules:
- Use snake_case field names.
- All records in the dataset should share the same top-level fields.
- Coerce types consistently (numbers as numbers, booleans as booleans).
- sample_records must contain one normalized object per input sample, same order.
- Do not invent fields not supported by the samples."""

SCHEMA_RETRY_SYSTEM = SCHEMA_SYSTEM + "\nReturn ONLY raw JSON. No explanation text."


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_db() -> MongoDBClient:
    client = MongoDBClient(settings)
    client.sync_connect_to_mongodb()
    return client


def _oid(value: str) -> ObjectId:
    return ObjectId(value)


def _serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(doc)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    if "dataset_id" in out and isinstance(out["dataset_id"], ObjectId):
        out["dataset_id"] = str(out["dataset_id"])
    for key in ("created_at", "updated_at"):
        if key in out and hasattr(out[key], "isoformat"):
            out[key] = out[key].isoformat()
    return out


def _truncate_value(value: Any, limit: int = FIELD_VALUE_MAX) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    if isinstance(value, list):
        return [_truncate_value(v, limit) for v in value[:50]]
    if isinstance(value, dict):
        return {k: _truncate_value(v, limit) for k, v in list(value.items())[:50]}
    return value


def _truncate_sample(record: Any) -> Any:
    text = json.dumps(record, default=str)
    if len(text) <= SAMPLE_TRUNCATE:
        return record
    if isinstance(record, dict):
        trimmed = {}
        for k, v in record.items():
            trimmed[k] = v
            if len(json.dumps(trimmed, default=str)) > SAMPLE_TRUNCATE:
                trimmed[k] = str(v)[:200] + "…"
                break
        return trimmed
    return str(record)[:SAMPLE_TRUNCATE]


def data_to_markdown(data: Dict[str, Any]) -> str:
    lines: List[str] = []

    def render(key: str, value: Any, depth: int = 0) -> None:
        indent = "  " * depth
        if isinstance(value, dict):
            lines.append(f"{indent}- **{key}**:")
            for k, v in value.items():
                render(k, v, depth + 1)
        elif isinstance(value, list):
            lines.append(f"{indent}- **{key}**:")
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(f"{indent}  -")
                    if isinstance(item, dict):
                        for k, v in item.items():
                            render(k, v, depth + 2)
                    else:
                        lines.append(f"{indent}    {json.dumps(item, default=str)}")
                else:
                    lines.append(f"{indent}  - {item}")
        else:
            lines.append(f"{indent}**{key}**: {value}")

    for k, v in data.items():
        render(k, v)
    return "\n".join(lines) if lines else "_Empty record_"


def parse_raw_input(content: bytes | str, filename: str = "") -> List[Any]:
    if isinstance(content, bytes):
        text = content.decode("utf-8", errors="replace")
    else:
        text = content

    text = text.strip()
    if not text:
        raise ValueError("Empty input")

    lower_name = (filename or "").lower()

    # JSON array
    if text.startswith("["):
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("JSON root must be an array")
        return data

    # NDJSON (check before single-object JSON when multiple lines)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) > 1:
        try:
            records = [json.loads(ln) for ln in lines]
            return records
        except json.JSONDecodeError:
            pass

    # Single JSON object
    if text.startswith("{"):
        data = json.loads(text)
        return [data]

    # CSV
    if lower_name.endswith(".csv") or ("," in text and "\n" in text):
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if rows:
            return rows

    # Free text — single record
    return [{"content": text}]


def _select_samples(records: List[Any]) -> List[Any]:
    if len(records) <= SAMPLE_SIZE:
        return records
    first = records[:10]
    rest = records[10:]
    extra = random.sample(rest, min(5, len(rest)))
    return first + extra


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


async def _infer_schema_async(samples: List[Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    llm = create_webui_llm_client(settings)
    truncated = [_truncate_sample(s) for s in samples]
    prompt = (
        "Infer schema and normalize these sample records:\n\n"
        + json.dumps(truncated, default=str, indent=2)
    )

    for attempt, system in enumerate((SCHEMA_SYSTEM, SCHEMA_RETRY_SYSTEM)):
        try:
            raw = await llm.invoke_text(prompt, system=system)
            parsed = _extract_json(raw)
            fields = parsed.get("fields") or []
            sample_records = parsed.get("sample_records") or parsed.get("records") or []
            if not fields:
                raise ValueError("LLM returned no fields")
            schema = {"fields": fields}
            return schema, [_truncate_value(r) for r in sample_records if isinstance(r, dict)]
        except Exception as e:
            logger.warning("Schema inference attempt %s failed: %s", attempt + 1, e)
            if attempt == 1:
                raise

    raise ValueError("Schema inference failed")


def infer_schema(samples: List[Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    return asyncio.run(_infer_schema_async(samples))


def _normalize_record(raw: Any, schema: Dict[str, Any], llm_normalized: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if llm_normalized and isinstance(llm_normalized, dict):
        return _truncate_value(llm_normalized)

    field_names = [f["name"] for f in schema.get("fields", []) if isinstance(f, dict) and f.get("name")]

    if isinstance(raw, dict):
        if field_names:
            out: Dict[str, Any] = {}
            for name in field_names:
                if name in raw:
                    out[name] = raw[name]
                else:
                    # fuzzy: snake_case match
                    for k, v in raw.items():
                        if k.lower().replace(" ", "_") == name:
                            out[name] = v
                            break
            if out:
                return _truncate_value(out)
        return _truncate_value(raw)

    return _truncate_value({"value": raw})


def list_datasets() -> List[Dict[str, Any]]:
    db = _get_db()
    col = db.get_collection(DATASETS_COL)
    docs = list(col.find().sort("created_at", -1))
    return [_serialize_doc(d) for d in docs]


def get_dataset(dataset_id: str) -> Optional[Dict[str, Any]]:
    db = _get_db()
    col = db.get_collection(DATASETS_COL)
    doc = col.find_one({"_id": _oid(dataset_id)})
    return _serialize_doc(doc) if doc else None


def get_records(
    dataset_id: str,
    page: int = 1,
    limit: int = 10,
) -> Dict[str, Any]:
    db = _get_db()
    col = db.get_collection(RECORDS_COL)
    ds = get_dataset(dataset_id)
    if not ds:
        raise ValueError("Dataset not found")

    page = max(1, page)
    limit = max(1, min(limit, 100))
    total = ds.get("record_count") or col.count_documents({"dataset_id": _oid(dataset_id)})
    skip = (page - 1) * limit

    cursor = (
        col.find({"dataset_id": _oid(dataset_id)})
        .sort("row_index", 1)
        .skip(skip)
        .limit(limit)
    )

    records = []
    for doc in cursor:
        ser = _serialize_doc(doc)
        data = ser.get("data") or {}
        ser["markdown"] = ser.get("display_markdown") or data_to_markdown(data)
        records.append(ser)

    total_pages = max(1, (total + limit - 1) // limit)
    return {
        "dataset": ds,
        "records": records,
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
    }


def patch_record_markdown(
    dataset_id: str,
    record_id: str,
    username: str,
    display_markdown: str,
) -> Dict[str, Any]:
    ds = get_dataset(dataset_id)
    if not ds:
        raise ValueError("Dataset not found")
    if ds.get("owner") != username:
        raise PermissionError("Only the dataset owner can edit records")

    db = _get_db()
    col = db.get_collection(RECORDS_COL)
    result = col.update_one(
        {"_id": _oid(record_id), "dataset_id": _oid(dataset_id)},
        {"$set": {"display_markdown": display_markdown}},
    )
    if result.matched_count == 0:
        raise ValueError("Record not found")

    doc = col.find_one({"_id": _oid(record_id)})
    ser = _serialize_doc(doc)
    ser["markdown"] = ser.get("display_markdown") or data_to_markdown(ser.get("data") or {})
    return ser


def ingest_dataset(
    *,
    name: str,
    description: str,
    category: str,
    owner: str,
    raw_content: bytes | str,
    filename: str = "",
    emit: Optional[Callable[[str, str, Optional[Dict[str, Any]]], None]] = None,
) -> Dict[str, Any]:
    """Parse, infer schema, and insert dataset + records. Optional emit(stage, message, extra)."""

    def _emit(stage: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        if emit:
            emit(stage, message, extra)

    if category not in CATEGORIES:
        raise ValueError(f"Invalid category. Must be one of: {', '.join(sorted(CATEGORIES))}")
    if not name.strip():
        raise ValueError("Dataset name is required")
    if not owner.strip():
        raise ValueError("Username is required")

    _emit("parsing", "Parsing input…")
    records = parse_raw_input(raw_content, filename)
    if len(records) > MAX_RECORDS:
        raise ValueError(f"Too many records ({len(records)}). Maximum is {MAX_RECORDS}.")

    samples = _select_samples(records)
    _emit("inferring_schema", "LLM evaluating schema…")
    schema, llm_normalized_samples = infer_schema(samples)

    db = _get_db()
    datasets_col = db.get_collection(DATASETS_COL)
    records_col = db.get_collection(RECORDS_COL)

    now = _utcnow()
    ds_doc = {
        "name": name.strip(),
        "description": (description or "").strip(),
        "category": category,
        "owner": owner.strip(),
        "schema": schema,
        "record_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    insert_result = datasets_col.insert_one(ds_doc)
    dataset_id = insert_result.inserted_id

    # Map sample indices to LLM-normalized records
    sample_indices = set()
    if len(records) <= SAMPLE_SIZE:
        sample_indices = set(range(len(records)))
    else:
        sample_indices = set(range(10))
        rest_indices = list(range(10, len(records)))
        sample_indices.update(random.sample(rest_indices, min(5, len(rest_indices))))

    llm_by_index: Dict[int, Dict[str, Any]] = {}
    for i, idx in enumerate(sorted(sample_indices)):
        if i < len(llm_normalized_samples):
            llm_by_index[idx] = llm_normalized_samples[i]

    total_batches = max(1, (len(records) + BATCH_SIZE - 1) // BATCH_SIZE)
    inserted = 0

    for batch_num, start in enumerate(range(0, len(records), BATCH_SIZE), start=1):
        batch = records[start : start + BATCH_SIZE]
        _emit(
            "normalizing",
            f"Normalizing records (batch {batch_num}/{total_batches})…",
            {"batch": batch_num, "total_batches": total_batches},
        )

        docs = []
        for offset, raw in enumerate(batch):
            idx = start + offset
            normalized = _normalize_record(
                raw,
                schema,
                llm_by_index.get(idx),
            )
            docs.append(
                {
                    "dataset_id": dataset_id,
                    "data": normalized,
                    "display_markdown": None,
                    "row_index": idx,
                    "created_at": now,
                }
            )

        _emit("inserting", f"Writing to MongoDB (batch {batch_num}/{total_batches})…")
        if docs:
            records_col.insert_many(docs)
            inserted += len(docs)

    datasets_col.update_one(
        {"_id": dataset_id},
        {"$set": {"record_count": inserted, "updated_at": _utcnow()}},
    )

    result = get_records(str(dataset_id), page=1, limit=10)
    _emit("complete", "Upload complete", {"dataset_id": str(dataset_id)})
    return {
        "dataset_id": str(dataset_id),
        "dataset": result["dataset"],
        "records": result["records"],
        "page": result["page"],
        "total": result["total"],
        "total_pages": result["total_pages"],
    }


def ensure_indexes() -> None:
    db = _get_db()
    datasets_col = db.get_collection(DATASETS_COL)
    records_col = db.get_collection(RECORDS_COL)
    datasets_col.create_index([("category", 1)])
    datasets_col.create_index([("owner", 1)])
    records_col.create_index([("dataset_id", 1), ("row_index", 1)])
