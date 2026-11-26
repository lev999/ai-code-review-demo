"""SQLite setup and read helpers for the task-board demo."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


SEED_TASKS = (
    ("task-1", "Write one small test", "todo", 0),
    ("task-2", "Check the board state", "todo", 1),
)


def connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as connection:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    list_name TEXT NOT NULL CHECK (list_name IN ('todo', 'done')),
                    position INTEGER NOT NULL
                )
                """
            )
            count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            if count == 0:
                connection.executemany(
                    "INSERT INTO tasks (id, title, list_name, position) VALUES (?, ?, ?, ?)",
                    SEED_TASKS,
                )
