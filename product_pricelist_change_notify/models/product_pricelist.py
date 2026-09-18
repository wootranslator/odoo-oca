# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models


class Pricelist(models.Model):
    _inherit = "product.pricelist"

    price_change_notify_user_ids = fields.Many2many(
        "res.users",
        string="Notify price changes to",
        domain=[("share", "=", False)],
        help="At the end of the day, these users receive a summary of the price "
        "changes made on this pricelist. If they have email notifications "
        "enabled, it reaches them by email; otherwise, only as an internal "
        "Odoo notification.",
    )
