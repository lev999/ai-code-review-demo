import unittest

from api.task_text import normalize_title


class NormalizeTitleTests(unittest.TestCase):
    def test_strips_only_outer_whitespace(self):
        self.assertEqual(normalize_title("  Write  one small test \n"), "Write  one small test")


if __name__ == "__main__":
    unittest.main()
