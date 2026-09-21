# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from psycopg2 import IntegrityError

from odoo.tests import TransactionCase
from odoo.tools import mute_logger


class TestGithubLink(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Regular project"})
        cls.repo_model = cls.env["project.github.repo"]

    def test_project_without_repo_is_not_linked(self):
        self.assertFalse(self.project.github_linked)

    def test_project_with_repo_is_linked(self):
        self.repo_model.create({"name": "org/repo", "project_id": self.project.id})
        self.assertTrue(self.project.github_linked)

    def test_unlink_repo_unlinks_project(self):
        repo = self.repo_model.create(
            {"name": "org/repo", "project_id": self.project.id}
        )
        repo.unlink()
        self.assertFalse(self.project.github_linked)

    @mute_logger("odoo.sql_db")
    def test_repo_linked_to_one_project_only(self):
        self.repo_model.create({"name": "org/repo", "project_id": self.project.id})
        other = self.env["project.project"].create({"name": "Other"})
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.repo_model.create({"name": "org/repo", "project_id": other.id})

    @mute_logger("odoo.sql_db")
    def test_issue_linked_to_one_task_only(self):
        repo = self.repo_model.create(
            {"name": "org/repo", "project_id": self.project.id}
        )
        vals = {
            "project_id": self.project.id,
            "github_repo_id": repo.id,
            "github_issue_number": 7,
        }
        self.env["project.task"].create({"name": "A", **vals})
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["project.task"].create({"name": "B", **vals})
