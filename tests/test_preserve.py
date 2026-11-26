import unittest

from board import move_selected


class PreserveTests(unittest.TestCase):
    def test_other_task_stays(self):
        self.assertEqual(move_selected({"a": "todo", "b": "todo"}, "a")["b"], "todo")
