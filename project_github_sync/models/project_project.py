# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    github_push_new_tasks = fields.Boolean(
        string="Publish new tasks on GitHub",
        help="Every new task created in Odoo in this project is published as "
        "an issue in the default repository. Leave it off to keep Odoo tasks "
        "private and publish them one by one.",
    )
    github_default_repo_id = fields.Many2one(
        comodel_name="project.github.repo",
        string="Default repository",
        compute="_compute_github_default_repo_id",
        store=True,
        readonly=False,
        domain="[('project_id', '=', id)]",
        help="Repository where new tasks are published.",
    )

    @api.depends("github_repo_ids.active")
    def _compute_github_linked(self):
        for project in self:
            project.github_linked = bool(project.github_repo_ids)

    @api.depends("github_repo_ids.active")
    def _compute_github_default_repo_id(self):
        for project in self:
            if project.github_default_repo_id not in project.github_repo_ids:
                project.github_default_repo_id = project.github_repo_ids[:1]

    @api.constrains("github_push_new_tasks", "github_default_repo_id")
    def _check_github_default_repo(self):
        for project in self:
            repo = project.github_default_repo_id
            if repo and repo.project_id != project:
                raise ValidationError(
                    self.env._("The default repository must belong to the project.")
                )
            if project.github_push_new_tasks and not repo:
                raise ValidationError(
                    self.env._(
                        "Add a GitHub repository to the project before "
                        "publishing new tasks on GitHub."
                    )
                )
