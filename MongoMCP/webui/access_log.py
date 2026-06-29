"""Readable HTTP access logging for the Flask Web UI."""

from __future__ import annotations

import logging

from flask import Request, Response

logger = logging.getLogger("webui.access")

# Werkzeug access lines are replaced by webui.access; keep werkzeug errors.
_WERKZEUG_LOG = logging.getLogger("werkzeug")

_STATIC_SUFFIXES = (".js", ".css", ".png", ".ico", ".webp", ".svg", ".woff", ".woff2")
_NO_CACHE_PREFIXES = ("/auth/", "/admin/", "/query", "/health", "/models", "/warmup")


def configure_access_logging() -> None:
    """Use structured access logs instead of raw werkzeug request lines."""
    _WERKZEUG_LOG.setLevel(logging.WARNING)
    logger.info(
        "Access logging enabled. HTTP 304 = browser cache hit (not an error). "
        "Static assets may 304; auth/API responses are marked no-store."
    )


def _category(path: str) -> str:
    if path.startswith("/assets/") or path.endswith(_STATIC_SUFFIXES):
        return "static"
    if path.startswith("/auth/"):
        return "auth"
    if path.startswith("/admin/"):
        return "api"
    if path.startswith("/query") or path in {"/health", "/models", "/warmup"}:
        return "api"
    if path in {"", "/"}:
        return "spa"
    return "other"


def _status_note(status: int, category: str, response: Response) -> str:
    if status == 304:
        if category in {"auth", "api"}:
            return "cache hit — unusual for dynamic route; sent Cache-Control: no-store on future responses"
        return "cache hit (browser reused local copy — normal for static files)"
    if status == 302:
        location = response.headers.get("Location", "")
        if location:
            host = location.split("/")[2] if location.startswith("http") and len(location.split("/")) > 2 else ""
            if host:
                return f"redirect -> {host}…"
            return f"redirect -> {location[:80]}"
        return "redirect"
    if status == 401:
        return "not authenticated"
    if status == 403:
        return "forbidden"
    if status >= 500:
        return "server error"
    if status >= 400:
        return "client error"
    return "ok"


def _log_level(status: int, category: str) -> int:
    if status >= 500:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    if status == 304 and category in {"auth", "api"}:
        return logging.WARNING
    return logging.INFO


def log_request(request: Request, response: Response, elapsed_ms: float) -> None:
    path = request.path
    category = _category(path)
    status = response.status_code
    qs = request.query_string.decode("utf-8", errors="replace")
    query_part = f"?{qs}" if qs else ""
    note = _status_note(status, category, response)
    line = f"[{category}] {request.method} {path}{query_part} -> {status} ({elapsed_ms:.0f}ms) | {note}"
    logger.log(_log_level(status, category), line)


def apply_cache_headers(request: Request, response: Response) -> Response:
    path = request.path
    category = _category(path)

    if any(path.startswith(prefix) for prefix in _NO_CACHE_PREFIXES):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response

    if category == "spa":
        response.headers["Cache-Control"] = "no-cache"
        return response

    return response