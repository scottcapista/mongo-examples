"""
Anthropic Messages API client for MongoDB Grove gateway.

Grove uses the Anthropic API shape with an ``api-key`` header instead of
``x-api-key``.  Tool-call history is kept in Bedrock Converse shape internally
so existing MCP / Web UI code paths stay unchanged.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from .bedrock_client import BedrockClient

logger = logging.getLogger(__name__)

DEFAULT_GROVE_BASE_URL = (
    "https://grove-gateway-prod.azure-api.net/grove-foundry-prod/anthropic"
)


def normalize_grove_model_id(model_id: str) -> str:
    """Map Bedrock inference profile IDs to Grove Anthropic model names."""
    if model_id.startswith("global.anthropic."):
        return model_id[len("global.anthropic.") :]
    if model_id.startswith("us.anthropic."):
        # e.g. us.anthropic.claude-sonnet-4-20250514-v1:0 — keep as-is unless Grove rejects
        return model_id
    return model_id


def resolve_llm_provider(settings) -> str:
    explicit = getattr(settings, "LLM_PROVIDER", None) or ""
    if explicit:
        return explicit.lower()
    key = getattr(settings, "GROVE_API_KEY", "") or getattr(settings, "ANTHROPIC_API_KEY", "")
    if key and key not in ("", "your-grove-api-key-here", "your-anthropic-api-key-here"):
        return "grove"
    return "bedrock"


class GroveAnthropicClient(BedrockClient):
    """BedrockClient-compatible LLM client that calls Grove / Anthropic Messages API."""

    def __init__(self, settings):
        super().__init__(settings)
        self.grove_api_key = (
            getattr(settings, "GROVE_API_KEY", None)
            or getattr(settings, "ANTHROPIC_API_KEY", None)
            or ""
        )
        base = (
            getattr(settings, "ANTHROPIC_BASE_URL", None)
            or DEFAULT_GROVE_BASE_URL
        ).rstrip("/")
        self.grove_messages_url = f"{base}/v1/messages"
        self.anthropic_version = getattr(settings, "ANTHROPIC_VERSION", "2023-06-01")
        self.grove_model_id = normalize_grove_model_id(settings.LLM_MODEL_ID)
        self.grove_max_tokens = int(getattr(settings, "LLM_MAX_TOKENS", 4096))
        # Grove does not use Bedrock cache points.
        self.enable_cache_points = False

    def _grove_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "anthropic-version": self.anthropic_version,
            "api-key": self.grove_api_key,
        }

    def _system_text(self) -> Optional[str]:
        if not self.system:
            return None
        parts: List[str] = []
        for block in self.system:
            if isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        text = "\n\n".join(p for p in parts if p.strip())
        return text or None

    def _convert_mcp_tools_to_anthropic(self) -> List[Dict[str, Any]]:
        if not self.mcp_tools:
            return []
        tools: List[Dict[str, Any]] = []
        for tool in self.mcp_tools:
            spec = tool.get("toolSpec") if isinstance(tool, dict) else None
            if not spec:
                continue
            schema = spec.get("inputSchema") or {}
            if isinstance(schema, dict) and "json" in schema:
                schema = schema["json"]
            tools.append(
                {
                    "name": spec.get("name", ""),
                    "description": spec.get("description", ""),
                    "input_schema": schema or {"type": "object", "properties": {}},
                }
            )
        return tools

    def _convert_bedrock_messages_to_anthropic(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        anthropic_messages: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", [])

            if role == "user":
                if content and isinstance(content, list) and any(
                    isinstance(c, dict) and "toolResult" in c for c in content
                ):
                    blocks = []
                    for item in content:
                        if not isinstance(item, dict) or "toolResult" not in item:
                            continue
                        tr = item["toolResult"]
                        result_text = ""
                        for part in tr.get("content", []):
                            if isinstance(part, dict) and "text" in part:
                                result_text += part["text"]
                        blocks.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tr.get("toolUseId", ""),
                                "content": result_text,
                            }
                        )
                    if blocks:
                        anthropic_messages.append({"role": "user", "content": blocks})
                else:
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            text_parts.append(item["text"])
                    if text_parts:
                        anthropic_messages.append(
                            {"role": "user", "content": "\n".join(text_parts)}
                        )

            elif role == "assistant":
                blocks = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if "text" in item:
                        blocks.append({"type": "text", "text": item["text"]})
                    elif "toolUse" in item:
                        tu = item["toolUse"]
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": tu.get("toolUseId", ""),
                                "name": tu.get("name", ""),
                                "input": tu.get("input") or {},
                            }
                        )
                if blocks:
                    anthropic_messages.append({"role": "assistant", "content": blocks})

        return anthropic_messages

    def _anthropic_assistant_to_bedrock(self, content: List[Dict[str, Any]]) -> Dict[str, Any]:
        bedrock_content: List[Dict[str, Any]] = []
        for block in content:
            btype = block.get("type")
            if btype == "text":
                bedrock_content.append({"text": block.get("text", "")})
            elif btype == "tool_use":
                bedrock_content.append(
                    {
                        "toolUse": {
                            "toolUseId": block.get("id", ""),
                            "name": block.get("name", ""),
                            "input": block.get("input") or {},
                        }
                    }
                )
        return {"role": "assistant", "content": bedrock_content}

    async def _post_messages(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.grove_messages_url,
                headers=self._grove_headers(),
                json=payload,
            )
            if response.status_code >= 400:
                detail = response.text[:500]
                raise httpx.HTTPStatusError(
                    f"Grove API {response.status_code}: {detail}",
                    request=response.request,
                    response=response,
                )
            return response.json()

    async def invoke_bedrock_text(self, prompt: str, system: Optional[str] = None) -> str:
        payload: Dict[str, Any] = {
            "model": self.grove_model_id,
            "max_tokens": min(self.grove_max_tokens, 1024),
            "messages": [{"role": "user", "content": prompt}],
        }
        sys_text = system or self._system_text()
        if sys_text:
            payload["system"] = sys_text
        try:
            data = await self._post_messages(payload)
            parts = []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "".join(parts)
        except Exception as e:
            logger.warning("invoke_bedrock_text (Grove) failed: %s", e)
            return ""

    async def invoke_bedrock_with_tools(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(request, dict):
            return {"history": [], "usage": None, "error": "Invalid request: must be a dict"}

        messages = request.get("messages")
        if not isinstance(messages, list) or not messages:
            return {
                "history": messages if isinstance(messages, list) else [],
                "usage": None,
                "error": "Invalid request: at least one message is required",
            }

        anthropic_messages = self._convert_bedrock_messages_to_anthropic(messages)
        anthropic_tools = self._convert_mcp_tools_to_anthropic()
        usage = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
        return_obj: Dict[str, Any] = {"history": messages, "usage": usage}

        if not anthropic_tools:
            return_obj["error"] = "No MCP tools configured. Tool discovery may have failed."
            return return_obj

        for iteration in range(self.max_iterations):
            try:
                self._emit_progress(
                    self.message_handler,
                    f"Invoking Grove Claude (iteration {iteration + 1})",
                    status="LLM Thinking...",
                )
                payload: Dict[str, Any] = {
                    "model": self.grove_model_id,
                    "max_tokens": self.grove_max_tokens,
                    "messages": anthropic_messages,
                    "tools": anthropic_tools,
                }
                sys_text = self._system_text()
                if sys_text:
                    payload["system"] = sys_text

                t0 = time.monotonic()
                data = await self._post_messages(payload)
                elapsed_ms = (time.monotonic() - t0) * 1000
                self._emit_progress(
                    self.message_handler,
                    f"Grove completed in {elapsed_ms / 1000:.3f}s",
                    status="LLM Response Received",
                )

                in_tok = int(data.get("usage", {}).get("input_tokens", 0))
                out_tok = int(data.get("usage", {}).get("output_tokens", 0))
                usage["inputTokens"] += in_tok
                usage["outputTokens"] += out_tok
                usage["totalTokens"] += in_tok + out_tok
                return_obj["usage"] = usage

                assistant_blocks = data.get("content", [])
                bedrock_assistant = self._anthropic_assistant_to_bedrock(assistant_blocks)
                messages.append(bedrock_assistant)
                anthropic_messages.append(
                    {"role": "assistant", "content": assistant_blocks}
                )
                return_obj["history"] = messages

                for block in assistant_blocks:
                    if block.get("type") == "text" and self.show_response_progress:
                        self._emit_progress(
                            self.message_handler,
                            block.get("text", ""),
                            status="LLM Reasoning",
                        )
                        break

                if iteration + 1 >= self.max_iterations:
                    break

                tool_uses = [b for b in assistant_blocks if b.get("type") == "tool_use"]
                if not tool_uses:
                    return_obj["stats"] = {
                        "total_itterations": iteration + 1,
                        "max_itterations": self.max_iterations,
                    }
                    text_parts = [
                        b.get("text", "")
                        for b in assistant_blocks
                        if b.get("type") == "text"
                    ]
                    if text_parts:
                        return_obj["response"] = "\n".join(text_parts)
                    return return_obj

                tool_result_blocks = []
                bedrock_tool_results = []

                for tu in tool_uses:
                    tool_name = tu.get("name", "")
                    tool_use_id = tu.get("id", "")
                    self._emit_progress(
                        self.message_handler,
                        f"Calling tool: {tool_name}",
                        status="Tool Execution",
                    )
                    try:
                        tool_input = self._deserialize_stringified_arrays(tu.get("input") or {})
                        result = await self._call_mcp_tool(tool_name, tool_input)
                        result_text = str(result)
                        self._emit_progress(
                            self.message_handler,
                            f"Tool {tool_name} returned {len(result_text)} chars",
                            status="Tool Complete",
                        )
                    except Exception as e:
                        logger.error("Error executing MCP tool %s: %s", tool_name, e)
                        result_text = f"Error: {e}"

                    tool_result_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": result_text,
                        }
                    )
                    bedrock_tool_results.append(
                        {
                            "toolResult": {
                                "toolUseId": tool_use_id,
                                "content": [{"text": result_text}],
                            }
                        }
                    )

                if tool_result_blocks:
                    anthropic_messages.append(
                        {"role": "user", "content": tool_result_blocks}
                    )
                    messages.append({"role": "user", "content": bedrock_tool_results})
                    return_obj["history"] = messages
                    self._emit_progress(
                        self.message_handler,
                        f"Sending {len(tool_result_blocks)} tool result(s) back to Grove...",
                        status="Tool Results",
                    )
                    continue

            except Exception as e:
                logger.error("Unexpected error in invoke_bedrock_with_tools (Grove): %s", e)
                return_obj["error"] = str(e)
                return return_obj

        return_obj["error"] = "No response generated"
        return return_obj


class ServerGroveClient(GroveAnthropicClient):
    """Server-side Grove client with prompt/context formatting."""

    def __init__(self, settings):
        super().__init__(settings)
        instructions = getattr(settings, "agent_instructions", "")
        if instructions:
            self.system = [{"text": instructions}]
        else:
            logger.warning("ServerGroveClient: agent_instructions EMPTY — system prompt NOT set")

    def _format_invoke_request(
        self,
        prompt: Optional[str] = None,
        context: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        request_messages = messages
        if request_messages is None:
            final_prompt = prompt or ""
            if context:
                final_prompt = final_prompt + f"\nUse the following data for Context: {context}"
            request_messages = [{"role": "user", "content": [{"text": final_prompt}]}]
        elif prompt or context:
            appended_prompt = prompt or ""
            if context:
                appended_prompt = appended_prompt + f"\nUse the following data for Context: {context}"
            request_messages.append(
                {"role": "user", "content": [{"text": appended_prompt}]}
            )
        return {"messages": request_messages}

    async def invoke_bedrock_with_tools(
        self,
        prompt: Optional[str] = None,
        context: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        request = self._format_invoke_request(
            prompt=prompt,
            context=context,
            messages=messages,
        )
        return await super().invoke_bedrock_with_tools(request=request)
