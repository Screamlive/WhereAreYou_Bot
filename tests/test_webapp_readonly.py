import os
import tempfile
import unittest

import config
import database
import db_repo
from webapp_readonly import (
    WebAppAccessError,
    get_absence_details_payload,
    get_overlaps_payload,
    get_webapp_profile,
    resolve_webapp_scope,
)


class TestWebAppReadonly(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(prefix="bot_webapp_test_", suffix=".db")
        os.close(fd)
        self.db_path = path

        config.DB_NAME = path
        database.DB_NAME = path
        db_repo.DB_NAME = path

        database.init_db()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_user(self, user_id: int, fullname: str, username: str = "") -> None:
        db_repo.upsert_user_registration(user_id, username, fullname)
        db_repo.approve_user(user_id)

    def test_profile_for_superadmin_has_all_scopes(self):
        self._create_user(100, "Super Admin", "sadmin")
        db_repo.promote_to_admin(100)
        db_repo.create_group("A Team", created_by=100)
        db_repo.create_group("B Team", created_by=100)
        group_id = db_repo.list_all_groups()[0][0]
        db_repo.set_last_group_id(100, group_id)

        profile = get_webapp_profile(100)
        self.assertEqual(profile["role"], "superadmin")
        self.assertEqual(profile["scopes"], ["global", "group", "superadmins"])
        self.assertEqual(profile["default_scope"]["type"], "group")
        self.assertEqual(profile["default_scope"]["group_id"], group_id)
        self.assertEqual(len(profile["groups"]), 2)

    def test_profile_for_member_has_group_scope_only(self):
        self._create_user(200, "Member User", "member")
        db_repo.create_group("Only Team", created_by=1)
        group_id = db_repo.list_all_groups()[0][0]
        db_repo.add_group_membership(200, group_id, "member", created_by=1)

        profile = get_webapp_profile(200)
        self.assertEqual(profile["role"], "user")
        self.assertEqual(profile["scopes"], ["group"])
        self.assertEqual(profile["default_scope"], {"type": "group", "group_id": group_id})

    def test_non_superadmin_cannot_select_global_scope(self):
        self._create_user(300, "Group Admin", "gadmin")
        db_repo.create_group("Team", created_by=1)
        group_id = db_repo.list_all_groups()[0][0]
        db_repo.add_group_membership(300, group_id, "admin", created_by=1)

        with self.assertRaises(WebAppAccessError) as ctx:
            resolve_webapp_scope(300, "global", None)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_overlaps_group_scope_is_restricted_by_acl(self):
        self._create_user(401, "Alice", "alice")
        self._create_user(402, "Bob", "bob")
        self._create_user(403, "Charlie", "charlie")

        db_repo.create_group("Group A", created_by=1)
        db_repo.create_group("Group B", created_by=1)
        group_a = db_repo.list_all_groups()[0][0]
        group_b = db_repo.list_all_groups()[1][0]

        db_repo.add_group_membership(401, group_a, "member", created_by=1)
        db_repo.add_group_membership(402, group_a, "member", created_by=1)
        db_repo.add_group_membership(403, group_b, "member", created_by=1)

        db_repo.create_absence(401, "vacation", "2026-02-01", "2026-02-03", "", "approved")
        db_repo.create_absence(402, "sick", "2026-02-02", "2026-02-04", "", "pending")
        db_repo.create_absence(403, "dayoff", "2026-02-02", "2026-02-02", "", "approved")

        payload = get_overlaps_payload(401, scope_type="group", group_id=group_a, year=2026)
        interval_user_ids = {row["user_id"] for row in payload["intervals"]}
        self.assertEqual(interval_user_ids, {401, 402})

        with self.assertRaises(WebAppAccessError) as ctx:
            get_overlaps_payload(401, scope_type="group", group_id=group_b, year=2026)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_overlaps_superadmins_scope_returns_only_superadmins(self):
        self._create_user(501, "Main SA", "mainsa")
        self._create_user(502, "Backup SA", "backupsa")
        self._create_user(503, "Regular User", "regular")
        db_repo.promote_to_admin(501)
        db_repo.promote_to_admin(502)

        db_repo.create_absence(501, "vacation", "2026-03-01", "2026-03-02", "", "approved")
        db_repo.create_absence(502, "sick", "2026-03-03", "2026-03-03", "", "approved")
        db_repo.create_absence(503, "dayoff", "2026-03-04", "2026-03-04", "", "approved")

        payload = get_overlaps_payload(501, scope_type="superadmins", year=2026)
        interval_user_ids = {row["user_id"] for row in payload["intervals"]}
        self.assertEqual(interval_user_ids, {501, 502})

    def test_absence_details_acl(self):
        self._create_user(601, "Requester", "req")
        self._create_user(602, "Target", "target")
        self._create_user(603, "Outsider", "out")
        self._create_user(604, "Super", "super")
        db_repo.promote_to_admin(604)

        db_repo.create_group("ACL Team", created_by=1)
        db_repo.create_group("Other Team", created_by=1)
        acl_group = db_repo.list_all_groups()[0][0]
        other_group = db_repo.list_all_groups()[1][0]

        db_repo.add_group_membership(601, acl_group, "member", created_by=1)
        db_repo.add_group_membership(602, acl_group, "member", created_by=1)
        db_repo.add_group_membership(603, other_group, "member", created_by=1)

        absence_id = db_repo.create_absence(602, "vacation", "2026-04-01", "2026-04-02", "comment", "approved")

        payload = get_absence_details_payload(601, absence_id)
        self.assertEqual(payload["absence_id"], absence_id)
        self.assertEqual(payload["user"]["id"], 602)
        self.assertEqual(payload["comment"], "comment")

        with self.assertRaises(WebAppAccessError) as ctx:
            get_absence_details_payload(603, absence_id)
        self.assertEqual(ctx.exception.status_code, 403)

        payload_sa = get_absence_details_payload(604, absence_id)
        self.assertEqual(payload_sa["absence_id"], absence_id)

    def test_default_status_filters_exclude_declined(self):
        self._create_user(701, "Status User", "status")
        db_repo.create_group("Status Team", created_by=1)
        group_id = db_repo.list_all_groups()[0][0]
        db_repo.add_group_membership(701, group_id, "member", created_by=1)

        db_repo.create_absence(701, "vacation", "2026-05-01", "2026-05-01", "", "approved")
        db_repo.create_absence(701, "sick", "2026-05-02", "2026-05-02", "", "pending")
        db_repo.create_absence(701, "dayoff", "2026-05-03", "2026-05-03", "", "declined")

        payload = get_overlaps_payload(701, scope_type="group", group_id=group_id, year=2026)
        statuses = {row["status"] for row in payload["intervals"]}
        self.assertEqual(statuses, {"approved", "pending"})

    def test_invalid_status_filter_returns_400(self):
        self._create_user(801, "Filter User", "filter")
        db_repo.create_group("Filter Team", created_by=1)
        group_id = db_repo.list_all_groups()[0][0]
        db_repo.add_group_membership(801, group_id, "member", created_by=1)

        with self.assertRaises(WebAppAccessError) as ctx:
            get_overlaps_payload(801, scope_type="group", group_id=group_id, year=2026, statuses=["bad_status"])
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
