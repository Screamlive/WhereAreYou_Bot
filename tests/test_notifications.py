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

    def test_superadmin_notifications_respect_selected_scope(self):
        super_id = 30
        db_repo.upsert_user_registration(super_id, "sa30", "Super Admin 30")
        db_repo.promote_to_admin(super_id)
        db_repo.approve_user(super_id)

        db_repo.create_group("Dept A", created_by=1)
        db_repo.create_group("Dept B", created_by=1)
        groups = db_repo.list_all_groups()
        group_a = groups[0][0]
        group_b = groups[1][0]

        user_a = 31
        user_b = 32
        db_repo.upsert_user_registration(user_a, "u31", "User A")
        db_repo.upsert_user_registration(user_b, "u32", "User B")
        db_repo.approve_user(user_a)
        db_repo.approve_user(user_b)

        db_repo.add_group_membership(user_a, group_a, "member", created_by=1)
        db_repo.add_group_membership(user_b, group_b, "member", created_by=1)

        db_repo.create_group_request(user_a, group_a, "join", requested_by=user_a)
        db_repo.create_group_request(user_b, group_b, "join", requested_by=user_b)

        db_repo.set_superadmin_notification_scope(super_id, group_a)
        notes = notifications.build_superadmin_notifications()

        self.assertIn(super_id, notes)
        self.assertIn("режим: selected_groups", notes[super_id])
        self.assertIn("Dept A", notes[super_id])
        self.assertNotIn("Dept B", notes[super_id])


if __name__ == "__main__":
    unittest.main()
