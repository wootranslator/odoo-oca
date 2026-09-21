# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
from datetime import datetime

from markupsafe import Markup
from psycopg2 import IntegrityError

from odoo import fields, models
from odoo.tools import plaintext2html

from odoo.addons.project.models.project_task import CLOSED_STATES

_logger = logging.getLogger(__name__)

GITHUB_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_github_datetime(value):
    """GitHub timestamps are UTC ISO 8601 (``2026-09-21T09:23:29Z``)."""
    if not value:
        return False
    try:
        return datetime.strptime(value, GITHUB_DATETIME_FORMAT)
    except (TypeError, ValueError):
        return False


class ProjectTask(models.Model):
    _inherit = "project.task"

    github_repo_id = fields.Many2one(
        comodel_name="project.github.repo",
        string="GitHub repository",
        copy=False,
        index="btree_not_null",
    )
    github_issue_id = fields.Char(
        string="GitHub issue ID",
        copy=False,
        readonly=True,
    )
    github_issue_number = fields.Integer(
        string="GitHub issue number",
        copy=False,
        readonly=True,
    )
    github_url = fields.Char(
        string="GitHub URL",
        copy=False,
    )
    github_updated_at = fields.Datetime(
        string="Issue updated on GitHub",
        copy=False,
        readonly=True,
        help="Last update time reported by GitHub. Older events are discarded.",
    )
    github_synced_at = fields.Datetime(
        string="Last GitHub sync",
        copy=False,
        readonly=True,
    )

    _github_issue_uniq = models.Constraint(
        "UNIQUE(github_repo_id, github_issue_number)",
        "This GitHub issue is already linked to another task.",
    )

    def _github_find(self, repo, number):
        return self.search(
            [("github_repo_id", "=", repo.id), ("github_issue_number", "=", number)],
            limit=1,
        )

    def _github_prepare_vals(self, repo, issue, task):
        """Values to write on the task for the given GitHub issue payload."""
        body = issue.get("body")
        vals = {
            "name": issue["title"],
            "description": plaintext2html(body) if body else False,
            "github_repo_id": repo.id,
            "github_issue_id": str(issue["id"]),
            "github_issue_number": issue["number"],
            "github_url": issue.get("html_url") or False,
            "github_updated_at": _parse_github_datetime(issue.get("updated_at")),
            "github_synced_at": fields.Datetime.now(),
        }
        if issue.get("state") == "closed":
            vals["state"] = (
                "1_canceled" if issue.get("state_reason") == "not_planned" else "1_done"
            )
        elif task and task.state in CLOSED_STATES:
            # Only reopen: do not override other open states set in Odoo.
            vals["state"] = "01_in_progress"
        return vals

    def _github_upsert_from_issue(self, repo, issue):
        """Create or update the task linked to a GitHub issue (idempotent)."""
        task = self._github_find(repo, issue["number"])
        updated_at = _parse_github_datetime(issue.get("updated_at"))
        if (
            task
            and updated_at
            and task.github_updated_at
            and updated_at < task.github_updated_at
        ):
            _logger.info("Discarding stale event for %s#%s", repo.name, issue["number"])
            return task
        vals = self._github_prepare_vals(repo, issue, task)
        if task:
            task.write(vals)
            return task
        project = repo.project_id
        create_vals = dict(vals, project_id=project.id)
        tasks = self.with_company(project.company_id) if project.company_id else self
        try:
            with self.env.cr.savepoint():
                return tasks.create(create_vals)
        except IntegrityError:
            # Another delivery for the same issue was processed concurrently.
            task = self._github_find(repo, issue["number"])
            if not task:
                raise
            task.write(vals)
            return task

    def _github_note(self, text):
        self.ensure_one()
        self.message_post(
            body=text,
            author_id=self.env.ref("base.partner_root").id,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

    def _github_comment_body(self, comment):
        login = (comment.get("user") or {}).get("login") or "?"
        url = comment.get("html_url") or ""
        if url.startswith("https://"):
            header = Markup('<p><strong>%s</strong> (<a href="%s">GitHub</a>):</p>')
            header %= (login, url)
        else:
            header = Markup("<p><strong>%s</strong> (GitHub):</p>") % login
        return header + plaintext2html(comment.get("body") or "")

    def _github_sync_comment(self, action, comment):
        """Mirror a GitHub issue comment in the chatter, once per comment."""
        self.ensure_one()
        comment_id = str(comment["id"])
        message = self.env["mail.message"].search(
            [
                ("model", "=", "project.task"),
                ("res_id", "=", self.id),
                ("github_comment_id", "=", comment_id),
            ],
            limit=1,
        )
        if action == "deleted":
            message.unlink()
            return
        body = self._github_comment_body(comment)
        if message:
            message.write({"body": body})
            return
        try:
            with self.env.cr.savepoint():
                message = self.message_post(
                    body=body,
                    author_id=self.env.ref("base.partner_root").id,
                    message_type="comment",
                    subtype_xmlid="mail.mt_note",
                )
                # message_post() refuses unknown values, hence the extra write.
                # The unique index makes a concurrent duplicate delivery fail.
                message.github_comment_id = comment_id
        except IntegrityError:
            _logger.info("GitHub comment %s was already mirrored", comment_id)
