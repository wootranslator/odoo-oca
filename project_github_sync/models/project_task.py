# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging
from datetime import datetime

from markupsafe import Markup
from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import html2plaintext, plaintext2html

from odoo.addons.project.models.project_task import CLOSED_STATES

from .github_utils import (
    MAX_BODY_LENGTH,
    MAX_TITLE_LENGTH,
    content_hash,
    normalize_body,
    split_marker,
    truncate,
)

_logger = logging.getLogger(__name__)

GITHUB_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# Changing one of these on a linked task pushes it to GitHub
PUSH_FIELDS = {"name", "description", "state", "stage_id"}
# Context flag set while applying changes that come from (or are already in)
# GitHub, so they are not pushed back.
NO_PUSH = "github_sync_from_github"


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
        help="Repository where this task is published as an issue. Setting it "
        "on a task without issue publishes the task on GitHub.",
    )
    github_linked = fields.Boolean(related="project_id.github_linked")
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
    github_sync_hash = fields.Char(
        copy=False,
        readonly=True,
        help="Fingerprint of the title, description and state known to be in "
        "sync with GitHub. Used to ignore echoes of our own changes.",
    )
    github_job_ids = fields.One2many(
        comodel_name="project.github.sync.job",
        inverse_name="task_id",
        string="GitHub synchronization",
        readonly=True,
    )

    _github_issue_uniq = models.Constraint(
        "UNIQUE(github_repo_id, github_issue_number)",
        "This GitHub issue is already linked to another task.",
    )

    @api.constrains("github_repo_id", "project_id")
    def _check_github_repo_project(self):
        for task in self:
            if (
                task.github_repo_id
                and task.github_repo_id.project_id != task.project_id
            ):
                raise ValidationError(
                    self.env._(
                        "The task '%(task)s' is linked to a GitHub repository of "
                        "another project. Unlink it before moving it.",
                        task=task.display_name,
                    )
                )

    # -- Odoo → GitHub: triggers ------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        if not self.env.context.get(NO_PUSH):
            tasks._github_after_create()
        return tasks

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get(NO_PUSH) and (
            PUSH_FIELDS & set(vals) or "github_repo_id" in vals
        ):
            self.filtered("github_repo_id")._github_enqueue()
        return result

    def _github_after_create(self):
        for task in self:
            project = task.project_id
            if (
                not task.github_repo_id
                and project.github_push_new_tasks
                and project.github_default_repo_id
            ):
                task.with_context(
                    **{NO_PUSH: True}
                ).github_repo_id = project.github_default_repo_id
        self.filtered(
            lambda task: task.github_repo_id and not task.github_issue_number
        )._github_enqueue()

    def _github_enqueue(self):
        """Queue the push of these tasks (only when the repository has a token)."""
        tasks = self.filtered(
            lambda task: not task.is_template and task.github_repo_id.sudo().api_token
        )
        if tasks:
            self.env["project.github.sync.job"].sudo()._enqueue_tasks(tasks)

    # -- Odoo → GitHub: content -------------------------------------------------

    def _github_state_key(self):
        self.ensure_one()
        if self.state == "1_done":
            return "completed"
        if self.state == "1_canceled":
            return "not_planned"
        return "open"

    def _github_outbound_values(self):
        """Title, body and state key to publish on GitHub."""
        self.ensure_one()
        title = truncate((self.name or "").strip(), MAX_TITLE_LENGTH)
        text = html2plaintext(self.description or "", include_references=False)
        body = truncate(normalize_body(text), MAX_BODY_LENGTH)
        return title, body, self._github_state_key()

    def _github_outbound_digest(self):
        self.ensure_one()
        return content_hash(*self._github_outbound_values())

    def _github_store_issue(self, data, digest):
        """Remember the GitHub issue answered by the API."""
        self.ensure_one()
        self.with_context(**{NO_PUSH: True}).write(
            {
                "github_issue_id": str(data["id"]),
                "github_issue_number": data["number"],
                "github_url": data.get("html_url") or False,
                "github_updated_at": _parse_github_datetime(data.get("updated_at")),
                "github_synced_at": fields.Datetime.now(),
                "github_sync_hash": digest,
            }
        )

    # -- GitHub → Odoo ----------------------------------------------------------

    def _github_find(self, repo, number):
        return self.search(
            [("github_repo_id", "=", repo.id), ("github_issue_number", "=", number)],
            limit=1,
        )

    def _github_adopt(self, repo, task_id):
        """Task created in Odoo whose issue we have not stored yet (marker)."""
        task = self.browse(task_id).exists()
        if task.github_repo_id == repo and not task.github_issue_number:
            return task
        return self.browse()

    @staticmethod
    def _github_issue_state_key(issue):
        if issue.get("state") != "closed":
            return "open"
        return (
            "not_planned" if issue.get("state_reason") == "not_planned" else "completed"
        )

    def _github_prepare_vals(self, repo, issue, task, body, digest, echo):
        """Values to write on the task for the given GitHub issue payload."""
        vals = {
            "github_repo_id": repo.id,
            "github_issue_id": str(issue["id"]),
            "github_issue_number": issue["number"],
            "github_url": issue.get("html_url") or False,
            "github_updated_at": _parse_github_datetime(issue.get("updated_at")),
            "github_synced_at": fields.Datetime.now(),
            "github_sync_hash": digest,
        }
        if echo:
            # Same content Odoo already has (e.g. the echo of our own push):
            # do not rewrite the task, it could lose its rich formatting.
            return vals
        vals["name"] = issue["title"]
        vals["description"] = plaintext2html(body) if body.strip() else False
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
        body, marker_kind, marker_id = split_marker(issue.get("body"))
        task = self._github_find(repo, issue["number"])
        adopted = False
        if not task and marker_kind == "task":
            task = self._github_adopt(repo, marker_id)
            adopted = bool(task)
        updated_at = _parse_github_datetime(issue.get("updated_at"))
        if (
            task
            and updated_at
            and task.github_updated_at
            and updated_at < task.github_updated_at
        ):
            _logger.info("Discarding stale event for %s#%s", repo.name, issue["number"])
            return task
        digest = content_hash(issue["title"], body, self._github_issue_state_key(issue))
        known = task._github_outbound_digest() if adopted else task.github_sync_hash
        vals = self._github_prepare_vals(
            repo, issue, task, body, digest, echo=bool(task) and known == digest
        )
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

    def _github_link_own_comment(self, comment_id, message_id):
        """The comment was published by Odoo: remember its GitHub id."""
        message = self.env["mail.message"].browse(message_id).exists()
        if (
            message
            and message.model == "project.task"
            and message.res_id == self.id
            and not message.github_comment_id
        ):
            try:
                with self.env.cr.savepoint():
                    message.github_comment_id = comment_id
            except IntegrityError:
                _logger.info("GitHub comment %s is already linked", comment_id)

    def _github_sync_comment(self, action, comment):
        """Mirror a GitHub issue comment in the chatter, once per comment."""
        self.ensure_one()
        comment_id = str(comment["id"])
        _clean, marker_kind, marker_id = split_marker(comment.get("body"))
        if marker_kind == "message":
            # Written by Odoo: it is already in the chatter.
            self._github_link_own_comment(comment_id, marker_id)
            return
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
