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

    async def test_overlaps_with_filters_and_query(self):
        request = make_mocked_request(
            "GET",
            (
                f"/webapp/v1/overlaps?scope_type=group&group_id={self.group_id}"
                "&year=2026&statuses=approved,pending&categories=vacation&q=User"
            ),
            headers={"X-Telegram-User-Id": "9001"},
        )
        response = await handle_overlaps(request)
        payload = json.loads(response.text)
        self.assertEqual(payload["filters"]["statuses"], ["approved", "pending"])
        self.assertEqual(payload["filters"]["categories"], ["vacation"])
        self.assertEqual(payload["filters"]["query"], "User")

    async def test_overlaps_with_custom_period(self):
        request = make_mocked_request(
            "GET",
            (
                f"/webapp/v1/overlaps?scope_type=group&group_id={self.group_id}"
                "&start_date=2026-01-01&end_date=2026-01-31"
            ),
            headers={"X-Telegram-User-Id": "9001"},
        )
        response = await handle_overlaps(request)
        payload = json.loads(response.text)
        self.assertEqual(payload["period"]["start_date"], "2026-01-01")
        self.assertEqual(payload["period"]["end_date"], "2026-01-31")
        self.assertTrue(payload["period"]["is_custom"])

    async def test_overlaps_rejects_broken_period(self):
        request = make_mocked_request(
            "GET",
            (
                f"/webapp/v1/overlaps?scope_type=group&group_id={self.group_id}"
                "&start_date=2026-02-10&end_date=2026-01-01"
            ),
            headers={"X-Telegram-User-Id": "9001"},
        )
        with self.assertRaises(web.HTTPBadRequest):
            await handle_overlaps(request)

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

    async def test_absence_details_validates_numeric_id(self):
        request = make_mocked_request(
            "GET",
            "/webapp/v1/absence/not-number",
            headers={"X-Telegram-User-Id": "9001"},
            match_info={"absence_id": "not-number"},
        )
        with self.assertRaises(web.HTTPBadRequest):
            await handle_absence(request)


if __name__ == "__main__":
    unittest.main()
