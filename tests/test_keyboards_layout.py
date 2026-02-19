import unittest

import keyboards


def _row_texts(menu) -> list[list[str]]:
    return [[btn.text for btn in row] for row in menu.keyboard]


class TestKeyboardLayout(unittest.TestCase):
    def test_long_two_column_row_is_split(self):
        long_label = "X" * (keyboards.TWO_COLUMN_MAX_LABEL_LEN + 1)
        menu = keyboards._build_menu([[long_label, "short"]])
        rows = _row_texts(menu)
        self.assertEqual(rows, [[long_label], ["short"]])

    def test_today_button_is_on_top_superadmin(self):
        rows = _row_texts(keyboards.superadmin_main_menu)
        self.assertEqual(rows[0][0], "Отсутствия на сегодня")
        flattened = {text for row in rows for text in row}
        self.assertIn("Фильтр по группе", flattened)

    def test_today_button_is_on_top_group_admin(self):
        rows = _row_texts(keyboards.group_admin_main_menu)
        self.assertEqual(rows[0][0], "Отсутствия на сегодня")

    def test_group_admin_absences_menu_starts_from_today(self):
        rows = _row_texts(keyboards.group_admin_absences_menu)
        self.assertEqual(rows[0][0], "Отсутствия на сегодня")
        self.assertEqual(rows[0][1], "Заявки на отсутствие")

    def test_superadmin_users_menu_compact_top_row(self):
        rows = _row_texts(keyboards.superadmin_users_menu)
        self.assertEqual(rows[0], ["Заявки регистрации", "Список пользователей"])

    def test_absences_menu_compact_rows(self):
        rows = _row_texts(keyboards.superadmin_absences_menu)
        self.assertEqual(rows[0], ["Отсутствия на сегодня", "Заявки на отсутствие"])
        self.assertEqual(rows[1], ["Отсутствия сотрудника", "Выгрузить в CSV"])

    def test_admin_absence_actions_use_distinct_labels(self):
        rows = _row_texts(keyboards.group_admin_absences_menu)
        flattened = {text for row in rows for text in row}
        self.assertIn("Изменить у сотрудника", flattened)
        self.assertIn("Удалить у сотрудника", flattened)
        self.assertNotIn("Изменить отсутствие", flattened)
        self.assertNotIn("Удалить отсутствие", flattened)

    def test_viewer_absences_menu_is_read_only(self):
        rows = _row_texts(keyboards.group_viewer_absences_menu)
        flattened = {text for row in rows for text in row}
        self.assertIn("Заявки на отсутствие", flattened)
        self.assertIn("Отсутствия сотрудника", flattened)
        self.assertIn("Выгрузить в CSV", flattened)
        self.assertNotIn("Добавить другому", flattened)
        self.assertNotIn("Изменить у сотрудника", flattened)
        self.assertNotIn("Удалить у сотрудника", flattened)

    def test_groups_menu_contains_viewer_role_request(self):
        rows = _row_texts(keyboards.user_groups_menu)
        flattened = {text for row in rows for text in row}
        self.assertIn("Запросить роль наблюдателя", flattened)

    def test_viewer_main_menu_requests_read_only_label(self):
        rows = _row_texts(keyboards.group_viewer_main_menu)
        flattened = {text for row in rows for text in row}
        self.assertIn("Заявки (просмотр)", flattened)


if __name__ == "__main__":
    unittest.main()
