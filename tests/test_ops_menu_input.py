import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from app.ops import menu


class MenuInputValidationTests(unittest.TestCase):
    def test_confirm_retries_until_valid(self):
        with patch("builtins.input", side_effect=["maybe", "y"]):
            with redirect_stdout(StringIO()):
                result = menu._confirm("Продолжить?", default=False)
        self.assertTrue(result)

    def test_confirm_accepts_no(self):
        with patch("builtins.input", side_effect=["n"]):
            with redirect_stdout(StringIO()):
                result = menu._confirm("Продолжить?", default=True)
        self.assertFalse(result)

    def test_choose_retries_until_valid_number(self):
        items = [("a", "A"), ("b", "B")]
        with patch("builtins.input", side_effect=["abc", "9", "2"]):
            with redirect_stdout(StringIO()):
                selected = menu._choose("Тест", items)
        self.assertEqual(selected, "b")

    def test_confirm_send_requires_explicit_send(self):
        with patch("builtins.input", side_effect=["oops", "SEND"]):
            with redirect_stdout(StringIO()):
                result = menu._confirm_send()
        self.assertTrue(result)

    def test_choose_user_from_directory_returns_selected_id(self):
        users = [
            (2, "Бета Б.Б.", "beta"),
            (1, "Альфа А.А.", "alpha"),
        ]
        with patch("builtins.input", side_effect=["1"]):
            with redirect_stdout(StringIO()):
                selected = menu._choose_user_from_directory("Тест", users)
        self.assertEqual(selected, 1)

    def test_choose_returns_back_token_when_enabled(self):
        with patch("builtins.input", side_effect=["2"]):
            with redirect_stdout(StringIO()):
                selected = menu._choose("Тест", [("a", "A")], allow_back=True, back_label="Назад")
        self.assertEqual(selected, menu.MENU_BACK)


if __name__ == "__main__":
    unittest.main()
