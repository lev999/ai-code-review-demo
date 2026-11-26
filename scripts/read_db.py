"""Print task IDs and their stored list names for browser evidence."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/read_db.py DATABASE_PATH")
    with sqlite3.connect(Path(sys.argv[1])) as connection:
        rows = connection.execute("SELECT id, list_name FROM tasks ORDER BY id").fetchall()
    print(json.dumps({task_id: list_name for task_id, list_name in rows}, sort_keys=True))


if __name__ == "__main__":
    main()
