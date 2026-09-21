# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Project GitHub Sync",
    "summary": "Optionally link Odoo projects with GitHub repositories and "
    "synchronize tasks with issues",
    "version": "19.0.1.0.0",
    "category": "Project",
    "website": "https://github.com/wootranslator/odoo-oca",
    "author": "Javier Sánchez de Pedro, Odoo Community Association (OCA)",
    "maintainers": ["wootranslator"],
    "license": "AGPL-3",
    "depends": ["mail", "project"],
    "data": [
        "security/ir.model.access.csv",
        "views/project_github_repo_views.xml",
        "views/project_project_views.xml",
        "views/project_task_views.xml",
    ],
    "development_status": "Alpha",
}
