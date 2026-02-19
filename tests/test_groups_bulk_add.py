import unittest
from unittest.mock import patch

from handlers import groups


def _button_texts(markup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _button_callbacks(markup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


class TestGroupBulkAddHelpers(unittest.TestCase):
    def test_paginate_users_clamps_page(self):
        users = [(i, f"User {i}", None) for i in range(1, 26)]
        page_items, safe_page, total_pages = groups._paginate_users(users, page=99, page_size=10)
        self.assertEqual(total_pages, 3)
        self.assertEqual(safe_page, 2)
        self.assertEqual(len(page_items), 5)

    def test_toggle_selected_user(self):
        self.assertEqual(groups._toggle_selected_user([], 10), [10])
        self.assertEqual(groups._toggle_selected_user([10], 10), [])
        self.assertEqual(groups._toggle_selected_user([10, 20], 15), [10, 15, 20])

    @patch("handlers.groups.get_group_name", return_value="Отдел 1")
    @patch("handlers.groups.get_group_membership_role")
    def test_build_picker_contains_controls_and_markers(self, mock_role, _mock_group_name):
        def role_side_effect(user_id, _group_id):
            return "member" if user_id == 2 else None

        mock_role.side_effect = role_side_effect
        users = [
            (1, "Иванов И.И.", "ivanov"),
            (2, "Петров П.П.", None),
        ]

        text, markup = groups._build_group_add_users_picker(
            group_id=7,
            users=users,
            selected_ids=[1],
            page=0,
        )

        self.assertIn("Группа: Отдел 1", text)
        self.assertIn("Выбрано: 1", text)

        texts = _button_texts(markup)
        callbacks = _button_callbacks(markup)

        self.assertIn("✅ Иванов И.И. (@ivanov)", texts)
        self.assertIn("⬜ Петров П.П. • уже в группе", texts)
        self.assertIn("Готово ✅", texts)
        self.assertIn("Сбросить выбор", texts)
        self.assertIn("Отмена", texts)
        self.assertIn("gm_toggle:1", callbacks)
        self.assertIn("gm_toggle:2", callbacks)
        self.assertIn("gm_apply", callbacks)
        self.assertIn("gm_reset", callbacks)
        self.assertIn("gm_cancel", callbacks)


if __name__ == "__main__":
    unittest.main()
