import unittest

from app.use_cases.absence_views import (
    build_admin_delete_absences_report,
    build_admin_edit_absence_label,
    build_admin_edit_current_text,
    build_my_absences_report,
    build_user_absences_report,
)


class TestAbsenceViewsUseCases(unittest.TestCase):
    def test_build_my_absences_report(self):
        rows = [
            (1, "vacation", "2026-01-10", "2026-01-12", "", "approved"),
            (2, "sick", "2026-02-01", "2026-02-01", "больничный", "pending"),
        ]
        text = build_my_absences_report(rows)
        self.assertIn("Ваши заявки:", text)
        self.assertIn("#1 — vacation, 10.01.2026–12.01.2026, статус=approved, коммент: —", text)
        self.assertIn("#2 — sick, 01.02.2026–01.02.2026, статус=pending, коммент: больничный", text)

    def test_build_user_absences_report(self):
        rows = [
            (10, "dayoff", "2026-03-05", "2026-03-05", "", "approved"),
        ]
        text = build_user_absences_report("Иванов И.И.", rows)
        self.assertTrue(text.startswith("Отсутствия Иванов И.И.:"))
        self.assertIn("- dayoff 05.03.2026–05.03.2026, [approved], —", text)

    def test_build_admin_delete_absences_report(self):
        rows = [
            (7, "other", "2026-04-01", "2026-04-02", "коммент", "declined"),
        ]
        text = build_admin_delete_absences_report("Петров П.П.", rows)
        self.assertIn("Отсутствия Петров П.П.:", text)
        self.assertIn("#7 other 01.04.2026–02.04.2026, [declined], коммент", text)

    def test_build_admin_edit_absence_label(self):
        label = build_admin_edit_absence_label(42, "vacation", "2026-06-01", "2026-06-03", "approved")
        self.assertEqual(label, "#42 vacation 01.06.2026–03.06.2026 [approved]")

    def test_build_admin_edit_current_text(self):
        text = build_admin_edit_current_text("sick", "2026-07-10", "2026-07-12", "", "pending")
        self.assertIn("Текущие данные: sick 10.07.2026–12.07.2026", text)
        self.assertIn("коммент: —", text)
        self.assertIn("статус=pending", text)


if __name__ == "__main__":
    unittest.main()
