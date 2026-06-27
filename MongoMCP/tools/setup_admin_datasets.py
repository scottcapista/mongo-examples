#!/usr/bin/env python3
"""Create indexes for admin dataset collections."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webui"))

from dataset_service import ensure_indexes


def main():
    ensure_indexes()
    print("Admin dataset indexes ensured.")


if __name__ == "__main__":
    main()
