# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.tools import html2plaintext

from .github_api import GithubApiError, github_request
from .github_utils import add_marker, content_hash

_logger = logging.getLogger(__name__)

# Seconds to wait before retrying after the 1st, 2nd... failed attempt.
RETRY_DELAYS = (60, 300, 900, 3600, 14400)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
KEEP_DONE_DAYS = 30

STATE_PAYLOADS = {
    "open": {"state": "open"},
    "completed": {"state": "closed", "state_reason": "completed"},
    "not_planned": {"state": "closed", "state_reason": "not_planned"},
}


class ProjectGithubSyncJob(models.Model):
    """Pending / done / failed pushes from Odoo to GitHub (the sync log)."""

    _name = "project.github.sync.job"
    _description = "GitHub synchronization job"
    _order = "id desc"

    kind = fields.Selection(
        selection=[("task", "Task"), ("comment", "Comment")],
        required=True,
    )
    task_id = fields.Many2one(
        comodel_name="project.task",
        required=True,
        ondelete="cascade",
        index=True,
    )
    message_id = fields.Many2one(
        comodel_name="mail.message",
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="task_id.company_id",
        store=True,
        index=True,
    )
    state = fields.Selection(
        selection=[("pending", "Pending"), ("done", "Done"), ("failed", "Failed")],
        default="pending",
        required=True,
        index=True,
    )
    attempt_count = fields.Integer(readonly=True)
    next_attempt_at = fields.Datetime(
        default=fields.Datetime.now,
        index=True,
        help="The job is not processed before this date.",
    )
    last_error = fields.Text(readonly=True)
    done_at = fields.Datetime(readonly=True)

    # A task has at most one pending push (later changes are coalesced: the
    # job always pushes the current state of the task) and a comment is
    # published only once.
    _pending_task_uniq = models.UniqueIndex(
        "(task_id) WHERE kind = 'task' AND state = 'pending'",
        "This task already has a pending GitHub synchronization.",
    )
    _comment_uniq = models.UniqueIndex(
        "(message_id) WHERE kind = 'comment'",
        "This message is already queued for GitHub.",
    )

    # -- queue ----------------------------------------------------------------

    @api.model
    def _enqueue_tasks(self, tasks):
        pending = self.search(
            [
                ("kind", "=", "task"),
                ("state", "=", "pending"),
                ("task_id", "in", tasks.ids),
            ]
        ).task_id
        for task in tasks - pending:
            try:
                with self.env.cr.savepoint():
                    self.create({"kind": "task", "task_id": task.id})
            except IntegrityError:
                # Lost a race with a concurrent transaction: it is queued.
                _logger.debug("Task %s already has a pending job", task.id)

    @api.model
    def _enqueue_comment(self, message, task):
        if self.search_count(
            [("kind", "=", "comment"), ("message_id", "=", message.id)]
        ):
            return
        try:
            with self.env.cr.savepoint():
                self.create(
                    {"kind": "comment", "task_id": task.id, "message_id": message.id}
                )
        except IntegrityError:
            _logger.debug("Message %s is already queued", message.id)

    @api.model
    def _cron_process_jobs(self, batch_size=50):
        due = self.search(
            [
                ("state", "=", "pending"),
                ("next_attempt_at", "<=", fields.Datetime.now()),
            ],
            order="id",
            limit=batch_size,
        )
        if not due:
            return
        # Skip jobs another worker is already processing
        self.env.cr.execute(
            "SELECT id FROM project_github_sync_job WHERE id IN %s "
            "FOR UPDATE SKIP LOCKED",
            (tuple(due.ids),),
        )
        jobs = self.browse([row[0] for row in self.env.cr.fetchall()])
        remaining = len(jobs)
        for job in jobs:
            job._run()
            remaining -= 1
            if not self.env["ir.cron"]._commit_progress(1, remaining=remaining):
                break

    @api.autovacuum
    def _gc_done_jobs(self):
        limit = fields.Datetime.now() - timedelta(days=KEEP_DONE_DAYS)
        self.search([("state", "=", "done"), ("done_at", "<", limit)]).unlink()

    def action_retry(self):
        self.filtered(lambda job: job.state == "failed").write(
            {
                "state": "pending",
                "attempt_count": 0,
                "next_attempt_at": fields.Datetime.now(),
            }
        )

    # -- processing -----------------------------------------------------------

    def _run(self):
        self.ensure_one()
        error = None
        try:
            with self.env.cr.savepoint():
                error = self._dispatch()
        except GithubApiError as exc:
            error = exc
        except Exception as exc:  # pylint: disable=broad-except
            # One broken job must not block the whole queue.
            _logger.exception("Unexpected error in GitHub sync job %s", self.id)
            error = GithubApiError(f"Unexpected error: {exc}", retryable=False)
        if error:
            self._register_failure(error)
        else:
            self.write(
                {
                    "state": "done",
                    "done_at": fields.Datetime.now(),
                    "last_error": False,
                }
            )

    def _dispatch(self):
        if self.kind == "comment":
            return self._push_comment()
        return self._push_task()

    def _register_failure(self, error):
        self.ensure_one()
        attempts = self.attempt_count + 1
        vals = {"attempt_count": attempts, "last_error": str(error)}
        if not error.retryable or attempts >= MAX_ATTEMPTS:
            vals.update(state="failed", done_at=fields.Datetime.now())
            self.write(vals)
            self.task_id._github_note(
                self.env._("GitHub synchronization failed: %(error)s", error=error)
            )
            return
        delay = max(RETRY_DELAYS[attempts - 1], error.retry_after or 0)
        vals["next_attempt_at"] = fields.Datetime.now() + timedelta(seconds=delay)
        self.write(vals)

    def _github_token(self, repo):
        token = repo.sudo().api_token
        if not repo or not token:
            raise GithubApiError(
                self.env._("No GitHub API token configured for this repository."),
                retryable=False,
            )
        return token

    def _push_task(self):
        """Create or update the GitHub issue of the task.

        Returns a GithubApiError when part of the work is done (and saved) but
        the rest must be retried, None when everything is in sync.
        """
        task = self.task_id
        repo = task.github_repo_id
        token = self._github_token(repo)
        title, body, state_key = task._github_outbound_values()
        digest = content_hash(title, body, state_key)
        payload = {"title": title, "body": add_marker(body, "task", task.id)}
        if task.github_issue_number:
            if digest == task.github_sync_hash:
                return None
            path = f"/repos/{repo.name}/issues/{task.github_issue_number}"
            data = github_request(
                token, "PATCH", path, dict(payload, **STATE_PAYLOADS[state_key])
            )
            task._github_store_issue(data, digest)
            return None
        data = github_request(token, "POST", f"/repos/{repo.name}/issues", payload)
        # Persist the link now: if closing the new issue fails below, the
        # retry updates it instead of creating a duplicate.
        task._github_store_issue(data, content_hash(title, body, "open"))
        if state_key == "open":
            return None
        try:
            data = github_request(
                token,
                "PATCH",
                f"/repos/{repo.name}/issues/{data['number']}",
                STATE_PAYLOADS[state_key],
            )
        except GithubApiError as exc:
            return exc
        task._github_store_issue(data, digest)
        return None

    def _push_comment(self):
        message = self.message_id
        task = self.task_id
        repo = task.github_repo_id
        token = self._github_token(repo)
        if message.github_comment_id:
            return None
        if not task.github_issue_number:
            # The issue is still being created by the task job.
            raise GithubApiError(
                self.env._("The GitHub issue does not exist yet."), retryable=True
            )
        author = message.author_id.name or self.env._("Someone")
        text = html2plaintext(message.body or "", include_references=False).strip()
        body = add_marker(f"**{author}** (Odoo):\n\n{text}", "message", message.id)
        data = github_request(
            token,
            "POST",
            f"/repos/{repo.name}/issues/{task.github_issue_number}/comments",
            {"body": body},
        )
        message.sudo().with_context(
            github_sync_from_github=True
        ).github_comment_id = str(data["id"])
        return None
