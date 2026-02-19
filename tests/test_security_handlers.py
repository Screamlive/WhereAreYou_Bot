import os
import tempfile
import unittest

try:
    import aiogram  # noqa: F401
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.fsm.storage.base import StorageKey
    HAS_AIOGRAM = True
except ModuleNotFoundError:
    HAS_AIOGRAM = False


class FakeUser:
    def __init__(self, user_id: int, username: str | None = None):
        self.id = user_id
        self.username = username


class FakeChat:
    def __init__(self, chat_id: int):
        self.id = chat_id


class FakeMessage:
    def __init__(self, text: str, user_id: int):
        self.text = text
        self.from_user = FakeUser(user_id)
        self.chat = FakeChat(user_id)
        self.responses: list[dict] = []

    async def answer(self, text: str, reply_markup=None):
        self.responses.append({"text": text, "reply_markup": reply_markup})


class FakeCallbackQuery:
    def __init__(self, user_id: int, data: str, message: FakeMessage | None = None):
        self.from_user = FakeUser(user_id)
        self.data = data
        self.message = message or FakeMessage("", user_id)
        self.answers: list[dict] = []

    async def answer(self, text: str | None = None, show_alert: bool = False):
        self.answers.append({"text": text, "show_alert": show_alert})


class DummyBot:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})


if HAS_AIOGRAM:
    import config
    import database
    import db_repo
    from handlers import admin as admin_handlers
    from handlers import groups as groups_handlers
    from handlers import absences as absences_handlers
    from texts import (
        TEXT_NO_RIGHTS,
        TEXT_NO_RIGHTS_ADMIN,
        TEXT_NO_RIGHTS_ALERT,
        TEXT_NOT_YOUR_REQUEST,
        TEXT_NOT_APPROVED_SHORT,
    )


    class TestSecurityHandlers(unittest.IsolatedAsyncioTestCase):
        def setUp(self):
            fd, path = tempfile.mkstemp(prefix="bot_sec_db_", suffix=".db")
            os.close(fd)
            self.db_path = path

            config.DB_NAME = path
            database.DB_NAME = path
            db_repo.DB_NAME = path

            database.init_db()

            self.bot = DummyBot()
            admin_handlers.set_bot(self.bot)
            groups_handlers.set_bot(self.bot)
            absences_handlers.set_bot(self.bot)

            self.storage = MemoryStorage()

        def tearDown(self):
            if os.path.exists(self.db_path):
                os.remove(self.db_path)

        def make_state(self, user_id: int) -> FSMContext:
            key = StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)
            return FSMContext(storage=self.storage, key=key)

        async def test_non_superadmin_cannot_create_group(self):
            user_id = 10
            db_repo.upsert_user_registration(user_id, "u10", "User 10")
            db_repo.approve_user(user_id)

            msg = FakeMessage("Создать группу", user_id)
            state = self.make_state(user_id)
            await groups_handlers.create_group_start(msg, state)

            self.assertTrue(msg.responses)
            self.assertEqual(msg.responses[0]["text"], TEXT_NO_RIGHTS)

        async def test_non_admin_cannot_view_absence_requests(self):
            user_id = 20
            db_repo.upsert_user_registration(user_id, "u20", "User 20")
            db_repo.approve_user(user_id)

            msg = FakeMessage("Заявки на отсутствие", user_id)
            await absences_handlers.show_absence_requests(msg)

            self.assertTrue(msg.responses)
            self.assertEqual(msg.responses[0]["text"], TEXT_NO_RIGHTS_ADMIN)

        async def test_non_admin_cannot_approve_group_request(self):
            # create group and request
            db_repo.create_group("Dept", created_by=1)
            group_id, _ = db_repo.list_all_groups()[0]
            user_id = 30
            db_repo.upsert_user_registration(user_id, "u30", "User 30")
            db_repo.approve_user(user_id)
            req_id = db_repo.create_group_request(user_id, group_id, "join", requested_by=user_id)

            cb = FakeCallbackQuery(999, f"grp_req_approve:{req_id}")
            await groups_handlers.handle_group_request(cb)

            self.assertTrue(cb.answers)
            self.assertEqual(cb.answers[0]["text"], TEXT_NO_RIGHTS_ALERT)
            self.assertTrue(cb.answers[0]["show_alert"])

        async def test_group_admin_cannot_approve_other_group_absence(self):
            # Admin in group A
            admin_id = 40
            db_repo.upsert_user_registration(admin_id, "ga", "Group Admin")
            db_repo.approve_user(admin_id)
            db_repo.create_group("A", created_by=1)
            db_repo.create_group("B", created_by=1)
            groups = db_repo.list_all_groups()
            group_a = groups[0][0]
            group_b = groups[1][0]
            db_repo.add_group_membership(admin_id, group_a, "admin", created_by=1)
            db_repo.set_last_group_id(admin_id, group_a)

            # User in group B with pending absence
            user_id = 41
            db_repo.upsert_user_registration(user_id, "u41", "User 41")
            db_repo.approve_user(user_id)
            db_repo.add_group_membership(user_id, group_b, "member", created_by=1)
            abs_id = db_repo.create_absence(user_id, "vacation", "2026-01-01", "2026-01-02", "", "pending")

            cb = FakeCallbackQuery(admin_id, f"approve_abs:{abs_id}")
            await absences_handlers.callback_absence_approval(cb)

            self.assertTrue(cb.answers)
            self.assertEqual(cb.answers[0]["text"], TEXT_NO_RIGHTS_ALERT)
            self.assertTrue(cb.answers[0]["show_alert"])

        async def test_user_cannot_delete_foreign_absence(self):
            owner_id = 50
            other_id = 51
            db_repo.upsert_user_registration(owner_id, "o", "Owner")
            db_repo.approve_user(owner_id)
            db_repo.upsert_user_registration(other_id, "x", "Other")
            db_repo.approve_user(other_id)

            abs_id = db_repo.create_absence(owner_id, "vacation", "2026-01-01", "2026-01-01", "", "approved")

            cb = FakeCallbackQuery(other_id, f"request_del:{abs_id}")
            await absences_handlers.request_delete_absence(cb)

            self.assertTrue(cb.answers)
            self.assertEqual(cb.answers[0]["text"], TEXT_NOT_YOUR_REQUEST)
            self.assertTrue(cb.answers[0]["show_alert"])

        async def test_unapproved_user_cannot_add_absence(self):
            user_id = 60
            db_repo.upsert_user_registration(user_id, "u60", "User 60")
            # not approved
            msg = FakeMessage("Добавить отсутствие", user_id)
            state = self.make_state(user_id)
            await absences_handlers.add_absence_start(msg, state)

            self.assertTrue(msg.responses)
            self.assertEqual(msg.responses[0]["text"], TEXT_NOT_APPROVED_SHORT)

        async def test_viewer_can_view_absence_requests_read_only(self):
            viewer_id = 70
            member_id = 71
            db_repo.create_group("View Team", created_by=1)
            group_id, _ = db_repo.list_all_groups()[0]

            db_repo.upsert_user_registration(viewer_id, "viewer70", "Viewer 70")
            db_repo.approve_user(viewer_id)
            db_repo.add_group_membership(viewer_id, group_id, "viewer", created_by=1)
            db_repo.set_last_group_id(viewer_id, group_id)

            db_repo.upsert_user_registration(member_id, "member71", "Member 71")
            db_repo.approve_user(member_id)
            db_repo.add_group_membership(member_id, group_id, "member", created_by=1)
            db_repo.create_absence(member_id, "vacation", "2026-01-10", "2026-01-11", "", "pending")

            msg = FakeMessage("Заявки на отсутствие", viewer_id)
            await absences_handlers.show_absence_requests(msg)

            self.assertTrue(msg.responses)
            self.assertIn("режим наблюдателя", msg.responses[-1]["text"])

        async def test_viewer_cannot_approve_absence(self):
            viewer_id = 80
            member_id = 81
            db_repo.create_group("View Team 2", created_by=1)
            group_id, _ = db_repo.list_all_groups()[0]

            db_repo.upsert_user_registration(viewer_id, "viewer80", "Viewer 80")
            db_repo.approve_user(viewer_id)
            db_repo.add_group_membership(viewer_id, group_id, "viewer", created_by=1)
            db_repo.set_last_group_id(viewer_id, group_id)

            db_repo.upsert_user_registration(member_id, "member81", "Member 81")
            db_repo.approve_user(member_id)
            db_repo.add_group_membership(member_id, group_id, "member", created_by=1)
            abs_id = db_repo.create_absence(member_id, "vacation", "2026-01-10", "2026-01-11", "", "pending")

            cb = FakeCallbackQuery(viewer_id, f"approve_abs:{abs_id}")
            await absences_handlers.callback_absence_approval(cb)

            self.assertTrue(cb.answers)
            self.assertEqual(cb.answers[0]["text"], TEXT_NO_RIGHTS_ALERT)
            self.assertTrue(cb.answers[0]["show_alert"])

        async def test_edit_request_notification_contains_overlaps_for_admin(self):
            group_id = None
            editor_id = 90
            admin_id = 91
            other_id = 92

            db_repo.create_group("Overlap Team", created_by=1)
            group_id, _ = db_repo.list_all_groups()[0]

            db_repo.upsert_user_registration(editor_id, "editor90", "Editor 90")
            db_repo.upsert_user_registration(admin_id, "admin91", "Admin 91")
            db_repo.upsert_user_registration(other_id, "other92", "Other 92")
            db_repo.approve_user(editor_id)
            db_repo.approve_user(admin_id)
            db_repo.approve_user(other_id)

            db_repo.add_group_membership(editor_id, group_id, "member", created_by=1)
            db_repo.add_group_membership(admin_id, group_id, "admin", created_by=1)
            db_repo.add_group_membership(other_id, group_id, "member", created_by=1)

            abs_id = db_repo.create_absence(
                editor_id, "vacation", "2026-01-01", "2026-01-01", "", "approved"
            )
            db_repo.create_absence(
                other_id, "sick", "2026-01-11", "2026-01-12", "", "approved"
            )

            state = self.make_state(editor_id)
            await state.update_data(
                abs_id=abs_id,
                new_cat="vacation",
                new_start_date="2026-01-10",
                new_end_date="2026-01-12",
            )
            await state.set_state(absences_handlers.EditAbsenceFSM.waiting_for_new_comment)

            msg = FakeMessage("-", editor_id)
            await absences_handlers.edit_absence_comment(msg, state)

            admin_msgs = [m["text"] for m in self.bot.sent if m["chat_id"] == admin_id]
            self.assertTrue(admin_msgs)
            self.assertTrue(any("Пересечения" in text for text in admin_msgs))

else:

    class TestSecurityHandlers(unittest.TestCase):
        @unittest.skip("aiogram is not installed")
        def test_skip(self):
            pass


if __name__ == "__main__":
    unittest.main()
