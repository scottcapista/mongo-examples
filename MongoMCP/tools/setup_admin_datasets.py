#!/usr/bin/env python3
"""Create indexes for admin dataset collections."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webui"))

from local_settings import settings
from dataset_service import ensure_indexes
from mongomcp.datasets.discovery import ensure_dataset_indexes


def main():
    ensure_dataset_indexes(settings)
    print("Admin dataset indexes ensured.")


if __name__ == "__main__":
    main()
