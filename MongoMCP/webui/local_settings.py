import os
from typing import Dict

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

# local_settings.py — drop-in replacement for aws_settings.py for local development.
# Copy this to local_settings.py and fill in your values.
# The MCP server (mongo_mcp.py) imports whichever settings module is named in the import.

class LocalSettings:
    def __init__(self):
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')

        # MongoDB config collection location (stores MCP tool definitions)
        self.mcp_config_db = "mcp_config"
        self.mcp_config_col = "mcp_tools"

        # LLM — Grove (Anthropic via MongoDB gateway)
        self.LLM_PROVIDER = "grove"
        self.GROVE_API_KEY = os.getenv("GROVE_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
        self.ANTHROPIC_BASE_URL = os.getenv(
            "ANTHROPIC_BASE_URL",
            "https://grove-gateway-prod.azure-api.net/grove-foundry-prod/anthropic",
        ).rstrip("/")
        self.ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01")
        self.LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "claude-sonnet-4-6")
        self.LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))

        # Embedding model
        self.EMBEDDING_MODEL_ID = "voyage-4"
        self.QUERY_EMBEDDING_MODEL_ID = os.getenv(
            'QUERY_EMBEDDING_MODEL_ID',
            'voyage-4-lite' if self.EMBEDDING_MODEL_ID.startswith('voyage-') else self.EMBEDDING_MODEL_ID
        )

        # Agent loop limits
        self.LLM_MAX_ITERATIONS = int(os.getenv('LLM_MAX_ITERATIONS', '15'))
        self.LLM_MAX_HISTORY = int(os.getenv('LLM_MAX_HISTORY', '20'))

        self.ENABLE_CACHE_POINTS = os.getenv('ENABLE_CACHE_POINTS', 'true').lower() in ['1', 'true', 'yes', 'on']
        self.ENABLE_MCP_TOOL_CACHING = False
        self.ENABLE_RESPONSE_CACHING = False
        self.CACHE_TTL = 300
        self.CACHE_NAMESPACE = os.getenv('CACHE_NAMESPACE', 'local')  # Isolates cache from AWS builds
        self.AI_TOOL_ROUTING = False
        self.TOOL_ROUTING = False

        self.mongo_mcp_root = os.getenv('MONGO_MCP_ROOT', 'http://localhost:8000')

        self.BEDROCK_SYSTEM_PROMPT_TEXTS = [
            "***IMPORTANT: DO NOT recall sessions by username until you have confirmed the username with the user. DO NOT ASSUME you know the Username. Default username is demo-user",
            "***IMPORTANT: STRATEGY FIRST: Before any tool call execute memory_strategy_recall to find applicable patterns THEN EXECUTE the found pattern. Validated and high scoring patterns CANNOT be ignored.***",
            "***IMPORTANT: All output should be Markdown formatted for display within a div in an existing webpage. Do not include html, head, or body tags. Only include the inner content. Always use Markdown formatting.",
        ]

        # Static auth token for the MCP server
        self.AUTH_TOKEN = os.getenv('MCP_AUTH_TOKEN', 'your-static-jwt-token-here')

        # OIDC (Workforce / Okta) — Web UI user login via Flask REST /auth/*
        self.OIDC_ISSUER = os.getenv('OIDC_ISSUER', '')
        self.OIDC_CLIENT_ID = os.getenv('OIDC_CLIENT_ID', '')
        self.OIDC_CLIENT_SECRET = os.getenv('OIDC_CLIENT_SECRET', '')
        self.OIDC_REDIRECT_URI = os.getenv(
            'OIDC_REDIRECT_URI', 'http://localhost:8001/auth/callback'
        )
        self.OIDC_SCOPES = os.getenv('OIDC_SCOPES', 'openid profile email')
        self.SESSION_SECRET = os.getenv(
            'SESSION_SECRET', 'dev-change-me-in-production'
        )
        self.AUTH_REQUIRED = os.getenv('AUTH_REQUIRED', 'false').lower() in (
            '1', 'true', 'yes', 'on'
        )

        # Voyage AI API key (only needed if EMBEDDING_MODEL_ID starts with "voyage-" and you run locally
        # without Atlas Data API embedding; typically stored in your MongoDB secret in production)
        self.VOYAGE_AI_KEY = os.getenv('VOYAGE_AI_KEY', 'your-voyage-api-key-here')

        # MongoDB credentials for local development (set via .env or environment)
        self._credentials: Dict[str, str] = {
            "username": os.getenv("MONGO_USERNAME", "your-mongo-username"),
            "password": os.getenv("MONGO_PASSWORD", "your-mongo-password"),
            "mongoUrl": os.getenv("MONGO_URL", "your-cluster.mongodb.net"),
        }

    def get_mongo_credentials(self) -> Dict[str, str]:
        return self._credentials

    def get_auth_token(self) -> str:
        return self.AUTH_TOKEN

    def mongo_url(self) -> str:
        return self._credentials['mongoUrl']

    def mongo_timeout(self) -> int:
        return 5000

    def mongo_voyage_apikey(self) -> str:
        return self.VOYAGE_AI_KEY


# Create a singleton instance
settings = LocalSettings()


def __getattr__(name: str):
    """Backward-compatible module attribute access via singleton settings."""
    if hasattr(settings, name):
        return getattr(settings, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
