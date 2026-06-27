"""
mongomcp.agent — Web UI agent subpackage.

Contains the query processor, tool router, and WebUI Grove client.
These classes depend on additional packages (flask, pydantic, etc.)
that the MCP server does not need. Install with:

    pip install mongomcp[agent]
"""

from .cached_query_processor import CachedQueryProcessor
from .tool_router import ToolRouter
from .webui_grove_client import WebUiGroveClient
from .prompt_agent import PromptAgent
from .mcp_tools import register_agent_tools, get_agent_toolspecs

__all__ = [
    "CachedQueryProcessor",
    "ToolRouter",
    "WebUiGroveClient",
    "PromptAgent",
    "register_agent_tools",
    "get_agent_toolspecs",
]
