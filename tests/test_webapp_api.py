import json
import os
import tempfile
import unittest
import zipfile
import hashlib
import hmac
from io import BytesIO
from unittest.mock import patch
from urllib.parse import quote

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

import config
import database
import db_repo
import webapp_api
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
        self.prev_initdata_compat = os.environ.get("WEBAPP_ALLOW_INITDATA_COMPAT")
        self.prev_rate_limit_max = os.environ.get("WEBAPP_RATE_LIMIT_MAX_REQUESTS")
        self.prev_rate_limit_window = os.environ.get("WEBAPP_RATE_LIMIT_WINDOW_SEC")
        os.environ["WEBAPP_ALLOW_DEV_FALLBACK"] = "1"
        os.environ["WEBAPP_ALLOW_INITDATA_COMPAT"] = "1"
        webapp_api._clear_rate_limiter_state()

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
        if self.prev_initdata_compat is None:
            os.environ.pop("WEBAPP_ALLOW_INITDATA_COMPAT", None)
        else:
            os.environ["WEBAPP_ALLOW_INITDATA_COMPAT"] = self.prev_initdata_compat
        if self.prev_rate_limit_max is None:
            os.environ.pop("WEBAPP_RATE_LIMIT_MAX_REQUESTS", None)
        else:
            os.environ["WEBAPP_RATE_LIMIT_MAX_REQUESTS"] = self.prev_rate_limit_max
        if self.prev_rate_limit_window is None:
            os.environ.pop("WEBAPP_RATE_LIMIT_WINDOW_SEC", None)
        else:
            os.environ["WEBAPP_RATE_LIMIT_WINDOW_SEC"] = self.prev_rate_limit_window
        webapp_api._clear_rate_limiter_state()

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

    async def test_me_rejects_compat_channels_when_disabled(self):
        os.environ["WEBAPP_ALLOW_DEV_FALLBACK"] = "0"
        os.environ["WEBAPP_ALLOW_INITDATA_COMPAT"] = "0"
        init_data = self._build_valid_init_data()
        request = make_mocked_request(
            "GET",
            f"/webapp/v1/me?tgWebAppData={quote(init_data, safe='')}",
        )
        with patch.object(webapp_api.logger, "warning") as mocked_warning:
            with self.assertRaises(web.HTTPUnauthorized):
                await handle_me(request)

        self.assertTrue(mocked_warning.called)
        args = mocked_warning.call_args[0]
        joined = " ".join(str(part) for part in args)
        self.assertNotIn("tgWebAppData", joined)
        self.assertNotIn("hash=", joined)

    async def test_index_is_file_response(self):
        request = make_mocked_request("GET", "/webapp")
        response = await handle_webapp_index(request)
        self.assertIsInstance(response, web.FileResponse)

    async def test_me_requires_context(self):
        request = make_mocked_request("GET", "/webapp/v1/me")
        with self.assertRaises(web.HTTPUnauthorized):
            await handle_me(request)

    async def test_me_requires_context_logs_without_sensitive_referer(self):
        request = make_mocked_request(
            "GET",
            "/webapp/v1/me",
            headers={
                "Referer": "https://bot-test.justasite.cc/webapp?debug_token=secret_payload",
                "User-Agent": "TestAgent/1.0",
            },
        )
        with patch.object(webapp_api.logger, "warning") as mocked_warning:
            with self.assertRaises(web.HTTPUnauthorized):
                await handle_me(request)

        self.assertTrue(mocked_warning.called)
        args = mocked_warning.call_args[0]
        joined = " ".join(str(part) for part in args)
        self.assertNotIn("secret_payload", joined)
        self.assertNotIn("debug_token=", joined)
        self.assertIn("referer_has_tg", str(args[0]))

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

    async def test_security_headers_present_for_webapp_routes(self):
        request = make_mocked_request("GET", "/webapp")

        async def ok_handler(_request):
            return web.Response(text="ok")

        index_resp = await webapp_api.security_headers_middleware(request, ok_handler)
        self.assertEqual(index_resp.status, 200)
        self.assertIn("Content-Security-Policy", index_resp.headers)
        self.assertEqual(index_resp.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(index_resp.headers.get("X-Content-Type-Options"), "nosniff")

        request_unauth = make_mocked_request("GET", "/webapp/v1/me")

        async def unauthorized_handler(_request):
            raise web.HTTPUnauthorized(text='{"error":"x"}', content_type="application/json")

        api_resp = await webapp_api.security_headers_middleware(request_unauth, unauthorized_handler)
        self.assertEqual(api_resp.status, 401)
        self.assertIn("Content-Security-Policy", api_resp.headers)
        self.assertEqual(api_resp.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

    async def test_rate_limit_middleware_blocks_burst_requests(self):
        os.environ["WEBAPP_RATE_LIMIT_MAX_REQUESTS"] = "2"
        os.environ["WEBAPP_RATE_LIMIT_WINDOW_SEC"] = "60"
        webapp_api._clear_rate_limiter_state()

        async def ok_handler(_request):
            return web.Response(text="ok")

        req_1 = make_mocked_request("GET", "/webapp/v1/me", headers={"X-Real-IP": "1.2.3.4"})
        req_2 = make_mocked_request("GET", "/webapp/v1/me", headers={"X-Real-IP": "1.2.3.4"})
        req_3 = make_mocked_request("GET", "/webapp/v1/me", headers={"X-Real-IP": "1.2.3.4"})

        resp_1 = await webapp_api.rate_limit_middleware(req_1, ok_handler)
        resp_2 = await webapp_api.rate_limit_middleware(req_2, ok_handler)
        self.assertEqual(resp_1.status, 200)
        self.assertEqual(resp_2.status, 200)

        with self.assertRaises(web.HTTPTooManyRequests) as cm:
            await webapp_api.rate_limit_middleware(req_3, ok_handler)
        retry_after = int(cm.exception.headers.get("Retry-After", "0"))
        self.assertGreaterEqual(retry_after, 1)

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
