# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import hashlib
import hmac
import logging
import re
import secrets

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _like_literal(text):
    """Escape ``text`` so it matches literally in an ``=ilike`` domain."""
    return text.replace("\\", "\\\\").replace("_", r"\_").replace("%", r"\%")


# ``issues`` actions that carry the full issue and are safe to apply
# idempotently. Anything else (transferred, pinned, locked...) is ignored.
ISSUE_ACTIONS = {
    "opened",
    "edited",
    "closed",
    "reopened",
    "assigned",
    "unassigned",
    "labeled",
    "unlabeled",
    "milestoned",
    "demilestoned",
}
COMMENT_ACTIONS = {"created", "edited", "deleted"}


class ProjectGithubRepo(models.Model):
    _name = "project.github.repo"
    _description = "GitHub repository linked to a project"
    _order = "name"

    name = fields.Char(
        string="Repository",
        required=True,
        help="Full repository name, e.g. 'my-org/my-repo'.",
    )
    project_id = fields.Many2one(
        comodel_name="project.project",
        required=True,
        ondelete="cascade",
        index=True,
    )
    webhook_secret = fields.Char(
        required=True,
        default=lambda self: secrets.token_hex(32),
        copy=False,
        help="Secret used to validate the signature of GitHub webhook payloads. "
        "Paste the same value in the webhook settings on GitHub.",
        groups="project.group_project_manager",
    )
    webhook_url = fields.Char(
        compute="_compute_webhook_url",
        help="Payload URL to configure in the GitHub webhook settings.",
    )
    api_token = fields.Char(
        copy=False,
        help="Token used to write on GitHub (create and update issues, post "
        "comments). Use a fine-grained personal access token limited to this "
        "repository with read and write access to Issues. Without a token, "
        "Odoo only receives changes from GitHub.",
        groups="project.group_project_manager",
    )
    company_id = fields.Many2one(
        related="project_id.company_id",
        store=True,
        index=True,
    )
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        "UNIQUE(name)",
        "This GitHub repository is already linked to a project.",
    )

    @api.constrains("name")
    def _check_name(self):
        for repo in self:
            if not REPO_NAME_RE.match(repo.name or ""):
                raise ValidationError(
                    self.env._(
                        "Invalid repository name '%(name)s'. Use the "
                        "'owner/repo' format.",
                        name=repo.name,
                    )
                )
            duplicates = self.with_context(active_test=False).search_count(
                [("id", "!=", repo.id), ("name", "=ilike", _like_literal(repo.name))]
            )
            if duplicates:
                raise ValidationError(
                    self.env._(
                        "The GitHub repository '%(name)s' is already linked to a "
                        "project (repository names are case-insensitive).",
                        name=repo.name,
                    )
                )

    def _compute_webhook_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for repo in self:
            repo.webhook_url = f"{base_url}/project_github_sync/webhook"

    @api.model
    def _find_by_full_name(self, full_name):
        """Return the active linked repository, GitHub names being case-insensitive."""
        if not isinstance(full_name, str) or not full_name:
            return self.browse()
        return self.search([("name", "=ilike", _like_literal(full_name))], limit=1)

    def _verify_signature(self, body, signature):
        """Check the ``X-Hub-Signature-256`` header against the raw request body."""
        self.ensure_one()
        secret = self.webhook_secret
        if not secret or not signature:
            return False
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, f"sha256={digest}")

    def _process_webhook(self, event, payload):
        """Apply a (already authenticated) GitHub webhook event.

        Returns a small dict describing what happened. Raises ValidationError
        when the payload is malformed.
        """
        self.ensure_one()
        if event == "ping":
            return {"status": "pong"}
        if event not in ("issues", "issue_comment"):
            return {"status": "ignored", "reason": f"unsupported event {event}"}
        issue = payload.get("issue")
        if not isinstance(issue, dict) or not all(
            key in issue for key in ("id", "number", "title")
        ):
            raise ValidationError(self.env._("Malformed issue payload."))
        if issue.get("pull_request"):
            return {"status": "ignored", "reason": "pull request"}
        action = payload.get("action")
        # Flag consumed by the (future) Odoo → GitHub side to avoid echoing
        # back the changes that just came from GitHub.
        tasks = self.env["project.task"].with_context(github_sync_from_github=True)
        if event == "issues":
            return self._process_issue_event(tasks, action, issue)
        return self._process_comment_event(tasks, action, issue, payload.get("comment"))

    def _process_issue_event(self, tasks, action, issue):
        if action == "deleted":
            task = tasks._github_find(self, issue["number"])
            if task:
                task._github_note(self.env._("The GitHub issue was deleted."))
                return {"status": "ok", "task_id": task.id}
            return {"status": "ignored", "reason": "unknown issue"}
        if action not in ISSUE_ACTIONS:
            return {"status": "ignored", "reason": f"unsupported action {action}"}
        task = tasks._github_upsert_from_issue(self, issue)
        return {"status": "ok", "task_id": task.id}

    def _process_comment_event(self, tasks, action, issue, comment):
        if action not in COMMENT_ACTIONS:
            return {"status": "ignored", "reason": f"unsupported action {action}"}
        if not isinstance(comment, dict) or "id" not in comment:
            raise ValidationError(self.env._("Malformed comment payload."))
        if action == "deleted":
            # Do not import an issue just to remove a comment we never saw.
            task = tasks._github_find(self, issue["number"])
            if not task:
                return {"status": "ignored", "reason": "unknown issue"}
        else:
            task = tasks._github_upsert_from_issue(self, issue)
        task._github_sync_comment(action, comment)
        return {"status": "ok", "task_id": task.id}
