import json
import os
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

import config
import database
import db_repo
from webapp_api import create_app, handle_absence, handle_me, handle_overlaps, handle_webapp_index


class TestWebAppApi(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, path = tempfile.mkstemp(prefix="bot_webapp_api_", suffix=".db")
        os.close(fd)
        self.db_path = path

        config.DB_NAME = path
        database.DB_NAME = path
        db_repo.DB_NAME = path
        database.init_db()

        db_repo.upsert_user_registration(9001, "u9001", "User 9001")
        db_repo.approve_user(9001)
        db_repo.create_group("API Team", created_by=9001)
        self.group_id = db_repo.list_all_groups()[0][0]
        db_repo.add_group_membership(9001, self.group_id, "member", created_by=9001)
        self.absence_id = db_repo.create_absence(
            9001, "vacation", "2026-01-10", "2026-01-12", "vac", "approved"
        )

    async def asyncTearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    async def test_create_app_registers_routes(self):
        app = create_app()
        paths = {route.resource.canonical for route in app.router.routes()}
        self.assertIn("/webapp", paths)
        self.assertIn("/webapp/static", paths)
        self.assertIn("/webapp/v1/me", paths)
        self.assertIn("/webapp/v1/overlaps", paths)
        self.assertIn("/webapp/v1/absence/{absence_id}", paths)

    async def test_index_is_file_response(self):
        request = make_mocked_request("GET", "/webapp")
        response = await handle_webapp_index(request)
        self.assertIsInstance(response, web.FileResponse)

    async def test_me_requires_context(self):
        request = make_mocked_request("GET", "/webapp/v1/me")
        with self.assertRaises(web.HTTPUnauthorized):
            await handle_me(request)

    async def test_me_with_dev_header(self):
        request = make_mocked_request(
            "GET",
            "/webapp/v1/me",
            headers={"X-Telegram-User-Id": "9001"},
        )
        response = await handle_me(request)
        payload = json.loads(response.text)
        self.assertEqual(payload["user"]["id"], 9001)
        self.assertEqual(payload["role"], "user")

    async def test_overlaps_with_group_scope(self):
        request = make_mocked_request(
            "GET",
            f"/webapp/v1/overlaps?scope_type=group&group_id={self.group_id}&year=2026",
            headers={"X-Telegram-User-Id": "9001"},
        )
        response = await handle_overlaps(request)
        payload = json.loads(response.text)
        self.assertEqual(payload["scope"]["type"], "group")
        self.assertEqual(payload["scope"]["group_id"], self.group_id)
        self.assertGreaterEqual(payload["meta"]["total_intervals"], 1)

    async def test_absence_details_by_id(self):
        request = make_mocked_request(
            "GET",
            f"/webapp/v1/absence/{self.absence_id}",
            headers={"X-Telegram-User-Id": "9001"},
            match_info={"absence_id": str(self.absence_id)},
        )
        response = await handle_absence(request)
        payload = json.loads(response.text)
        self.assertEqual(payload["absence_id"], self.absence_id)
        self.assertEqual(payload["user"]["id"], 9001)


if __name__ == "__main__":
    unittest.main()
