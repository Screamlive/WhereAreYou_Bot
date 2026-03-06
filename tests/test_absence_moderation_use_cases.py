import unittest

from app.use_cases.absence_moderation import (
    build_absence_decision,
    build_delete_decision,
    build_edit_approve_admin_text,
    build_edit_approve_user_text,
    build_edit_request_admin_text,
)


class TestAbsenceModerationUseCases(unittest.TestCase):
    def test_build_absence_decision_approve(self):
        decision = build_absence_decision(
            action="approve_abs",
            absence_id=42,
            category="vacation",
            start_date="2026-03-01",
            end_date="2026-03-05",
        )
        self.assertEqual(decision.new_status, "approved")
        self.assertIn("Заявка #42 одобрена.", decision.admin_text)
        self.assertIn("vacation 01.03.2026–05.03.2026", decision.user_text)

    def test_build_absence_decision_decline(self):
        decision = build_absence_decision(
            action="decline_abs",
            absence_id=7,
            category="sick",
            start_date="2026-01-10",
            end_date="2026-01-12",
        )
        self.assertEqual(decision.new_status, "declined")
        self.assertIn("Заявка #7 отклонена.", decision.admin_text)
        self.assertIn("sick 10.01.2026–12.01.2026", decision.user_text)

    def test_build_delete_decision_approve(self):
        decision = build_delete_decision(
            action="approve_del",
            absence_id=100,
            category="dayoff",
            start_date="2026-02-01",
            end_date="2026-02-01",
        )
        self.assertTrue(decision.should_delete)
        self.assertEqual(decision.log_text, "approve_del absence 100")

    def test_build_delete_decision_decline(self):
        decision = build_delete_decision(
            action="decline_del",
            absence_id=101,
            category="other",
            start_date="2026-02-02",
            end_date="2026-02-03",
        )
        self.assertFalse(decision.should_delete)
        self.assertEqual(decision.log_text, "decline_del absence 101")

    def test_build_edit_request_admin_text_contains_old_and_new(self):
        text = build_edit_request_admin_text(
            requester_fullname="Иванов И.И.",
            absence_id=5,
            old_category="vacation",
            old_start_date="2026-03-01",
            old_end_date="2026-03-05",
            old_comment="старый",
            new_category="sick",
            new_start_date="2026-03-02",
            new_end_date="2026-03-06",
            new_comment="новый",
        )
        self.assertIn("Пользователь Иванов И.И. хочет изменить заявку #5.", text)
        self.assertIn("Категория: vacation", text)
        self.assertIn("Даты: 01.03.2026–05.03.2026", text)
        self.assertIn("Категория: sick", text)
        self.assertIn("Даты: 02.03.2026–06.03.2026", text)

    def test_build_edit_approve_texts(self):
        admin_text = build_edit_approve_admin_text(
            absence_id=8,
            old_category="vacation",
            old_start_date="2026-04-10",
            old_end_date="2026-04-15",
            old_comment="",
            new_category="dayoff",
            new_start_date="2026-04-11",
            new_end_date="2026-04-11",
            new_comment="test",
        )
        user_text = build_edit_approve_user_text(
            absence_id=8,
            new_category="dayoff",
            new_start_date="2026-04-11",
            new_end_date="2026-04-11",
            new_comment="test",
        )
        self.assertIn("Изменение заявки #8 одобрено.", admin_text)
        self.assertIn("10.04.2026–15.04.2026", admin_text)
        self.assertIn("11.04.2026–11.04.2026", user_text)


if __name__ == "__main__":
    unittest.main()
