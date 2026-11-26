"""HTTP checks for atomic two-task moves."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.app import create_server


class BatchTasksApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="task-board-batch-api-")
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

    def post_single_move(self, task_id: str) -> int:
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
            return response.code

    def post_batch_move(self, task_ids: list[str]) -> tuple[int, dict[str, object]]:
        request = Request(
            f"{self.base_url}/api/tasks/move-selected-to-done",
            data=json.dumps({"task_ids": task_ids}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.code, json.loads(response.read())

    def test_batch_move_moves_both_selected_tasks(self) -> None:
        status_code, body = self.post_batch_move(["task-1", "task-2"])

        with self.subTest("batch request succeeds"):
            self.assertEqual(status_code, 200, body)
            self.assertEqual(body, {"ids": ["task-1", "task-2"], "list": "done"})
        with self.subTest("both task rows move together"):
            self.assertEqual(
                self.get_tasks(),
                {
                    "lists": {
                        "todo": [],
                        "done": [
                            {"id": "task-1", "title": "Write one small test"},
                            {"id": "task-2", "title": "Check the board state"},
                        ],
                    }
                },
            )

    def test_invalid_mixed_batch_leaves_both_task_rows_unchanged(self) -> None:
        # Set up one To do task and one Done task through the existing one-task API.
        self.assertEqual(self.post_single_move("task-2"), 200)
        before = self.get_tasks()

        status_code, _ = self.post_batch_move(["task-1", "task-2"])
        after = self.get_tasks()

        with self.subTest("mixed batch is rejected"):
            self.assertEqual(status_code, 409)
        with self.subTest("neither task row changes on rejection"):
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
