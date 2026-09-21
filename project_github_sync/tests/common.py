# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

API_PATH = "odoo.addons.project_github_sync.models.github_api.requests.request"
ISSUES_URL = "https://api.github.com/repos/org/repo/issues"


class FakeResponse:
    """Just enough of requests.Response for the GitHub client."""

    def __init__(self, status=200, data=None, headers=None, text=""):
        self.status_code = status
        self._data = data
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


def issue_response(number=7, status=201, **extra):
    data = {
        "id": 7000 + number,
        "number": number,
        "html_url": f"https://github.com/org/repo/issues/{number}",
        "updated_at": "2026-09-21T12:00:00Z",
    }
    data.update(extra)
    return FakeResponse(status, data)


class OutboundCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Linked project"})
        cls.repo = cls.env["project.github.repo"].create(
            {
                "name": "org/repo",
                "project_id": cls.project.id,
                "api_token": "ghp_secret_token",
            }
        )
        cls.Job = cls.env["project.github.sync.job"]
        cls.Task = cls.env["project.task"]
        cls.alice = new_test_user(
            cls.env, login="alice_gh", name="Alice", groups="project.group_project_user"
        )

    def mute(self, *loggers):
        """Silence expected errors/warnings (the OCA CI fails on unexpected ones)."""
        muted = mute_logger(*loggers)
        muted.__enter__()
        self.addCleanup(muted.__exit__, None, None, None)

    def mute_sync_errors(self):
        self.mute(
            "odoo.addons.project_github_sync.models.github_api",
            "odoo.addons.project_github_sync.models.project_github_sync_job",
        )

    def mock_api(self, *responses):
        patcher = patch(API_PATH, side_effect=list(responses))
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def run_jobs(self):
        # The cron commits after each job, which tests are not allowed to do.
        with patch.object(
            type(self.env["ir.cron"]), "_commit_progress", return_value=float("inf")
        ):
            self.Job._cron_process_jobs()

    def jobs(self, task=None, kind=None, state=None):
        domain = []
        if task:
            domain.append(("task_id", "=", task.id))
        if kind:
            domain.append(("kind", "=", kind))
        if state:
            domain.append(("state", "=", state))
        return self.Job.search(domain)

    def make_task(self, **vals):
        vals.setdefault("name", "Task from Odoo")
        vals.setdefault("project_id", self.project.id)
        return self.Task.create(vals)

    def publish(self, task, number=7):
        """Publish a task on GitHub through the queue; return the API mock."""
        mock = self.mock_api(issue_response(number, status=201))
        task.github_repo_id = self.repo
        self.run_jobs()
        return mock

    def make_due(self, job):
        job.next_attempt_at = fields.Datetime.now() - timedelta(seconds=1)
