# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


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
        help="Secret used to validate the signature of GitHub webhook payloads.",
        groups="project.group_project_manager",
    )
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        "UNIQUE(name)",
        "This GitHub repository is already linked to a project.",
    )
