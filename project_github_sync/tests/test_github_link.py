# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
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

    def test_secret_is_generated(self):
        repo = self.repo_model.create(
            {"name": "org/repo", "project_id": self.project.id}
        )
        self.assertGreaterEqual(len(repo.webhook_secret), 32)
        other = self.repo_model.create(
            {"name": "org/other", "project_id": self.project.id}
        )
        self.assertNotEqual(repo.webhook_secret, other.webhook_secret)

    def test_webhook_url(self):
        repo = self.repo_model.create(
            {"name": "org/repo", "project_id": self.project.id}
        )
        self.assertTrue(repo.webhook_url.endswith("/project_github_sync/webhook"))

    def test_invalid_repo_names(self):
        for name in ("repo", "org/", "/repo", "org/re po", "org/repo/extra", ""):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.repo_model.create({"name": name, "project_id": self.project.id})

    def test_repo_name_is_case_insensitive_unique(self):
        self.repo_model.create({"name": "Org/Repo", "project_id": self.project.id})
        with self.assertRaises(ValidationError):
            self.repo_model.create({"name": "org/repo", "project_id": self.project.id})

    def test_underscore_is_not_a_wildcard(self):
        self.repo_model.create({"name": "org/my_repo", "project_id": self.project.id})
        # would collide if "_" were treated as a LIKE wildcard
        self.repo_model.create({"name": "org/myXrepo", "project_id": self.project.id})

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
