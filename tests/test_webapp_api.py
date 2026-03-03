import json
import os
import tempfile
import unittest
import zipfile
import hashlib
import hmac
from io import BytesIO
from urllib.parse import quote

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

import config
import database
import db_repo
from webapp_api import (
    _verify_telegram_init_data,
    create_app,
    handle_absence,
    handle_export_xlsx,
    handle_me,
    handle_overlaps,
    handle_webapp_index,
)


class TestWebAppApi(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.prev_dev_fallback = os.environ.get("WEBAPP_ALLOW_DEV_FALLBACK")
        os.environ["WEBAPP_ALLOW_DEV_FALLBACK"] = "1"

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
        if self.prev_dev_fallback is None:
            os.environ.pop("WEBAPP_ALLOW_DEV_FALLBACK", None)
        else:
            os.environ["WEBAPP_ALLOW_DEV_FALLBACK"] = self.prev_dev_fallback

        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    async def test_create_app_registers_routes(self):
        app = create_app()
        paths = {route.resource.canonical for route in app.router.routes()}
        self.assertIn("/webapp", paths)
        self.assertIn("/webapp/static", paths)
        self.assertIn("/webapp/v1/me", paths)
        self.assertIn("/webapp/v1/overlaps", paths)
        self.assertIn("/webapp/v1/export/xlsx", paths)
        self.assertIn("/webapp/v1/absence/{absence_id}", paths)

    def _build_valid_init_data(self, user_id: int = 9001, auth_date: int = 4102444800) -> str:
        # Fixed future auth_date keeps the sample valid in tests.
        user_json = json.dumps({"id": user_id, "first_name": "Test", "username": "u9001"}, separators=(",", ":"))
        pairs = {
            "auth_date": str(auth_date),
            "query_id": "AAEAAAE",
            "user": user_json,
        }
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", config.TOKEN.encode(), hashlib.sha256).digest()
        digest = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
        parts = [f"{key}={quote(value, safe='')}" for key, value in pairs.items()]
        parts.append(f"hash={digest}")
        return "&".join(parts)

    async def test_verify_init_data_accepts_encoded_variants(self):
        raw_init_data = self._build_valid_init_data()
        encoded_once_more = quote(raw_init_data, safe="")
        prefixed_tma = f"tma {raw_init_data}"

        self.assertEqual(_verify_telegram_init_data(raw_init_data), 9001)
        self.assertEqual(_verify_telegram_init_data(encoded_once_more), 9001)
        self.assertEqual(_verify_telegram_init_data(prefixed_tma), 9001)

    async def test_me_accepts_initdata_from_referer(self):
        os.environ["WEBAPP_ALLOW_DEV_FALLBACK"] = "0"
        init_data = self._build_valid_init_data()
        referer = f"https://bot-test.justasite.cc/webapp?tgWebAppData={quote(init_data, safe='')}"
        request = make_mocked_request(
            "GET",
            "/webapp/v1/me",
            headers={"Referer": referer},
        )
        response = await handle_me(request)
        payload = json.loads(response.text)
        self.assertEqual(payload["user"]["id"], 9001)

    async def test_me_accepts_initdata_from_authorization_tma(self):
        os.environ["WEBAPP_ALLOW_DEV_FALLBACK"] = "0"
        init_data = self._build_valid_init_data()
        request = make_mocked_request(
            "GET",
            "/webapp/v1/me",
            headers={"Authorization": f"tma {init_data}"},
        )
        response = await handle_me(request)
        payload = json.loads(response.text)
        self.assertEqual(payload["user"]["id"], 9001)

    async def test_me_accepts_initdata_from_cookie(self):
        os.environ["WEBAPP_ALLOW_DEV_FALLBACK"] = "0"
        init_data = self._build_valid_init_data()
        cookie_header = f"tg_init_data={quote(init_data, safe='')}"
        request = make_mocked_request(
            "GET",
            "/webapp/v1/me",
            headers={"Cookie": cookie_header},
        )
        response = await handle_me(request)
        payload = json.loads(response.text)
        self.assertEqual(payload["user"]["id"], 9001)

    async def test_me_accepts_initdata_from_query_tgwebappdata(self):
        os.environ["WEBAPP_ALLOW_DEV_FALLBACK"] = "0"
        init_data = self._build_valid_init_data()
        request = make_mocked_request(
            "GET",
            f"/webapp/v1/me?tgWebAppData={quote(init_data, safe='')}",
        )
        response = await handle_me(request)
        payload = json.loads(response.text)
        self.assertEqual(payload["user"]["id"], 9001)

    async def test_index_is_file_response(self):
        request = make_mocked_request("GET", "/webapp")
        response = await handle_webapp_index(request)
        self.assertIsInstance(response, web.FileResponse)

    async def test_me_requires_context(self):
        request = make_mocked_request("GET", "/webapp/v1/me")
        with self.assertRaises(web.HTTPUnauthorized):
            await handle_me(request)

    async def test_me_without_initdata_when_dev_fallback_disabled(self):
        os.environ["WEBAPP_ALLOW_DEV_FALLBACK"] = "0"
        request = make_mocked_request(
            "GET",
            "/webapp/v1/me",
            headers={"X-Telegram-User-Id": "9001"},
        )
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
        self.assertIn("daily_load", payload)

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

    async def test_export_xlsx_returns_workbook(self):
        request = make_mocked_request(
            "GET",
            f"/webapp/v1/export/xlsx?scope_type=group&group_id={self.group_id}&year=2026",
            headers={"X-Telegram-User-Id": "9001"},
        )
        response = await handle_export_xlsx(request)
        self.assertEqual(
            response.content_type,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment;", response.headers.get("Content-Disposition", ""))

        archive = zipfile.ZipFile(BytesIO(response.body))
        self.assertIn("xl/workbook.xml", archive.namelist())
        self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())

    async def test_export_xlsx_respects_acl(self):
        request = make_mocked_request(
            "GET",
            "/webapp/v1/export/xlsx?scope_type=group&group_id=999&year=2026",
            headers={"X-Telegram-User-Id": "9001"},
        )
        with self.assertRaises(web.HTTPForbidden):
            await handle_export_xlsx(request)


if __name__ == "__main__":
    unittest.main()
