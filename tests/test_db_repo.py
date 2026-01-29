import os
import tempfile
import unittest

import config
import database
import db_repo


class TestDbRepo(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(prefix="bot_test_db_", suffix=".db")
        os.close(fd)
        self.db_path = path

        config.DB_NAME = path
        database.DB_NAME = path
        db_repo.DB_NAME = path

        database.init_db()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_user_registration_and_roles(self):
        tg_id = 1001
        db_repo.upsert_user_registration(tg_id, "testuser", "Test User")

        status = db_repo.get_user_approval_status(tg_id)
        self.assertEqual(status, 0)

        self.assertTrue(db_repo.approve_user(tg_id))
        self.assertTrue(db_repo.is_user_approved(tg_id))

        self.assertTrue(db_repo.promote_to_admin(tg_id))
        self.assertTrue(db_repo.is_user_admin(tg_id))

        self.assertTrue(db_repo.revoke_admin(tg_id))
        self.assertFalse(db_repo.is_user_admin(tg_id))

        self.assertTrue(db_repo.update_user_fullname(tg_id, "New Name"))
        row = db_repo.get_user_name_and_username(tg_id)
        self.assertEqual(row, ("New Name", "testuser"))

    def test_groups_and_memberships(self):
        self.assertTrue(db_repo.create_group("Team A", created_by=1))
        self.assertFalse(db_repo.create_group("Team A", created_by=1))

        groups = db_repo.list_all_groups()
        self.assertEqual(len(groups), 1)
        group_id, _name = groups[0]

        db_repo.upsert_user_registration(2001, "u1", "User One")
        db_repo.add_group_membership(2001, group_id, "admin", created_by=1)

        role = db_repo.get_group_membership_role(2001, group_id)
        self.assertEqual(role, "admin")

        self.assertTrue(db_repo.update_group_membership_role(2001, group_id, "member"))
        role = db_repo.get_group_membership_role(2001, group_id)
        self.assertEqual(role, "member")

        admins = db_repo.list_group_admin_users(group_id)
        self.assertEqual(admins, [])

        self.assertTrue(db_repo.remove_user_from_group(2001, group_id))
        self.assertIsNone(db_repo.get_group_membership_role(2001, group_id))

    def test_group_requests(self):
        self.assertTrue(db_repo.create_group("Team B", created_by=1))
        group_id, _name = db_repo.list_all_groups()[0]

        db_repo.upsert_user_registration(3001, "u2", "User Two")

        req_id = db_repo.create_group_request(3001, group_id, "join", requested_by=3001)
        pending = db_repo.list_pending_group_requests("join", group_id)
        self.assertTrue(any(r[0] == req_id for r in pending))

        row = db_repo.get_group_request(req_id)
        self.assertEqual(row[3], "pending")

        db_repo.set_group_request_status(req_id, "approved", "2026-01-01T00:00:00", 1)
        row = db_repo.get_group_request(req_id)
        self.assertEqual(row[3], "approved")

    def test_absences_and_edits(self):
        tg_id = 4001
        db_repo.upsert_user_registration(tg_id, "u3", "User Three")

        abs_id = db_repo.create_absence(tg_id, "vacation", "2026-01-10", "2026-01-12", "", "pending")
        row = db_repo.get_absence_by_id(abs_id)
        self.assertEqual(row[0], tg_id)
        self.assertEqual(row[5], "pending")

        db_repo.update_absence_status(abs_id, "approved")
        row = db_repo.get_absence_by_id(abs_id)
        self.assertEqual(row[5], "approved")

        rows = db_repo.list_user_absences(tg_id)
        self.assertEqual(len(rows), 1)

        req_id = db_repo.create_edit_request(abs_id, "sick", "2026-01-11", "2026-01-12", "note", tg_id)
        edit = db_repo.get_edit_request(req_id)
        self.assertEqual(edit[0], abs_id)

        db_repo.delete_edit_request(req_id)
        self.assertIsNone(db_repo.get_edit_request(req_id))

        db_repo.update_absence(abs_id, "sick", "2026-01-11", "2026-01-12", "note")
        row = db_repo.get_absence_by_id(abs_id)
        self.assertEqual(row[1], "sick")

        approved_between = db_repo.list_approved_absences_between("2026-01-01", "2026-01-31")
        self.assertTrue(len(approved_between) >= 1)

        approved_for_day = db_repo.list_approved_absences_for_date("2026-01-11")
        self.assertTrue(len(approved_for_day) >= 1)

        db_repo.delete_absence(abs_id)
        self.assertIsNone(db_repo.get_absence_by_id(abs_id))


if __name__ == "__main__":
    unittest.main()
