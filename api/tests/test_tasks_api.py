"""HTTP-level checks for the task-board API contract."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.app import create_server
from api.db import connect


class TasksApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="task-board-api-")
        self.db_path = Path(self.temp_dir.name) / "tasks.sqlite3"
        self.server = create_server(self.db_path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp_dir.cleanup()

    def get_tasks(self) -> dict[str, object]:
        with urlopen(f"{self.base_url}/api/tasks", timeout=5) as response:
            self.assertEqual(response.status, 200)
            return json.loads(response.read())

    def post_move(self, task_id: str) -> tuple[int, dict[str, object]]:
        request = Request(
            f"{self.base_url}/api/tasks/{task_id}/move-to-done",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.code, json.loads(response.read())

    def test_get_returns_the_seeded_task_lists(self) -> None:
        self.assertEqual(
            self.get_tasks(),
            {
                "lists": {
                    "todo": [
                        {"id": "task-1", "title": "Write one small test"},
                        {"id": "task-2", "title": "Check the board state"},
                    ],
                    "done": [],
                }
            },
        )

    def test_move_changes_only_the_selected_task(self) -> None:
        before = self.get_tasks()
        status_code, body = self.post_move("task-1")
        after = self.get_tasks()

        with self.subTest("request succeeds"):
            self.assertEqual(status_code, 200, body)
            self.assertEqual(body, {"id": "task-1", "list": "done"})
        with self.subTest("both lists show only the selected task changed"):
            self.assertEqual(
                before["lists"],
                {
                    "todo": [
                        {"id": "task-1", "title": "Write one small test"},
                        {"id": "task-2", "title": "Check the board state"},
                    ],
                    "done": [],
                },
            )
            self.assertEqual(
                after["lists"],
                {
                    "todo": [{"id": "task-2", "title": "Check the board state"}],
                    "done": [{"id": "task-1", "title": "Write one small test"}],
                },
            )

    def test_unknown_task_returns_404(self) -> None:
        before = self.get_tasks()
        status_code, _ = self.post_move("missing-task")
        after = self.get_tasks()
        with self.subTest("unknown ID returns 404"):
            self.assertEqual(status_code, 404)
        with self.subTest("both seeded rows stay unchanged"):
            self.assertEqual(after, before)

    def test_task_outside_todo_returns_409(self) -> None:
        with closing(connect(self.db_path)) as connection:
            with connection:
                connection.execute("UPDATE tasks SET list_name = 'done' WHERE id = 'task-1'")
        before = self.get_tasks()
        status_code, _ = self.post_move("task-1")
        after = self.get_tasks()
        with self.subTest("task outside To do returns 409"):
            self.assertEqual(status_code, 409)
        with self.subTest("both seeded rows stay unchanged"):
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
