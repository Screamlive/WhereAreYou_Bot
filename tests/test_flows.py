import os
import tempfile
import unittest

import config
import database
import db_repo


class TestFlows(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(prefix="bot_flow_db_", suffix=".db")
        os.close(fd)
        self.db_path = path

        config.DB_NAME = path
        database.DB_NAME = path
        db_repo.DB_NAME = path

        database.init_db()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_group_join_flow(self):
        db_repo.create_group("Dept 1", created_by=1)
        group_id, _ = db_repo.list_all_groups()[0]

        user_id = 100
        db_repo.upsert_user_registration(user_id, "u100", "User 100")
        db_repo.approve_user(user_id)

        req_id = db_repo.create_group_request(user_id, group_id, "join", requested_by=user_id)
        row = db_repo.get_group_request(req_id)
        self.assertEqual(row[3], "pending")

        db_repo.add_group_membership(user_id, group_id, "member", created_by=1)
        db_repo.set_group_request_status(req_id, "approved", "2026-01-01T00:00:00", 1)

        self.assertTrue(db_repo.user_in_group(user_id, group_id))
        row = db_repo.get_group_request(req_id)
        self.assertEqual(row[3], "approved")

    def test_group_leave_flow(self):
        db_repo.create_group("Dept 2", created_by=1)
        group_id, _ = db_repo.list_all_groups()[0]

        user_id = 200
        db_repo.upsert_user_registration(user_id, "u200", "User 200")
        db_repo.approve_user(user_id)
        db_repo.add_group_membership(user_id, group_id, "member", created_by=1)

        req_id = db_repo.create_group_request(user_id, group_id, "leave", requested_by=user_id)
        db_repo.remove_user_from_group(user_id, group_id)
        db_repo.set_group_request_status(req_id, "approved", "2026-01-01T00:00:00", 1)

        self.assertFalse(db_repo.user_in_group(user_id, group_id))
        row = db_repo.get_group_request(req_id)
        self.assertEqual(row[3], "approved")

    def test_absence_approval_flow(self):
        user_id = 300
        db_repo.upsert_user_registration(user_id, "u300", "User 300")
        db_repo.approve_user(user_id)

        abs_id = db_repo.create_absence(user_id, "vacation", "2026-02-01", "2026-02-03", "", "pending")
        pending = db_repo.list_pending_absences()
        self.assertTrue(any(r[0] == abs_id for r in pending))

        db_repo.update_absence_status(abs_id, "approved")
        pending = db_repo.list_pending_absences()
        self.assertFalse(any(r[0] == abs_id for r in pending))

        approved_between = db_repo.list_approved_absences_between("2026-02-01", "2026-02-10")
        self.assertTrue(len(approved_between) >= 1)

    def test_edit_request_flow(self):
        user_id = 400
        db_repo.upsert_user_registration(user_id, "u400", "User 400")
        db_repo.approve_user(user_id)

        abs_id = db_repo.create_absence(user_id, "dayoff", "2026-03-01", "2026-03-01", "", "approved")
        req_id = db_repo.create_edit_request(abs_id, "sick", "2026-03-02", "2026-03-02", "note", user_id)
        self.assertIsNotNone(db_repo.get_edit_request(req_id))

        db_repo.update_absence(abs_id, "sick", "2026-03-02", "2026-03-02", "note")
        db_repo.delete_edit_request(req_id)

        self.assertIsNone(db_repo.get_edit_request(req_id))
        row = db_repo.get_absence_by_id(abs_id)
        self.assertEqual(row[1], "sick")


if __name__ == "__main__":
    unittest.main()
