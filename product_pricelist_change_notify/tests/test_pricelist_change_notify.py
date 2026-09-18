# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestPricelistChangeNotify(TransactionCase):
    def setUp(self):
        super().setUp()
        self.pricelist = self.env["product.pricelist"].create(
            {"name": "Test Pricelist"}
        )
        self.product = self.env["product.product"].create(
            {"name": "Test Product", "list_price": 10.0}
        )

    def test_create_logs_change(self):
        item = self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "0_product_variant",
                "product_id": self.product.id,
                "compute_price": "fixed",
                "fixed_price": 20.0,
            }
        )
        log = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        )
        self.assertEqual(len(log), 1)
        self.assertEqual(log.change_type, "create")
        self.assertFalse(log.notified)

        item.write({"fixed_price": 25.0})
        logs = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        )
        self.assertEqual(len(logs), 2)

        item.unlink()
        logs = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        )
        self.assertEqual(len(logs), 3)

    def test_cron_digest_marks_notified(self):
        self.pricelist.price_change_notify_user_ids = [(6, 0, [self.env.user.id])]
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "3_global",
                "compute_price": "fixed",
                "fixed_price": 15.0,
            }
        )
        self.env["product.pricelist.change.log"]._cron_send_price_change_digest()
        logs = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        )
        self.assertTrue(all(logs.mapped("notified")))

    def test_cron_digest_without_recipients_still_marks_notified(self):
        # No price_change_notify_user_ids set on the pricelist: the cron
        # must not fail and must still flag the logs as notified.
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "3_global",
                "compute_price": "fixed",
                "fixed_price": 15.0,
            }
        )
        self.env["product.pricelist.change.log"]._cron_send_price_change_digest()
        logs = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        )
        self.assertTrue(logs)
        self.assertTrue(all(logs.mapped("notified")))

    def test_category_level_rule_logs_category(self):
        category = self.env["product.category"].create({"name": "Test Category"})
        item = self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "2_product_category",
                "categ_id": category.id,
                "compute_price": "fixed",
                "fixed_price": 30.0,
            }
        )
        log = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        )
        self.assertEqual(log.categ_id, category)
        self.assertFalse(log.product_id)
        self.assertEqual(log._get_target_display(), category.display_name)
        item.unlink()

    def test_global_rule_logs_all_products(self):
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "3_global",
                "compute_price": "fixed",
                "fixed_price": 5.0,
            }
        )
        log = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        )
        self.assertFalse(log.product_id)
        self.assertFalse(log.categ_id)
        self.assertEqual(log._get_target_display(), "All products")

    def test_percentage_rule_logs_percent_price_field(self):
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "3_global",
                "compute_price": "percentage",
                "percent_price": 10.0,
            }
        )
        log = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        )
        self.assertEqual(log.field_name, "percent_price")
        self.assertEqual(log.new_value, "10.0")

    def test_formula_rule_logs_price_discount_field(self):
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "3_global",
                "compute_price": "formula",
                "price_discount": 15.0,
            }
        )
        log = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        )
        self.assertEqual(log.field_name, "price_discount")
        self.assertEqual(log.new_value, "15.0")

    def test_bulk_unlink_logs_one_entry_per_item(self):
        items = self.env["product.pricelist.item"].create(
            [
                {
                    "pricelist_id": self.pricelist.id,
                    "applied_on": "3_global",
                    "compute_price": "fixed",
                    "fixed_price": price,
                }
                for price in (1.0, 2.0, 3.0)
            ]
        )
        self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        ).unlink()

        items.unlink()

        logs = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id), ("change_type", "=", "unlink")]
        )
        self.assertEqual(len(logs), 3)

    def test_write_unrelated_field_does_not_log(self):
        item = self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "3_global",
                "compute_price": "fixed",
                "fixed_price": 1.0,
            }
        )
        self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        ).unlink()

        # date_start is not one of the tracked PRICE_FIELDS.
        item.write({"date_start": "2026-01-01"})

        logs = self.env["product.pricelist.change.log"].search(
            [("pricelist_id", "=", self.pricelist.id)]
        )
        self.assertFalse(logs)
