#!/usr/bin/env python3
"""Initialize local runtime databases for the book loop."""
from research_common import DB_PATH, init_db

if __name__ == "__main__":
    init_db()
    print(f"initialized {DB_PATH}")
