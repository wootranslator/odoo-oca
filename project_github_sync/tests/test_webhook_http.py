# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import hashlib
import hmac
import json

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

WEBHOOK_URL = "/project_github_sync/webhook"


@tagged("post_install", "-at_install")
class TestWebhookHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Linked project"})
        cls.repo = cls.env["project.github.repo"].create(
            {"name": "org/repo", "project_id": cls.project.id}
        )

    def _payload(self, repo="org/repo", number=1):
        return {
            "action": "opened",
            "repository": {"full_name": repo},
            "issue": {
                "id": 1000 + number,
                "number": number,
                "title": f"Issue {number}",
                "body": "body",
                "state": "open",
                "html_url": f"https://github.com/{repo}/issues/{number}",
                "updated_at": "2026-09-21T10:00:00Z",
            },
        }

    def _sign(self, body, secret=None):
        secret = secret or self.repo.webhook_secret
        return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def _post(self, payload=None, event="issues", raw=None, signature=None):
        body = raw if raw is not None else json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "X-GitHub-Event": event,
            "X-Hub-Signature-256": self._sign(body) if signature is None else signature,
        }
        return self.url_open(WEBHOOK_URL, data=body, headers=headers)

    def _tasks(self):
        return self.env["project.task"].search([("github_repo_id", "!=", False)])

    def test_valid_delivery_creates_task(self):
        response = self._post(self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        task = self._tasks()
        self.assertEqual(task.name, "Issue 1")
        self.assertEqual(task.project_id, self.project)

    def test_ping(self):
        response = self._post(
            {"zen": "x", "repository": {"full_name": "org/repo"}}, "ping"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "pong")

    @mute_logger("odoo.addons.project_github_sync.controllers.main")
    def test_bad_signature_is_rejected(self):
        for signature in ("sha256=" + "0" * 64, "", self._sign(b"other body")):
            with self.subTest(signature=signature):
                response = self._post(self._payload(), signature=signature or "")
                self.assertEqual(response.status_code, 403)
        self.assertFalse(self._tasks())

    @mute_logger("odoo.addons.project_github_sync.controllers.main")
    def test_signature_with_wrong_secret_is_rejected(self):
        body = json.dumps(self._payload()).encode()
        response = self._post(raw=body, signature=self._sign(body, secret="guess"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self._tasks())

    def test_unlinked_repo_is_ignored(self):
        response = self._post(self._payload(repo="org/other"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")
        self.assertFalse(self._tasks())

    def test_archived_repo_is_ignored(self):
        self.repo.active = False
        response = self._post(self._payload())
        self.assertEqual(response.json()["status"], "ignored")
        self.assertFalse(self._tasks())

    def test_repo_name_is_case_insensitive(self):
        response = self._post(self._payload(repo="ORG/Repo"))
        self.assertEqual(response.json()["status"], "ok")

    def test_invalid_json(self):
        response = self._post(raw=b"{not json", signature="x")
        self.assertEqual(response.status_code, 400)

    def test_json_that_is_not_an_object(self):
        response = self._post(raw=b"[1, 2]", signature="x")
        self.assertEqual(response.status_code, 400)

    def test_payload_without_repository_is_ignored(self):
        response = self._post({"zen": "x"}, "ping", signature="x")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")

    def test_malformed_issue_returns_400(self):
        payload = self._payload()
        payload["issue"] = {}
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self._tasks())
