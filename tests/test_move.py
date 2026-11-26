import unittest

from board import move_selected


class MoveTests(unittest.TestCase):
    def test_selected_task_moves(self):
        self.assertEqual(move_selected({"a": "todo"}, "a"), {"a": "done"})
