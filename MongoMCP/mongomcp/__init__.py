"""
MongoMCP Package

MongoDB MCP (Model Context Protocol) server package providing:
- MongoDB search capabilities
- Authentication and middleware
- Grove LLM integration
- Configuration management

Main Classes:
- MongoDBQueryServer: Core Mongo Query functionality
- MongoMCPMiddleware: Request middleware, config interactions to/from MongoDB, MCP tool management
- LlmClientBase: Shared LLM client utilities (embeddings, MCP tool dispatch)
- ServerGroveClient: Server-side Grove implementation
- MongoTokenVerifier: JWT token authentication
- MongoDBClient: MongoDB connection management

The ``mongomcp.agent`` subpackage contains the Web UI agent classes
(CachedQueryProcessor, ToolRouter, WebUiGroveClient).  Install with
``pip install mongomcp[agent]`` to pull in agent-only dependencies.
"""

from .mongodb_query_provider import MongoDBQueryServer
from .mongo_mcp_middleware import MongoMCPMiddleware
from .llm_client_base import LlmClientBase
from .grove_anthropic_client import ServerGroveClient
from .mongo_token_verifier import MongoTokenVerifier
from .mongodb_client import MongoDBClient
from .memory import register_memory_tools, get_memory_toolspecs
from .tools import register_query_tools
from .agent import register_agent_tools, get_agent_toolspecs
from .datasets import register_dataset_tools, get_dataset_toolspecs

__version__ = "3.2.0"

__all__ = [
   "MongoDBQueryServer",
   "MongoMCPMiddleware",
   "LlmClientBase",
   "ServerGroveClient",
   "MongoTokenVerifier",
   "MongoDBClient",
   "register_memory_tools",
   "get_memory_toolspecs",
   "register_query_tools",
   "register_agent_tools",
   "get_agent_toolspecs",
   "register_dataset_tools",
   "get_dataset_toolspecs",
]
