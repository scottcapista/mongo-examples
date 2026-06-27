"""Create Grove LLM clients for server and Web UI."""

from __future__ import annotations

from typing import Any

from .grove_anthropic_client import ServerGroveClient
from .agent.webui_grove_client import WebUiGroveClient


def create_server_llm_client(settings) -> Any:
    return ServerGroveClient(settings)


def create_webui_llm_client(settings) -> Any:
    return WebUiGroveClient(settings)
