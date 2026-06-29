"""Web UI Grove client with text-oriented response normalization."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..grove_anthropic_client import GroveAnthropicClient

JSON_DATA_START = "[JSON_DATA_START]"
JSON_DATA_END = "[JSON_DATA_END]"


def _extract_json_block(text: str):
    """Extract JSON from [JSON_DATA_START]...[JSON_DATA_END] tags."""
    start_idx = text.find(JSON_DATA_START)
    end_idx = text.find(JSON_DATA_END)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return None, text.strip()
    json_str = text[start_idx + len(JSON_DATA_START) : end_idx].strip()
    clean = (text[:start_idx] + text[end_idx + len(JSON_DATA_END) :]).strip()
    try:
        parsed = json.loads(json_str)
        return parsed, clean
    except (json.JSONDecodeError, TypeError):
        return None, text.strip()


class WebUiGroveClient(GroveAnthropicClient):
    def _format_invoke_request(
        self,
        prompt: Optional[str] = None,
        context: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        request_messages = messages if messages is not None else []
        if prompt or context:
            appended_prompt = prompt or ""
            if context:
                appended_prompt = appended_prompt + f"\nUse the following data for Context: {context}"
            request_messages.append(
                {"role": "user", "content": [{"text": appended_prompt}]}
            )
        return {"messages": request_messages}

    async def invoke_with_tools(
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
        return await super().invoke_with_tools(request=request)

    async def invoke_with_tools_text(
        self,
        prompt: Optional[str] = None,
        context: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        raw = await self.invoke_with_tools(
            prompt=prompt,
            context=context,
            messages=messages,
        )
        return self.normalize_llm_response(raw, fallback_history=messages or [])

    def normalize_llm_response(
        self,
        response_obj: Dict[str, Any],
        fallback_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        history = response_obj.get("history", fallback_history or [])
        usage = response_obj.get("usage")
        usage_calls = response_obj.get("usage_calls")
        stats = response_obj.get("stats")

        if response_obj.get("error"):
            return {
                "response_text": f"Error: {response_obj['error']}",
                "jsondata": None,
                "history": history,
                "usage": usage,
                "usage_calls": usage_calls,
                "stats": stats,
            }

        raw_text = None
        if history and history[-1].get("role") == "assistant":
            text_parts = [
                c["text"]
                for c in history[-1].get("content", [])
                if isinstance(c, dict) and "text" in c
            ]
            if text_parts:
                raw_text = " ".join(text_parts)

        if not raw_text and "response" in response_obj:
            raw_text = str(response_obj["response"])

        if not raw_text:
            return {
                "response_text": "No response generated",
                "jsondata": None,
                "history": history,
                "usage": usage,
                "usage_calls": usage_calls,
                "stats": stats,
            }

        tag_json, clean_text = _extract_json_block(raw_text)
        return {
            "response_text": clean_text,
            "jsondata": tag_json,
            "history": history,
            "usage": usage,
            "usage_calls": usage_calls,
            "stats": stats,
        }
