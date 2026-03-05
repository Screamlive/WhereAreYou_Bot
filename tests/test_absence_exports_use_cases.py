import unittest

from app.use_cases.absence_exports import (
    CSV_HEADER,
    build_absence_export_csv_text,
    build_absence_export_filename,
    build_today_absences_report,
)


class TestAbsenceExportsUseCases(unittest.TestCase):
    def test_build_absence_export_filename_uses_display_dates(self):
        filename = build_absence_export_filename("2026-02-01", "2026-02-05")
        self.assertEqual(filename, "absences_01.02.2026_05.02.2026.csv")

    def test_build_absence_export_csv_text(self):
        rows = [
            (1, "vacation", "2026-01-01", "2026-01-10", "коммент;тест", "Иванов И.И.", "ivanov"),
            (2, "sick", "2026-02-02", "2026-02-02", "", "Петров П.П.", ""),
        ]
        text = build_absence_export_csv_text(rows)
        lines = text.splitlines()
        self.assertEqual(lines[0], CSV_HEADER)
        self.assertIn("Иванов И.И. (@ivanov);ivanov;vacation;01.01.2026;10.01.2026;коммент,тест", lines[1])
        self.assertIn("Петров П.П.;;sick;02.02.2026;02.02.2026;", lines[2])

    def test_build_today_absences_report(self):
        rows = [
            (1, "dayoff", "2026-03-01", "2026-03-01", "", "Сидоров С.С.", "sid"),
            (2, "other", "2026-03-01", "2026-03-02", "важно", "Кузнецов К.К.", ""),
        ]
        text = build_today_absences_report("01.03.2026", rows)
        self.assertIn("Отсутствия на сегодня (01.03.2026):", text)
        self.assertIn("Сидоров С.С. (dayoff, 01.03.2026 - 01.03.2026), комментарий: —", text)
        self.assertIn("Кузнецов К.К. (other, 01.03.2026 - 02.03.2026), комментарий: важно", text)


if __name__ == "__main__":
    unittest.main()
