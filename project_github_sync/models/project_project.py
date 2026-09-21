# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    github_repo_ids = fields.One2many(
        comodel_name="project.github.repo",
        inverse_name="project_id",
        string="GitHub repositories",
    )
    github_linked = fields.Boolean(
        string="Linked to GitHub",
        compute="_compute_github_linked",
        store=True,
        help="Only linked projects are synchronized with GitHub. Projects "
        "without any repository behave as regular projects.",
    )

    @api.depends("github_repo_ids.active")
    def _compute_github_linked(self):
        for project in self:
            project.github_linked = bool(project.github_repo_ids)
