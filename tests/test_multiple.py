import unittest

from board import move_selected


class MultipleTests(unittest.TestCase):
    def test_all_selected_tasks_move(self):
        tasks = {"a": "todo", "b": "todo", "c": "todo"}
        self.assertEqual(move_selected(tasks, ["a", "c"]), {"a": "done", "b": "todo", "c": "done"})
