# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class MailMessage(models.Model):
    _inherit = "mail.message"

    github_comment_id = fields.Char(
        string="GitHub comment ID",
        copy=False,
        readonly=True,
    )

    _github_comment_uniq = models.UniqueIndex(
        "(github_comment_id) WHERE github_comment_id IS NOT NULL",
        "This GitHub comment is already mirrored in the chatter.",
    )
