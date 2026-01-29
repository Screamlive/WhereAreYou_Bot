import unittest

from utils import format_date_display


class TestUtils(unittest.TestCase):
    def test_format_date_display(self):
        self.assertEqual(format_date_display("2026-01-31"), "31.01.2026")
        self.assertEqual(format_date_display("31.01.2026"), "31.01.2026")
        self.assertEqual(format_date_display(None), "—")
        self.assertEqual(format_date_display("bad"), "bad")


if __name__ == "__main__":
    unittest.main()
