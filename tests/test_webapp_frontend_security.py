import unittest
from pathlib import Path


APP_JS_PATH = Path(__file__).resolve().parent.parent / "webapp_static" / "app.js"


class TestWebAppFrontendSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_js = APP_JS_PATH.read_text(encoding="utf-8")

    def test_no_persistent_initdata_storage(self):
        self.assertNotIn('localStorage.setItem("tg_init_data"', self.app_js)
        self.assertNotIn("document.cookie = `tg_init_data=", self.app_js)

    def test_no_initdata_in_api_query_string(self):
        self.assertNotIn('url.searchParams.set("init_data"', self.app_js)

    def test_initdata_is_sent_via_headers(self):
        self.assertIn('headers["X-Telegram-Init-Data"] = state.initData;', self.app_js)
        self.assertIn("headers.Authorization = `tma ${state.initData}`;", self.app_js)

