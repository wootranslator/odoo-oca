# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import hashlib
import hmac
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger


class TestWebhookEvents(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Linked project"})
        cls.repo = cls.env["project.github.repo"].create(
            {"name": "org/repo", "project_id": cls.project.id}
        )
        cls.task_model = cls.env["project.task"]

    def _issue(self, number=1, **kwargs):
        issue = {
            "id": 1000 + number,
            "number": number,
            "title": f"Issue {number}",
            "body": "Some *body*",
            "state": "open",
            "html_url": f"https://github.com/org/repo/issues/{number}",
            "updated_at": "2026-09-21T10:00:00Z",
        }
        issue.update(kwargs)
        return issue

    def _issue_event(self, action="opened", **issue_kwargs):
        return self.repo._process_webhook(
            "issues", {"action": action, "issue": self._issue(**issue_kwargs)}
        )

    def _comment_event(self, action="created", comment_id=50, body="Hi", number=1):
        return self.repo._process_webhook(
            "issue_comment",
            {
                "action": action,
                "issue": self._issue(number=number),
                "comment": {
                    "id": comment_id,
                    "body": body,
                    "user": {"login": "octocat"},
                    "html_url": "https://github.com/org/repo/issues/1#c",
                },
            },
        )

    def _task(self, number=1):
        return self.task_model.search(
            [
                ("github_repo_id", "=", self.repo.id),
                ("github_issue_number", "=", number),
            ]
        )

    def _comment_messages(self, task):
        return self.env["mail.message"].search(
            [
                ("model", "=", "project.task"),
                ("res_id", "=", task.id),
                ("github_comment_id", "!=", False),
            ]
        )

    # -- issues ---------------------------------------------------------------

    def test_ping(self):
        result = self.repo._process_webhook("ping", {})
        self.assertEqual(result["status"], "pong")

    def test_opened_creates_task(self):
        result = self._issue_event("opened")
        task = self._task()
        self.assertEqual(result, {"status": "ok", "task_id": task.id})
        self.assertEqual(task.name, "Issue 1")
        self.assertEqual(task.project_id, self.project)
        self.assertEqual(task.github_issue_id, "1001")
        self.assertEqual(task.github_url, "https://github.com/org/repo/issues/1")
        self.assertEqual(task.state, "01_in_progress")
        self.assertIn("Some *body*", task.description)
        self.assertTrue(task.github_synced_at)

    def test_repeated_delivery_is_idempotent(self):
        self._issue_event("opened")
        self._issue_event("opened")
        self.assertEqual(len(self._task()), 1)

    def test_edited_updates_task(self):
        self._issue_event("opened")
        self._issue_event(
            "edited", title="New title", updated_at="2026-09-21T11:00:00Z"
        )
        self.assertEqual(self._task().name, "New title")
        self.assertEqual(len(self._task()), 1)

    def test_empty_body_clears_description(self):
        self._issue_event("opened")
        self._issue_event("edited", body=None, updated_at="2026-09-21T11:00:00Z")
        self.assertFalse(self._task().description)

    def test_body_is_escaped(self):
        self._issue_event("opened", body="<script>alert(1)</script>")
        self.assertNotIn("<script>", self._task().description)

    def test_closed_completed_and_not_planned(self):
        self._issue_event("opened")
        self._issue_event(
            "closed",
            state="closed",
            state_reason="completed",
            updated_at="2026-09-21T11:00:00Z",
        )
        self.assertEqual(self._task().state, "1_done")
        self._issue_event(
            "closed",
            state="closed",
            state_reason="not_planned",
            updated_at="2026-09-21T12:00:00Z",
        )
        self.assertEqual(self._task().state, "1_canceled")

    def test_reopened(self):
        self._issue_event("opened", state="closed", state_reason="completed")
        self.assertEqual(self._task().state, "1_done")
        self._issue_event("reopened", updated_at="2026-09-21T11:00:00Z")
        self.assertEqual(self._task().state, "01_in_progress")

    def test_open_event_keeps_other_open_states(self):
        self._issue_event("opened")
        task = self._task()
        task.state = "02_changes_requested"
        self._issue_event("edited", updated_at="2026-09-21T11:00:00Z")
        self.assertEqual(task.state, "02_changes_requested")

    def test_stale_event_is_discarded(self):
        self._issue_event("edited", title="Newest", updated_at="2026-09-21T12:00:00Z")
        self._issue_event("opened", title="Older", updated_at="2026-09-21T10:00:00Z")
        self.assertEqual(self._task().name, "Newest")

    @mute_logger("odoo.sql_db")
    def test_concurrent_creation_falls_back_to_update(self):
        existing = self.task_model.create(
            {
                "name": "Created by a concurrent delivery",
                "project_id": self.project.id,
                "github_repo_id": self.repo.id,
                "github_issue_number": 5,
            }
        )
        real_find = type(self.task_model)._github_find
        calls = []

        def find_missing_first(this, repo, number):
            calls.append(number)
            if len(calls) == 1:
                return this.browse()
            return real_find(this, repo, number)

        with patch.object(type(self.task_model), "_github_find", find_missing_first):
            result = self._issue_event("opened", number=5, title="Final")
        self.assertEqual(result["task_id"], existing.id)
        self.assertEqual(existing.name, "Final")
        self.assertEqual(len(self._task(5)), 1)

    def test_pull_request_is_ignored(self):
        result = self._issue_event(
            "opened", pull_request={"url": "https://api.github.com/x"}
        )
        self.assertEqual(result["status"], "ignored")
        self.assertFalse(self._task())

    def test_unsupported_event_and_actions_are_ignored(self):
        self.assertEqual(self.repo._process_webhook("push", {})["status"], "ignored")
        self.assertEqual(self._issue_event("transferred")["status"], "ignored")
        self.assertFalse(self._task())

    def test_malformed_issue_payload(self):
        with self.assertRaises(ValidationError):
            self.repo._process_webhook("issues", {"action": "opened", "issue": {}})
        with self.assertRaises(ValidationError):
            self.repo._process_webhook("issues", {"action": "opened"})

    def test_deleted_issue_keeps_task_and_notes_it(self):
        self._issue_event("opened")
        task = self._task()
        result = self._issue_event("deleted")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(task.exists())
        self.assertIn("deleted", task.message_ids[0].body)

    def test_deleted_unknown_issue_is_ignored(self):
        self.assertEqual(self._issue_event("deleted")["status"], "ignored")

    def test_sync_context_flag(self):
        contexts = []
        real = type(self.task_model)._github_upsert_from_issue

        def spy(this, repo, issue):
            contexts.append(dict(this.env.context))
            return real(this, repo, issue)

        with patch.object(type(self.task_model), "_github_upsert_from_issue", spy):
            self._issue_event("opened")
        self.assertTrue(contexts[0].get("github_sync_from_github"))

    # -- comments -------------------------------------------------------------

    def test_comment_created_is_mirrored_once(self):
        self._comment_event("created")
        self._comment_event("created")
        task = self._task()
        messages = self._comment_messages(task)
        self.assertEqual(len(messages), 1)
        self.assertIn("octocat", messages.body)
        self.assertIn("Hi", messages.body)
        self.assertEqual(messages.author_id, self.env.ref("base.partner_root"))

    @mute_logger("odoo.sql_db")
    def test_duplicate_comment_id_does_not_break_the_webhook(self):
        """Simulates a concurrent delivery that already stored the comment."""
        self._comment_event("created", comment_id=50, number=1)
        other = self._issue_event("opened", number=2)
        result = self._comment_event("created", comment_id=50, number=2)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(
            self._comment_messages(self.task_model.browse(other["task_id"]))
        )

    def test_comment_on_unseen_issue_imports_it(self):
        self._comment_event("created", number=9)
        self.assertTrue(self._task(9))

    def test_comment_edited_updates_message(self):
        self._comment_event("created", body="First")
        self._comment_event("edited", body="Second")
        messages = self._comment_messages(self._task())
        self.assertEqual(len(messages), 1)
        self.assertIn("Second", messages.body)
        self.assertNotIn("First", messages.body)

    def test_comment_deleted_removes_message(self):
        self._comment_event("created")
        self._comment_event("deleted")
        self.assertFalse(self._comment_messages(self._task()))

    def test_comment_deleted_on_unknown_issue_does_not_import_it(self):
        result = self._comment_event("deleted", number=42)
        self.assertEqual(result["status"], "ignored")
        self.assertFalse(self._task(42))

    def test_comment_is_escaped(self):
        self.repo._process_webhook(
            "issue_comment",
            {
                "action": "created",
                "issue": self._issue(),
                "comment": {
                    "id": 77,
                    "body": "<script>alert(1)</script>",
                    "user": {"login": "<b>evil</b>"},
                    "html_url": "javascript:alert(1)",
                },
            },
        )
        body = self._comment_messages(self._task()).body
        self.assertNotIn("<script>", body)
        self.assertNotIn("<b>evil", body)
        self.assertNotIn("javascript:", body)

    def test_malformed_comment_payload(self):
        with self.assertRaises(ValidationError):
            self.repo._process_webhook(
                "issue_comment",
                {"action": "created", "issue": self._issue(), "comment": {}},
            )

    # -- linking --------------------------------------------------------------

    def test_find_by_full_name(self):
        finder = self.env["project.github.repo"]._find_by_full_name
        self.assertEqual(finder("ORG/Repo"), self.repo)
        self.assertFalse(finder("org/other"))
        self.assertFalse(finder(None))
        self.assertFalse(finder(""))
        self.assertFalse(finder(["org/repo"]))

    def test_archived_repo_is_not_found(self):
        self.repo.active = False
        self.assertFalse(self.env["project.github.repo"]._find_by_full_name("org/repo"))
        self.assertFalse(self.project.github_linked)

    def test_signature(self):
        secret = self.repo.webhook_secret
        body = b'{"a": 1}'
        good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(self.repo._verify_signature(body, good))
        self.assertFalse(self.repo._verify_signature(b'{"a": 2}', good))
        self.assertFalse(self.repo._verify_signature(body, ""))
        self.assertFalse(self.repo._verify_signature(body, "sha256=abc"))
        self.assertFalse(self.repo._verify_signature(body, good.replace("sha256=", "")))
