"""Select LLM client implementation (Grove Anthropic vs AWS Bedrock)."""

from __future__ import annotations

from typing import Any

from .grove_anthropic_client import resolve_llm_provider, ServerGroveClient
from .bedrock_client import ServerBedrockClient


def create_server_llm_client(settings) -> Any:
    if resolve_llm_provider(settings) == "grove":
        return ServerGroveClient(settings)
    return ServerBedrockClient(settings)


def create_webui_llm_client(settings) -> Any:
    if resolve_llm_provider(settings) == "grove":
        from .agent.webui_grove_client import WebUiGroveClient

        return WebUiGroveClient(settings)
    from .agent.webui_bedrock_client import WebUiBedrockClient

    return WebUiBedrockClient(settings)
