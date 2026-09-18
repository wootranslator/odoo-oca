# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import logging

from markupsafe import Markup

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

CHANGE_TYPES = [
    ("create", "Created"),
    ("write", "Changed"),
    ("unlink", "Deleted"),
]


class PricelistChangeLog(models.Model):
    _name = "product.pricelist.change.log"
    _description = "Pricelist price change history"
    _order = "change_date desc"

    pricelist_id = fields.Many2one(
        "product.pricelist", required=True, ondelete="cascade", index=True
    )
    product_id = fields.Many2one("product.product", ondelete="cascade")
    product_tmpl_id = fields.Many2one(
        "product.template", ondelete="cascade", string="Product Template"
    )
    categ_id = fields.Many2one(
        "product.category", ondelete="cascade", string="Product Category"
    )
    applied_on = fields.Char(string="Applied on")

    change_type = fields.Selection(
        CHANGE_TYPES, string="Type", required=True, default="write", index=True
    )
    field_name = fields.Char(required=True)
    field_label = fields.Char(required=True)
    old_value = fields.Char()
    new_value = fields.Char()

    user_id = fields.Many2one("res.users", required=True)
    change_date = fields.Datetime(
        string="Change date", required=True, default=fields.Datetime.now
    )

    notified = fields.Boolean(default=False, index=True)
    notified_date = fields.Datetime()

    def _get_target_display(self):
        self.ensure_one()
        return (
            self.product_id.display_name
            or self.product_tmpl_id.display_name
            or self.categ_id.display_name
            or self.env._("All products")
        )

    def _build_digest_rows(self):
        """Return the <tr> rows of the digest table, safely HTML-escaped.

        Kept in Python (rather than inline in the mail.template) so every
        interpolated value goes through Markup's automatic escaping.
        """
        # Use fields_get() rather than the CHANGE_TYPES constant so the
        # selection labels come translated in the recipient's language.
        change_type_labels = dict(
            self.fields_get(["change_type"])["change_type"]["selection"]
        )

        row_template = Markup(
            "<tr>"
            "<td style='padding:4px 8px;border-bottom:1px solid #eee;'>{}</td>"
            "<td style='padding:4px 8px;border-bottom:1px solid #eee;'>{}</td>"
            "<td style='padding:4px 8px;border-bottom:1px solid #eee;'>{}</td>"
            "<td style='padding:4px 8px;border-bottom:1px solid #eee;'>{}</td>"
            "<td style='padding:4px 8px;border-bottom:1px solid #eee;'>{}</td>"
            "</tr>"
        )
        return Markup("").join(
            row_template.format(
                change_type_labels.get(log.change_type, log.change_type),
                log._get_target_display(),
                log.field_label,
                log.old_value,
                log.new_value,
            )
            for log in self
        )

    @api.model
    def _cron_send_price_change_digest(self):
        pending_logs = self.search([("notified", "=", False)])
        if not pending_logs:
            return

        template = self.env.ref(
            "product_pricelist_change_notify.mail_template_price_change_digest"
        )

        for pricelist, logs in pending_logs.grouped("pricelist_id").items():
            # Isolate each pricelist in a savepoint: if sending to one fails,
            # it doesn't block or roll back the rest.
            try:
                with self.env.cr.savepoint():
                    recipient_users = pricelist.price_change_notify_user_ids
                    if recipient_users:
                        subject = template._render_field("subject", pricelist.ids)[
                            pricelist.id
                        ]
                        body = template._render_field("body_html", pricelist.ids)[
                            pricelist.id
                        ]
                        # Sender from the company's real domain (with authenticated
                        # SMTP), not the odoobot@*.odoo.com address that goes to spam.
                        company = pricelist.company_id or self.env.company
                        email_from = company.email_formatted or company.email or None
                        self.env["mail.thread"].message_notify(
                            partner_ids=recipient_users.partner_id.ids,
                            subject=subject,
                            body=body,
                            email_from=email_from,
                        )

                    logs.write(
                        {
                            "notified": True,
                            "notified_date": fields.Datetime.now(),
                        }
                    )
            except Exception:
                _logger.exception(
                    "Failed sending the price change digest for pricelist %s (id %s)",
                    pricelist.display_name,
                    pricelist.id,
                )
