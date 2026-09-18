# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from markupsafe import Markup

from odoo import api, models
from odoo.tools.translate import _

PRICE_FIELDS = [
    "fixed_price",
    "percent_price",
    "price_discount",
    "price_surcharge",
    "price_round",
    "price_min_margin",
    "price_max_margin",
    "min_quantity",
    "compute_price",
    "base",
]

# Field holding the price according to the rule's compute mode.
REPRESENTATIVE_FIELD_BY_COMPUTE = {
    "fixed": "fixed_price",
    "percentage": "percent_price",
    "formula": "price_discount",
}


class PricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    def _get_price_change_notify_field_label(self, field_name):
        return self._fields[field_name].string

    def _format_price_change_notify_value(self, field_name, value):
        field = self._fields[field_name]
        if field.type == "selection":
            selection = dict(self.fields_get([field_name])[field_name]["selection"])
            return selection.get(value, value)
        return value

    def _get_representative_price_field(self):
        self.ensure_one()
        return REPRESENTATIVE_FIELD_BY_COMPUTE.get(self.compute_price, "fixed_price")

    def _price_change_target(self):
        self.ensure_one()
        return self.product_id or self.product_tmpl_id

    def _build_price_change_log_vals(
        self, change_type, field_name, old_value, new_value
    ):
        """Return (log_vals, field_label, formatted_old_value, formatted_new_value)."""
        self.ensure_one()
        field_label = self._get_price_change_notify_field_label(field_name)
        formatted_old = (
            ""
            if old_value is None
            else str(self._format_price_change_notify_value(field_name, old_value))
        )
        formatted_new = (
            ""
            if new_value is None
            else str(self._format_price_change_notify_value(field_name, new_value))
        )
        vals = {
            "pricelist_id": self.pricelist_id.id,
            "product_id": self.product_id.id,
            "product_tmpl_id": self.product_tmpl_id.id,
            "categ_id": self.categ_id.id,
            "applied_on": self.applied_on,
            "change_type": change_type,
            "field_name": field_name,
            "field_label": field_label,
            "old_value": formatted_old,
            "new_value": formatted_new,
            "user_id": self.env.user.id,
        }
        return vals, field_label, formatted_old, formatted_new

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        log_vals_list = []
        for record in records.filtered("pricelist_id"):
            field_name = record._get_representative_price_field()
            vals, field_label, _fold, formatted_new = (
                record._build_price_change_log_vals(
                    "create",
                    field_name,
                    None,
                    record[field_name],
                )
            )
            log_vals_list.append(vals)

            target = record._price_change_target()
            if target:
                target.message_post(
                    body=Markup(
                        _(
                            "New price rule on pricelist <strong>%(pricelist)s</strong>: %(field)s = %(value)s"
                        )
                    )
                    % {
                        "pricelist": record.pricelist_id.display_name,
                        "field": field_label,
                        "value": formatted_new,
                    }
                )

        if log_vals_list:
            self.env["product.pricelist.change.log"].sudo().create(log_vals_list)

        return records

    def write(self, vals):
        changed_fields = [f for f in PRICE_FIELDS if f in vals]

        if not changed_fields:
            return super().write(vals)

        old_values = {
            record.id: {f: record[f] for f in changed_fields} for record in self
        }

        res = super().write(vals)

        log_vals_list = []
        for record in self:
            old_vals = old_values.get(record.id, {})
            for field_name in changed_fields:
                old_value = old_vals.get(field_name)
                new_value = record[field_name]
                if old_value == new_value:
                    continue

                vals_log, field_label, formatted_old, formatted_new = (
                    record._build_price_change_log_vals(
                        "write",
                        field_name,
                        old_value,
                        new_value,
                    )
                )
                log_vals_list.append(vals_log)

                target = record._price_change_target()
                if target:
                    target.message_post(
                        body=Markup(
                            _(
                                "Price change on pricelist <strong>%(pricelist)s</strong>: "
                                "%(field)s from %(old)s to %(new)s"
                            )
                        )
                        % {
                            "pricelist": record.pricelist_id.display_name,
                            "field": field_label,
                            "old": formatted_old,
                            "new": formatted_new,
                        }
                    )

        if log_vals_list:
            self.env["product.pricelist.change.log"].sudo().create(log_vals_list)

        return res

    def unlink(self):
        # Capture the data BEFORE deleting (records no longer exist afterwards).
        entries = []
        for record in self.filtered("pricelist_id"):
            field_name = record._get_representative_price_field()
            vals, field_label, formatted_old, _fnew = (
                record._build_price_change_log_vals(
                    "unlink",
                    field_name,
                    record[field_name],
                    None,
                )
            )
            target = record._price_change_target()
            chatter = Markup(
                _(
                    "Price rule deleted on pricelist <strong>%(pricelist)s</strong>: %(field)s = %(value)s"
                )
            ) % {
                "pricelist": record.pricelist_id.display_name,
                "field": field_label,
                "value": formatted_old,
            }
            entries.append((vals, target, chatter))

        res = super().unlink()

        if entries:
            self.env["product.pricelist.change.log"].sudo().create(
                [e[0] for e in entries]
            )
            for _vals, target, chatter in entries:
                if target:
                    target.message_post(body=chatter)

        return res
