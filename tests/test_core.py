import os
import tempfile
import unittest

try:
    import aiogram  # noqa: F401
    HAS_AIOGRAM = True
except ModuleNotFoundError:
    HAS_AIOGRAM = False

if HAS_AIOGRAM:
    import config
    import database
    import db_repo
    import core
    import keyboards


    class TestCore(unittest.TestCase):
        def setUp(self):
            fd, path = tempfile.mkstemp(prefix="bot_core_db_", suffix=".db")
            os.close(fd)
            self.db_path = path

            config.DB_NAME = path
            database.DB_NAME = path
            db_repo.DB_NAME = path

            database.init_db()

        def tearDown(self):
            if os.path.exists(self.db_path):
                os.remove(self.db_path)

        def test_role_menu_superadmin(self):
            tg_id = 1
            db_repo.upsert_user_registration(tg_id, "admin", "Admin")
            db_repo.promote_to_admin(tg_id)

            menu = core.get_role_menu(tg_id)
            self.assertIs(menu, keyboards.superadmin_main_menu)

        def test_role_menu_no_group(self):
            tg_id = 2
            db_repo.upsert_user_registration(tg_id, "user", "User")
            db_repo.approve_user(tg_id)

            menu = core.get_role_menu(tg_id)
            self.assertIs(menu, keyboards.no_group_menu)

        def test_role_menu_group_admin_single(self):
            tg_id = 3
            db_repo.upsert_user_registration(tg_id, "ga", "Group Admin")
            db_repo.approve_user(tg_id)
            db_repo.create_group("Team A", created_by=1)
            group_id, _ = db_repo.list_all_groups()[0]
            db_repo.add_group_membership(tg_id, group_id, "admin", created_by=1)

            menu = core.get_role_menu(tg_id)
            self.assertIs(menu, keyboards.group_admin_main_menu)
            self.assertEqual(db_repo.get_last_group_id(tg_id), group_id)

        def test_role_menu_group_admin_multi_requires_select(self):
            tg_id = 4
            db_repo.upsert_user_registration(tg_id, "ga2", "Group Admin 2")
            db_repo.approve_user(tg_id)
            db_repo.create_group("Team B", created_by=1)
            db_repo.create_group("Team C", created_by=1)
            groups = db_repo.list_all_groups()
            for gid, _name in groups:
                db_repo.add_group_membership(tg_id, gid, "admin", created_by=1)

            # no last_group_id -> must select
            menu = core.get_role_menu(tg_id)
            self.assertIs(menu, keyboards.group_admin_select_menu)

            # set last group -> full menu
            db_repo.set_last_group_id(tg_id, groups[0][0])
            menu = core.get_role_menu(tg_id)
            self.assertIs(menu, keyboards.group_admin_main_menu)

        def test_role_menu_regular_user(self):
            tg_id = 5
            db_repo.upsert_user_registration(tg_id, "user2", "User Two")
            db_repo.approve_user(tg_id)
            db_repo.create_group("Team D", created_by=1)
            group_id, _ = db_repo.list_all_groups()[0]
            db_repo.add_group_membership(tg_id, group_id, "member", created_by=1)

            menu = core.get_role_menu(tg_id)
            self.assertIs(menu, keyboards.user_main_menu)

        def test_role_menu_group_viewer_single(self):
            tg_id = 8
            db_repo.upsert_user_registration(tg_id, "viewer", "Viewer")
            db_repo.approve_user(tg_id)
            db_repo.create_group("Team V", created_by=1)
            group_id, _ = db_repo.list_all_groups()[0]
            db_repo.add_group_membership(tg_id, group_id, "viewer", created_by=1)

            menu = core.get_role_menu(tg_id)
            self.assertIs(menu, keyboards.group_viewer_main_menu)
            self.assertEqual(db_repo.get_last_group_id(tg_id), group_id)

        def test_get_admin_scope(self):
            tg_id = 6
            db_repo.upsert_user_registration(tg_id, "ga3", "Group Admin 3")
            db_repo.approve_user(tg_id)
            db_repo.create_group("Team E", created_by=1)
            group_id, _ = db_repo.list_all_groups()[0]
            db_repo.add_group_membership(tg_id, group_id, "admin", created_by=1)

            allowed, gid, need_select = core.get_admin_scope(tg_id)
            self.assertTrue(allowed)
            self.assertEqual(gid, group_id)
            self.assertFalse(need_select)

            # Non-admin member should not pass
            tg_id2 = 7
            db_repo.upsert_user_registration(tg_id2, "member", "Member")
            db_repo.approve_user(tg_id2)
            db_repo.add_group_membership(tg_id2, group_id, "member", created_by=1)
            allowed, gid, need_select = core.get_admin_scope(tg_id2)
            self.assertFalse(allowed)
            self.assertIsNone(gid)
            self.assertFalse(need_select)

        def test_get_group_scope_viewer(self):
            tg_id = 9
            db_repo.upsert_user_registration(tg_id, "viewer2", "Viewer 2")
            db_repo.approve_user(tg_id)
            db_repo.create_group("Team Scope", created_by=1)
            group_id, _ = db_repo.list_all_groups()[0]
            db_repo.add_group_membership(tg_id, group_id, "viewer", created_by=1)

            can_read, can_write, gid, need_select = core.get_group_scope(tg_id)
            self.assertTrue(can_read)
            self.assertFalse(can_write)
            self.assertEqual(gid, group_id)
            self.assertFalse(need_select)

else:

    class TestCore(unittest.TestCase):
        @unittest.skip("aiogram is not installed")
        def test_skip(self):
            pass


if __name__ == "__main__":
    unittest.main()
