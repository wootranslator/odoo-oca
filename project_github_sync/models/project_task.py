# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


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
    github_synced_at = fields.Datetime(
        string="Last GitHub sync",
        copy=False,
        readonly=True,
    )

    _github_issue_uniq = models.Constraint(
        "UNIQUE(github_repo_id, github_issue_number)",
        "This GitHub issue is already linked to another task.",
    )
