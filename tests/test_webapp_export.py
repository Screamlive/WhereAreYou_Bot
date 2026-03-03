import unittest
import zipfile
from io import BytesIO

from webapp_export import (
    build_overlaps_export_filename,
    build_overlaps_export_rows,
    build_overlaps_xlsx,
)


class TestWebAppExport(unittest.TestCase):
    def _sample_payload(self) -> dict:
        return {
            "scope": {
                "type": "group",
                "group_id": 7,
                "group_name": "QA Team",
            },
            "period": {
                "year": 2026,
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "is_custom": True,
            },
            "filters": {
                "statuses": ["approved", "pending"],
                "categories": ["vacation"],
                "query": "Иван",
            },
            "users": [
                {
                    "user_id": 100,
                    "fullname": "Иванов И.И.",
                    "username": "ivanov",
                },
            ],
            "intervals": [
                {
                    "absence_id": 55,
                    "user_id": 100,
                    "category": "vacation",
                    "start_date": "2026-03-10",
                    "end_date": "2026-03-12",
                    "comment": "Отпуск",
                    "status": "approved",
                }
            ],
            "meta": {
                "total_users": 1,
                "total_intervals": 1,
            },
        }

    def test_build_rows_contains_filters_and_interval(self):
        rows = build_overlaps_export_rows(self._sample_payload())
        flat_values = [value for row in rows for value in row]
        self.assertIn("Выгрузка пересечений отсутствий", flat_values)
        self.assertIn("Группа: QA Team", flat_values)
        self.assertIn("01.03.2026 - 31.03.2026", flat_values)
        self.assertIn("Иванов И.И.", flat_values)
        self.assertIn("@ivanov", flat_values)
        self.assertIn("Отпуск", flat_values)
        self.assertIn("10.03.2026", flat_values)
        self.assertIn("12.03.2026", flat_values)
        self.assertIn("Одобрено", flat_values)

    def test_build_xlsx_has_sheet_and_filename(self):
        payload = self._sample_payload()
        body = build_overlaps_xlsx(payload)
        self.assertGreater(len(body), 100)

        archive = zipfile.ZipFile(BytesIO(body))
        names = set(archive.namelist())
        self.assertIn("xl/workbook.xml", names)
        self.assertIn("xl/worksheets/sheet1.xml", names)

        filename = build_overlaps_export_filename(payload)
        self.assertEqual(filename, "overlaps_group_7_20260301_20260331.xlsx")


if __name__ == "__main__":
    unittest.main()
