# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo.tests import BaseCase
from odoo.tools import mute_logger

from ..models.github_api import GithubApiError, github_request
from ..models.github_utils import (
    add_marker,
    content_hash,
    normalize_body,
    split_marker,
    truncate,
)
from .common import API_PATH, FakeResponse


class TestUtils(BaseCase):
    def test_marker_round_trip(self):
        body = add_marker("Hello", "task", 42)
        self.assertEqual(split_marker(body), ("Hello", "task", 42))
        self.assertEqual(split_marker(add_marker("", "message", 3)), ("", "message", 3))

    def test_no_marker(self):
        self.assertEqual(split_marker("plain"), ("plain", None, None))
        self.assertEqual(split_marker(None), ("", None, None))

    def test_marker_survives_crlf_editing(self):
        body = add_marker("Hello\nWorld", "task", 1).replace("\n", "\r\n")
        clean, kind, record_id = split_marker(body)
        self.assertEqual((kind, record_id), ("task", 1))
        self.assertEqual(normalize_body(clean), "Hello\nWorld")

    def test_hash_ignores_line_endings_and_edge_whitespace(self):
        self.assertEqual(
            content_hash(" T ", "a\r\nb\r\n", "open"), content_hash("T", "a\nb", "open")
        )
        self.assertNotEqual(
            content_hash("T", "a", "open"), content_hash("T", "a", "completed")
        )

    def test_truncate(self):
        self.assertEqual(truncate("abc", 5), "abc")
        self.assertEqual(len(truncate("a" * 50, 10)), 10)
        self.assertTrue(truncate("a" * 50, 10).endswith("…"))


class TestGithubClient(BaseCase):
    def setUp(self):
        super().setUp()
        muted = mute_logger("odoo.addons.project_github_sync.models.github_api")
        muted.__enter__()
        self.addCleanup(muted.__exit__, None, None, None)

    def _call(self, response):
        with patch(API_PATH, return_value=response):
            return github_request("tok", "GET", "/x")

    def test_success(self):
        self.assertEqual(self._call(FakeResponse(200, {"a": 1})), {"a": 1})

    def test_success_without_json(self):
        self.assertEqual(self._call(FakeResponse(204)), {})

    def test_rate_limit_reset_header(self):
        headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"}
        with self.assertRaises(GithubApiError) as ctx:
            self._call(FakeResponse(403, {"message": "limit"}, headers))
        self.assertTrue(ctx.exception.retryable)
        self.assertGreater(ctx.exception.retry_after, 0)

    def test_permission_error_is_not_retryable(self):
        with self.assertRaises(GithubApiError) as ctx:
            self._call(FakeResponse(403, {"message": "Resource not accessible"}))
        self.assertFalse(ctx.exception.retryable)

    def test_429_is_retryable(self):
        with self.assertRaises(GithubApiError) as ctx:
            self._call(FakeResponse(429, {"message": "limit"}, {"Retry-After": "30"}))
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(ctx.exception.retry_after, 30)

    def test_garbage_error_body(self):
        with self.assertRaises(GithubApiError) as ctx:
            self._call(FakeResponse(500, None, text="<html>oops</html>"))
        self.assertIn("500", str(ctx.exception))
        self.assertTrue(ctx.exception.retryable)
