import unittest

from aiohttp.test_utils import make_mocked_request

from app.webapp.service import WebAppAccessError
from app.webapp.validation import parse_absence_id, parse_overlaps_query


class TestWebAppValidation(unittest.TestCase):
    def test_parse_overlaps_query_ok(self):
        request = make_mocked_request(
            "GET",
            "/webapp/v1/overlaps?scope_type=group&group_id=12&year=2026&statuses=approved,pending&categories=vacation",
        )
        parsed = parse_overlaps_query(request)
        self.assertEqual(parsed["scope_type"], "group")
        self.assertEqual(parsed["group_id"], 12)
        self.assertEqual(parsed["year"], 2026)
        self.assertEqual(parsed["statuses"], ["approved", "pending"])
        self.assertEqual(parsed["categories"], ["vacation"])

    def test_parse_overlaps_query_invalid_group_id(self):
        request = make_mocked_request("GET", "/webapp/v1/overlaps?group_id=abc")
        with self.assertRaises(WebAppAccessError) as ctx:
            parse_overlaps_query(request)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("group_id", ctx.exception.message)

    def test_parse_absence_id(self):
        self.assertEqual(parse_absence_id("123"), 123)
        with self.assertRaises(WebAppAccessError) as ctx:
            parse_absence_id("not-number")
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()

