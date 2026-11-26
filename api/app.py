"""Small standard-library HTTP server for the task-board demo."""

from __future__ import annotations

import json
import os
import re
import sys
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from api.db import connect, initialize


ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = ROOT / "web"
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "tasks.sqlite3"
TASK_MOVE_PATH = re.compile(r"^/api/tasks/([^/]+)/move-to-done$")
STATIC_FILES = {
    "/src/app.js": (WEB_ROOT / "src" / "app.js", "text/javascript; charset=utf-8"),
    "/src/task_state.js": (WEB_ROOT / "src" / "task_state.js", "text/javascript; charset=utf-8"),
    "/styles.css": (WEB_ROOT / "styles.css", "text/css; charset=utf-8"),
}


def handler_for(db_path: str | Path):
    class BoardHandler(BaseHTTPRequestHandler):
        def send_bytes(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status: int, value: object) -> None:
            self.send_bytes(status, json.dumps(value).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/tasks":
                with closing(connect(db_path)) as connection:
                    rows = connection.execute(
                        "SELECT id, title, list_name FROM tasks ORDER BY list_name, position, id"
                    ).fetchall()
                lists = {"todo": [], "done": []}
                for row in rows:
                    lists[row["list_name"]].append(
                        {"id": row["id"], "title": row["title"].strip()}
                    )
                self.send_json(200, {"lists": lists})
                return

            static_file = (WEB_ROOT / "index.html", "text/html; charset=utf-8") if path == "/" else STATIC_FILES.get(path)
            if static_file is None:
                self.send_json(404, {"error": "Not found"})
                return
            file_path, content_type = static_file
            self.send_bytes(200, file_path.read_bytes(), content_type)

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            match = TASK_MOVE_PATH.fullmatch(path)
            if match is None:
                self.send_json(404, {"error": "Not found"})
                return

            task_id = unquote(match.group(1))
            with closing(connect(db_path)) as connection:
                # Lock the rows before checking state so concurrent move
                # requests cannot both act on the same To do task.
                connection.execute("BEGIN IMMEDIATE")
                task = connection.execute(
                    "SELECT list_name FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()

                if task is None:
                    connection.rollback()
                    result = (404, {"error": "Task not found"})
                elif task["list_name"] != "todo":
                    connection.rollback()
                    result = (409, {"error": "Task is not in To do"})
                else:
                    next_position = connection.execute(
                        "SELECT COALESCE(MAX(position), -1) + 1 FROM tasks WHERE list_name = 'done'"
                    ).fetchone()[0]
                    updated = connection.execute(
                        "UPDATE tasks SET list_name = 'done', position = ? "
                        "WHERE id = ? AND list_name = 'todo'",
                        (next_position, task_id),
                    )
                    if updated.rowcount != 1:
                        connection.rollback()
                        result = (409, {"error": "Task is not in To do"})
                    else:
                        connection.commit()
                        result = (200, {"id": task_id, "list": "done"})

            self.send_json(*result)

        def log_message(self, format: str, *args: object) -> None:
            # Keep local and CI output free of host-specific request details.
            return

    return BoardHandler


def create_server(db_path: str | Path | None = None, port: int = 0) -> HTTPServer:
    selected_path = Path(db_path or os.environ.get("DEMO_DB_PATH") or DEFAULT_DB_PATH)
    initialize(selected_path)
    return HTTPServer(("127.0.0.1", port), handler_for(selected_path))


def main() -> None:
    arguments = sys.argv[1:]
    if len(arguments) == 1:
        db_path = arguments[0]
    elif len(arguments) == 0:
        db_path = os.environ.get("DEMO_DB_PATH") or DEFAULT_DB_PATH
    else:
        raise SystemExit("Usage: python3 -m api.app [database-path]")

    server = create_server(db_path)
    print(server.server_address[1], flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
