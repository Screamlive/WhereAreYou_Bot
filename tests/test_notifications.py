import os
import tempfile
import unittest

import config
import database
import db_repo
import notifications


class TestNotifications(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(prefix="bot_notify_db_", suffix=".db")
        os.close(fd)
        self.db_path = path

        config.DB_NAME = path
        database.DB_NAME = path
        db_repo.DB_NAME = path

        database.init_db()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_group_admin_notifications(self):
        db_repo.create_group("Dept 1", created_by=1)
        group_id, _name = db_repo.list_all_groups()[0]

        admin_id = 10
        user_id = 11
        db_repo.upsert_user_registration(admin_id, "ga", "Group Admin")
        db_repo.upsert_user_registration(user_id, "u1", "User 1")
        db_repo.approve_user(admin_id)
        db_repo.approve_user(user_id)
        db_repo.add_group_membership(admin_id, group_id, "admin", created_by=1)
        db_repo.add_group_membership(user_id, group_id, "member", created_by=1)

        db_repo.create_group_request(user_id, group_id, "join", requested_by=user_id)
        db_repo.create_absence(user_id, "vacation", "2026-02-01", "2026-02-02", "", "pending")

        notes = notifications.build_group_admin_notifications()
        self.assertIn(admin_id, notes)
        self.assertIn("Dept 1", notes[admin_id])
        self.assertIn("заявки на вступление", notes[admin_id])
        self.assertIn("заявки на отсутствие", notes[admin_id])

    def test_superadmin_notifications(self):
        super_id = 20
        db_repo.upsert_user_registration(super_id, "sa", "Super Admin")
        db_repo.promote_to_admin(super_id)
        db_repo.approve_user(super_id)

        user_id = 21
        db_repo.upsert_user_registration(user_id, "u2", "User 2")
        # is_approved=0 -> pending registration

        notes = notifications.build_superadmin_notifications()
        self.assertIn(super_id, notes)
        self.assertIn("Новых заявок на регистрацию", notes[super_id])
        self.assertIn("User 2", notes[super_id])

    def test_no_notifications_when_empty(self):
        db_repo.create_group("Dept 2", created_by=1)
        notes = notifications.build_group_admin_notifications()
        self.assertEqual(notes, {})

        notes_sa = notifications.build_superadmin_notifications()
        self.assertEqual(notes_sa, {})


if __name__ == "__main__":
    unittest.main()
