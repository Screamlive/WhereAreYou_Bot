import unittest

from app.use_cases.absence_requests import (
    build_added_for_another_text,
    build_admin_request_submitted_text,
    build_target_user_added_text,
    build_user_request_submitted_text,
    normalize_comment,
)


class TestAbsenceRequestUseCases(unittest.TestCase):
    def test_normalize_comment(self):
        self.assertEqual(normalize_comment("  test  "), "test")
        self.assertEqual(normalize_comment("-"), "")

    def test_build_user_request_submitted_text(self):
        text = build_user_request_submitted_text(10, "vacation", "2026-01-02", "2026-01-03", "")
        self.assertIn("Заявка #10", text)
        self.assertIn("02.01.2026", text)
        self.assertIn("03.01.2026", text)
        self.assertIn("Комментарий: —", text)

    def test_build_admin_request_submitted_text(self):
        text = build_admin_request_submitted_text(
            "Иванов И.И.",
            11,
            "sick",
            "2026-02-01",
            "2026-02-02",
            "note",
        )
        self.assertIn("Иванов И.И. добавил заявку #11", text)
        self.assertIn("sick 01.02.2026–02.02.2026", text)
        self.assertIn("Комментарий: note (pending)", text)

    def test_build_admin_request_submitted_text_for_target(self):
        text = build_admin_request_submitted_text(
            "Петров П.П.",
            12,
            "dayoff",
            "2026-03-04",
            "2026-03-04",
            "",
            target_fullname="Сидоров С.С.",
        )
        self.assertIn("ДЛЯ Сидоров С.С.", text)
        self.assertIn("dayoff 04.03.2026–04.03.2026", text)
        self.assertIn("Комментарий: — (pending)", text)

    def test_build_added_for_another_text(self):
        text = build_added_for_another_text(
            13,
            "Тест Т.Т.",
            "vacation",
            "2026-04-10",
            "2026-04-11",
            "",
        )
        self.assertIn("Отсутствие #13 добавлено пользователю Тест Т.Т.", text)
        self.assertIn("10.04.2026–11.04.2026", text)

    def test_build_target_user_added_text(self):
        text = build_target_user_added_text(14, "other", "2026-05-01", "2026-05-01", "ok")
        self.assertIn("Вам добавлено отсутствие #14", text)
        self.assertIn("(other, 01.05.2026–01.05.2026)", text)
        self.assertIn("Комментарий: ok", text)


if __name__ == "__main__":
    unittest.main()
