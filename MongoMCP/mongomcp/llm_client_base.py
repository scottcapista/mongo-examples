"""Shared LLM client utilities: MCP tool dispatch, embeddings, and message helpers."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re
import traceback
from typing import Any, Callable, Dict, List, Optional

import httpx

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


class LlmClientBase:
    """Base class for Grove LLM clients: tool wiring, embeddings, and shared helpers."""

    def __init__(self, settings):
        self.settings = settings
        self.mcp_tools = None
        self.mcp_call = None
        self.llm_setup = False
        self.max_iterations = self.settings.LLM_MAX_ITERATIONS
        self.enable_cache_points = False
        self.system = None
        self.message_handler = None
        self.show_response_progress = True

    def configure_tools(self, tools_config, tool_handler: Optional[Callable] = None):
        self.mcp_tools = tools_config
        self.mcp_call = tool_handler
        self.llm_setup = True

    def _emit_progress(self, message_handler: Optional[Callable], message: str, status: str = "Processing") -> None:
        if not message_handler:
            return
        try:
            message_handler(message, status=status)
        except Exception:
            return

    @staticmethod
    def _estimate_text_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)

    def _estimate_content_tokens(self, content: Any) -> int:
        if isinstance(content, str):
            return self._estimate_text_tokens(content)
        if isinstance(content, list):
            return sum(self._estimate_content_tokens(item) for item in content)
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                return self._estimate_text_tokens(text)
            return self._estimate_text_tokens(json.dumps(content, ensure_ascii=False, default=str))
        return self._estimate_text_tokens(str(content))

    def _estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        total = 0
        for msg in messages or []:
            total += 6
            total += self._estimate_content_tokens(msg.get("content", []))
        return total

    def _estimate_system_tokens(self) -> int:
        return self._estimate_content_tokens(self.system or [])

    def _estimate_total_context_tokens(self, messages: List[Dict[str, Any]]) -> int:
        return self._estimate_system_tokens() + self._estimate_messages_tokens(messages)

    @staticmethod
    def _tool_overflow_notice(tool_name: str, estimated_added_tokens: int, current_tokens: int, max_tokens: int) -> str:
        return (
            f"Tool '{tool_name}' executed successfully, but the full result was omitted because it would overflow "
            f"the model context (current~{current_tokens}, add~{estimated_added_tokens}, max={max_tokens}). "
            "Please rework the request to page results into smaller chunks and use the memory layer to store and "
            "retrieve those chunks across turns."
        )

    @staticmethod
    def _deserialize_stringified_arrays(tool_input: dict) -> dict:
        if not isinstance(tool_input, dict):
            return tool_input
        result = {}
        for k, v in tool_input.items():
            if isinstance(v, str) and len(v) >= 2 and v[0] in ("[", "{"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, (list, dict)):
                        result[k] = parsed
                        continue
                except (json.JSONDecodeError, ValueError):
                    pass
            result[k] = v
        return result

    async def _call_mcp_tool(self, toolname: str, tool_input: dict) -> str:
        try:
            call_fn = self.mcp_call
            if call_fn is None:
                raise NotImplementedError(
                    "No MCP tool callback configured. Provide configure_tools(..., tool_handler) "
                    "or override _call_mcp_tool in a subclass."
                )
            result = await call_fn(toolname, tool_input)
            if isinstance(result, dict):
                return json.dumps(result, cls=DateTimeEncoder, indent=2)
            return str(result)
        except Exception as e:
            logger.error("MCP tool %s failed: %s", toolname, e)
            traceback.print_exc()
            raise

    async def generate_embedding(self, text: str, model_id: Optional[str] = None) -> dict:
        if model_id is None:
            model_id = self.settings.EMBEDDING_MODEL_ID
        if model_id.startswith("voyage-"):
            return await self.generate_voyage_embeddings(text, model_id=model_id)
        raise ValueError(f"Unsupported embedding model {model_id!r}; use a voyage-* model.")

    async def generate_voyage_embeddings(
        self, text: str, model_id: Optional[str] = None, is_query: bool = True
    ) -> dict:
        api_key = self.settings.mongo_voyage_apikey()
        if is_query:
            model_id = self.settings.QUERY_EMBEDDING_MODEL_ID
        if model_id is None:
            model_id = self.settings.EMBEDDING_MODEL_ID
        if not model_id.startswith("voyage-"):
            model_id = "voyage-4"

        input_type = "query" if is_query else "document"
        max_retries = 6
        base_delay = 2.0
        for attempt in range(max_retries):
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://ai.mongodb.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"input": text, "model": model_id, "input_type": input_type},
                )
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", base_delay * (2 ** attempt)))
                    logger.warning(
                        "Voyage rate limit — waiting %.1fs (attempt %s/%s)",
                        retry_after,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                data = response.json()
                return {"embedding_model": model_id, "vector": data["data"][0]["embedding"]}
        raise RuntimeError(f"generate_voyage_embeddings: exceeded {max_retries} retries due to rate limiting")

    async def generate_voyage_embeddings_batch(
        self,
        texts: List[str],
        model_id: Optional[str] = None,
        is_query: bool = False,
        batch_size: int = 1000,
    ) -> List[dict]:
        api_key = self.settings.mongo_voyage_apikey()
        if is_query:
            model_id = model_id or self.settings.QUERY_EMBEDDING_MODEL_ID
        if model_id is None:
            model_id = self.settings.EMBEDDING_MODEL_ID
        if not model_id.startswith("voyage-"):
            model_id = "voyage-4"

        input_type = "query" if is_query else "document"
        batch_size = min(batch_size, 1000)
        results: List[dict] = [None] * len(texts)
        max_retries = 6
        base_delay = 2.0

        for batch_start in range(0, len(texts), batch_size):
            batch = texts[batch_start : batch_start + batch_size]
            for attempt in range(max_retries):
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://ai.mongodb.com/v1/embeddings",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={"input": batch, "model": model_id, "input_type": input_type},
                    )
                    if response.status_code == 429:
                        retry_after = float(
                            response.headers.get("Retry-After", base_delay * (2 ** attempt))
                        )
                        logger.warning(
                            "Voyage batch rate limit — waiting %.1fs (batch %s, attempt %s/%s)",
                            retry_after,
                            batch_start,
                            attempt + 1,
                            max_retries,
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    for item in data["data"]:
                        global_idx = batch_start + item["index"]
                        results[global_idx] = {
                            "embedding_model": model_id,
                            "vector": item["embedding"],
                        }
                    break
            else:
                raise RuntimeError(
                    f"generate_voyage_embeddings_batch: exceeded {max_retries} retries "
                    f"on batch starting at index {batch_start}"
                )

        return results

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = 10,
        truncation: bool = True,
    ) -> List[dict]:
        model = "rerank-2.5"
        api_key = self.settings.mongo_voyage_apikey()
        payload: Dict[str, Any] = {
            "query": query,
            "documents": documents,
            "model": model,
            "truncation": truncation,
            "top_k": top_k,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://ai.mongodb.com/v1/rerank",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return data.get("data", [])
