"""MCP tools for cluster dataset discovery and generic dataset queries."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Dict, List, Optional

from pydantic import Field

from .discovery import discover_cluster_datasets
from .service import list_datasets, query_dataset

logger = logging.getLogger(__name__)


def register_dataset_tools(mcp, settings) -> Dict[str, Any]:
    """Register dataset discovery and query tools on a FastMCP instance."""
    dispatch: Dict[str, Any] = {}

    @mcp.tool()
    async def discover_cluster_datasets_tool(
        force_refresh: Annotated[
            bool,
            Field(
                default=False,
                description="When true, refresh index metadata and counts for all discovered collections.",
            ),
        ] = False,
    ) -> Dict[str, Any]:
        """Scan the MongoDB cluster and register datasets for every non-system collection.

        Skips databases: admin, local, config, mcp_config.
        Logs database, Atlas Search, and vector indexes for each collection.
        """
        try:
            return discover_cluster_datasets(settings, force_refresh=force_refresh)
        except Exception as exc:
            logger.error("discover_cluster_datasets failed: %s", exc, exc_info=True)
            return {"error": str(exc)}

    dispatch["discover_cluster_datasets"] = getattr(
        discover_cluster_datasets_tool, "fn", discover_cluster_datasets_tool
    )

    @mcp.tool()
    async def dataset_list(
        source_type: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Filter by source_type: 'cluster' (auto-discovered) or 'upload' (admin uploads).",
            ),
        ] = None,
    ) -> Dict[str, Any]:
        """List registered datasets with index summaries for query planning."""
        try:
            datasets = list_datasets(settings, source_type=source_type)
            return {"count": len(datasets), "datasets": datasets}
        except Exception as exc:
            logger.error("dataset_list failed: %s", exc, exc_info=True)
            return {"error": str(exc)}

    dispatch["dataset_list"] = getattr(dataset_list, "fn", dataset_list)

    @mcp.tool()
    async def dataset_query(
        dataset_name: Annotated[
            Optional[str],
            Field(default=None, description="Dataset name, e.g. sample_airbnb.listingsAndReviews"),
        ] = None,
        dataset_id: Annotated[
            Optional[str],
            Field(default=None, description="Dataset ObjectId hex string."),
        ] = None,
        pipeline: Annotated[
            Optional[List[Dict[str, Any]]],
            Field(
                default=None,
                description="MongoDB aggregation pipeline. For upload datasets, scoped to dataset_id automatically.",
            ),
        ] = None,
        filter: Annotated[
            Optional[Dict[str, Any]],
            Field(
                default=None,
                description="MongoDB find filter when pipeline is omitted.",
            ),
        ] = None,
        limit: Annotated[int, Field(default=20, ge=1, le=1000, description="Max documents to return.")] = 20,
    ) -> Dict[str, Any]:
        """Query a dataset by name or id. Returns results plus index_context for follow-up queries.

        Use dataset_list first to see available datasets and index summaries.
        For cluster collections, queries run directly against the backing collection.
        """
        try:
            if isinstance(pipeline, str):
                pipeline = json.loads(pipeline)
            if isinstance(filter, str):
                filter = json.loads(filter)
            return query_dataset(
                settings,
                dataset_id=dataset_id,
                dataset_name=dataset_name,
                pipeline=pipeline,
                filter=filter,
                limit=limit,
            )
        except Exception as exc:
            logger.error("dataset_query failed: %s", exc, exc_info=True)
            return {"error": str(exc)}

    dispatch["dataset_query"] = getattr(dataset_query, "fn", dataset_query)

    return dispatch


def get_dataset_toolspecs() -> List[Dict[str, Any]]:
    """Grove toolSpec entries for dataset tools (for agent catalog)."""
    def _spec(name: str, description: str, properties: dict, required: list) -> Dict[str, Any]:
        return {
            "toolSpec": {
                "name": name,
                "description": description,
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    }
                },
            }
        }

    return [
        _spec(
            "discover_cluster_datasets",
            "Scan the cluster and register datasets for each non-system collection. Logs db/search/vector indexes.",
            {
                "force_refresh": {
                    "type": "boolean",
                    "description": "Refresh index metadata for existing discovered datasets.",
                    "default": False,
                }
            },
            [],
        ),
        _spec(
            "dataset_list",
            "List registered datasets (cluster-discovered and uploaded) with index summaries.",
            {
                "source_type": {
                    "type": "string",
                    "description": "Optional filter: cluster or upload.",
                }
            },
            [],
        ),
        _spec(
            "dataset_query",
            "Query a dataset by name or id. Returns index_context and query_hints for planning.",
            {
                "dataset_name": {"type": "string", "description": "Dataset name from dataset_list."},
                "dataset_id": {"type": "string", "description": "Dataset id hex string."},
                "pipeline": {
                    "type": "array",
                    "description": "Aggregation pipeline stages.",
                    "items": {"type": "object"},
                },
                "filter": {"type": "object", "description": "Find filter when pipeline omitted."},
                "limit": {"type": "integer", "description": "Max results.", "default": 20},
            },
            [],
        ),
    ]
