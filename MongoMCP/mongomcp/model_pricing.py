"""LLM model pricing registry and cost estimation (compute-at-read)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from mongomcp.grove_anthropic_client import normalize_grove_model_id

logger = logging.getLogger(__name__)

_UNKNOWN_MODEL_LOGGED: set[str] = set()


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_million: float
    output_usd_per_million: float
    cache_read_usd_per_million: float
    cache_write_usd_per_million: float
    display_name: str = ""


MODEL_PRICING: Dict[str, ModelPricing] = {
    "claude-sonnet-4-6": ModelPricing(3.0, 15.0, 0.30, 3.75, "Claude Sonnet 4.6"),
}


def resolve_model_id(model_id: str) -> str:
    return normalize_grove_model_id(model_id or "")


def get_model_pricing(model_id: str) -> Optional[ModelPricing]:
    key = resolve_model_id(model_id)
    return MODEL_PRICING.get(key)


def estimate_cost_usd(
    *,
    model_id: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> Optional[float]:
    pricing = get_model_pricing(model_id)
    if pricing is None:
        key = resolve_model_id(model_id)
        if key and key not in _UNKNOWN_MODEL_LOGGED:
            _UNKNOWN_MODEL_LOGGED.add(key)
            logger.debug("No pricing for model_id=%r", model_id)
        return None
    cost = (
        input_tokens * pricing.input_usd_per_million
        + output_tokens * pricing.output_usd_per_million
        + cache_read_input_tokens * pricing.cache_read_usd_per_million
        + cache_creation_input_tokens * pricing.cache_write_usd_per_million
    ) / 1_000_000
    return cost


def export_model_pricing() -> List[Dict[str, Any]]:
    """Read-only registry export for admin UI."""
    models = []
    for model_id, p in sorted(MODEL_PRICING.items()):
        models.append({
            "id": model_id,
            "display_name": p.display_name or model_id,
            "input_usd_per_million": p.input_usd_per_million,
            "output_usd_per_million": p.output_usd_per_million,
            "cache_read_usd_per_million": p.cache_read_usd_per_million,
            "cache_write_usd_per_million": p.cache_write_usd_per_million,
        })
    return models
