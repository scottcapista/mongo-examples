"""Constants for admin dataset discovery and querying."""

from __future__ import annotations

DATASETS_COL = "admin_datasets"
RECORDS_COL = "admin_dataset_records"
SOURCE_UPLOAD = "upload"
SOURCE_CLUSTER = "cluster"
DISCOVERY_OWNER = "system"

# MongoDB system / platform databases — never auto-discovered as datasets.
EXCLUDED_DATABASES = frozenset(
    {
        "admin",
        "local",
        "config",
        "mcp_config",
    }
)

# Collections to skip inside non-excluded databases (platform plumbing).
EXCLUDED_COLLECTION_PREFIXES = ("system.",)
