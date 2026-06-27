"""Web UI Grove client — same response normalization as WebUiBedrockClient."""

from typing import Any, Dict, List, Optional

from ..grove_anthropic_client import GroveAnthropicClient
from .webui_bedrock_client import _extract_json_block


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

    async def invoke_bedrock_with_tools_text(
        self,
        prompt: Optional[str] = None,
        context: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        raw = await self.invoke_bedrock_with_tools(
            prompt=prompt,
            context=context,
            messages=messages,
        )
        return self.normalize_bedrock_response(raw, fallback_history=messages or [])

    def normalize_bedrock_response(
        self,
        response_obj: Dict[str, Any],
        fallback_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        history = response_obj.get("history", fallback_history or [])
        usage = response_obj.get("usage")
        stats = response_obj.get("stats")

        if response_obj.get("error"):
            return {
                "response_text": f"Error: {response_obj['error']}",
                "jsondata": None,
                "history": history,
                "usage": usage,
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
                "stats": stats,
            }

        tag_json, clean_text = _extract_json_block(raw_text)
        return {
            "response_text": clean_text,
            "jsondata": tag_json,
            "history": history,
            "usage": usage,
            "stats": stats,
        }
