# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


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

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        if not self.env.context.get("github_sync_from_github"):
            messages.filtered(
                lambda message: message.model == "project.task" and message.res_id
            )._github_enqueue_comments()
        return messages

    def _github_enqueue_comments(self):
        """Queue the messages that users send from the task chatter.

        Only "Send message" (discussion) messages go to GitHub. Internal notes,
        emails, system messages and what comes from GitHub itself stay in Odoo.
        """
        comment = self.env.ref("mail.mt_comment")
        bot = self.env.ref("base.partner_root")
        Task = self.env["project.task"].sudo()
        Job = self.env["project.github.sync.job"].sudo()
        for message in self:
            if (
                message.message_type != "comment"
                or message.subtype_id != comment
                or message.github_comment_id
                or message.author_id == bot
            ):
                continue
            task = Task.browse(message.res_id)
            if task.github_repo_id.api_token:
                Job._enqueue_comment(message, task)
