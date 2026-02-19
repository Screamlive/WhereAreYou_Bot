import os
import tempfile
import unittest

import broadcast
import config
import database
import db_repo


class TestBroadcast(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(prefix="bot_broadcast_db_", suffix=".db")
        os.close(fd)
        self.db_path = path

        config.DB_NAME = path
        database.DB_NAME = path
        db_repo.DB_NAME = path

        database.init_db()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _seed_users(self):
        # Superadmin
        db_repo.upsert_user_registration(1, "sa", "Super Admin")
        db_repo.approve_user(1)
        db_repo.promote_to_admin(1)

        # Approved regular
        db_repo.upsert_user_registration(2, "u2", "User 2")
        db_repo.approve_user(2)

        # Pending registration
        db_repo.upsert_user_registration(3, "u3", "User 3")

        # Group admin candidate
        db_repo.upsert_user_registration(4, "u4", "User 4")
        db_repo.approve_user(4)

        db_repo.create_group("Dept A", created_by=1)
        db_repo.create_group("Dept B", created_by=1)
        groups = db_repo.list_all_groups()
        group_a = groups[0][0]
        group_b = groups[1][0]

        db_repo.add_group_membership(2, group_a, "member", created_by=1)
        db_repo.add_group_membership(4, group_a, "admin", created_by=1)
        db_repo.add_group_membership(4, group_b, "admin", created_by=1)
        db_repo.add_group_membership(3, group_b, "member", created_by=1)

        return group_a, group_b

    def test_parse_group_audience(self):
        self.assertEqual(broadcast._parse_group_audience("group:15"), 15)
        self.assertIsNone(broadcast._parse_group_audience("approved"))
        with self.assertRaises(ValueError):
            broadcast._parse_group_audience("group:")
        with self.assertRaises(ValueError):
            broadcast._parse_group_audience("group:abc")

    def test_resolve_recipient_ids(self):
        group_a, group_b = self._seed_users()

        self.assertEqual(broadcast._resolve_recipient_ids("superadmins"), [1])
        self.assertEqual(broadcast._resolve_recipient_ids("approved"), [1, 2, 4])
        self.assertEqual(broadcast._resolve_recipient_ids("all"), [1, 2, 3, 4])
        self.assertEqual(broadcast._resolve_recipient_ids("group_admins"), [4])
        self.assertEqual(broadcast._resolve_recipient_ids(f"group:{group_a}"), [2, 4])
        self.assertEqual(broadcast._resolve_recipient_ids(f"group:{group_b}"), [3, 4])

        with self.assertRaises(ValueError):
            broadcast._resolve_recipient_ids("group:999")
        with self.assertRaises(ValueError):
            broadcast._resolve_recipient_ids("wrong")

    def test_load_text(self):
        self.assertEqual(broadcast._load_text("  hello  ", None), "hello")

        fd, path = tempfile.mkstemp(prefix="broadcast_msg_", suffix=".txt")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(" test from file \n")
            self.assertEqual(broadcast._load_text(None, path), "test from file")
        finally:
            if os.path.exists(path):
                os.remove(path)

        with self.assertRaises(ValueError):
            broadcast._load_text("   ", None)

    def test_extract_latest_changelog_section(self):
        fd, path = tempfile.mkstemp(prefix="broadcast_changelog_", suffix=".md")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "# CHANGELOG\n\n"
                    "## 2026-02-20 — Релиз 2\n"
                    "- Новая фича\n"
                    "- Багфикс\n\n"
                    "## 2026-02-10 — Релиз 1\n"
                    "- Старое изменение\n"
                )
            section = broadcast._extract_latest_changelog_section(path)
            self.assertIn("## 2026-02-20 — Релиз 2", section)
            self.assertIn("- Новая фича", section)
            self.assertNotIn("2026-02-10", section)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_load_broadcast_text_from_changelog(self):
        fd, path = tempfile.mkstemp(prefix="broadcast_changelog_", suffix=".md")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "# CHANGELOG\n\n"
                    "## 2026-02-20 — Релиз 2\n"
                    "- Новая фича\n\n"
                    "## 2026-02-10 — Релиз 1\n"
                    "- Старое изменение\n"
                )
            text = broadcast._load_broadcast_text(None, None, path)
            self.assertTrue(text.startswith("## 2026-02-20"))
            self.assertNotIn("2026-02-10", text)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_extract_latest_changelog_section_requires_sections(self):
        fd, path = tempfile.mkstemp(prefix="broadcast_changelog_bad_", suffix=".md")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("# CHANGELOG\n\nНет секций второго уровня.\n")
            with self.assertRaises(ValueError):
                broadcast._extract_latest_changelog_section(path)
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
