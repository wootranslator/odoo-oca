# Copyright 2017-24 ForgeFlow S.L.
#   (http://www.forgeflow.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from datetime import date, timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestStockRemovalLocationByPriority(TransactionCase):
    def setUp(self):
        super().setUp()
        self.res_users_model = self.env["res.users"]
        self.stock_location_model = self.env["stock.location"]
        self.stock_warehouse_model = self.env["stock.warehouse"]
        self.stock_picking_model = self.env["stock.picking"]
        self.product_model = self.env["product.product"]
        self.quant_model = self.env["stock.quant"]

        self.picking_internal = self.env.ref("stock.picking_type_internal")
        self.picking_out = self.env.ref("stock.picking_type_out")
        self.location_supplier = self.env.ref("stock.stock_location_suppliers")

        self.company = self.env.ref("base.main_company")
        grp_rem_priority = self.env.ref(
            "stock_removal_location_by_priority.group_removal_priority"
        )

        # We assign the group to admin, as the _get_removal_strategy_order
        # method is going to be always executed as sudo.
        user_admin = self.env.ref("base.user_root")
        user_admin.group_ids = [Command.link(grp_rem_priority.id)]

        self.wh1 = self.stock_warehouse_model.create({"name": "WH1", "code": "WH1"})

        # Removal strategies:
        self.fifo = self.env.ref("stock.removal_fifo")
        self.lifo = self.env.ref("stock.removal_lifo")

        # Create locations:
        self.stock = self.stock_location_model.create(
            {"name": "Stock Base", "usage": "internal"}
        )
        self.shelf_A = self.stock_location_model.create(
            {
                "name": "Shelf_A",
                "usage": "internal",
                "location_id": self.stock.id,
                "removal_priority": 10,
            }
        )
        self.shelf_B = self.stock_location_model.create(
            {
                "name": "Shelf_B",
                "usage": "internal",
                "location_id": self.stock.id,
                "removal_priority": 5,
            }
        )
        self.stock_2 = self.stock_location_model.create(
            {"name": "Another Stock Location", "usage": "internal"}
        )

        # Create a product:
        self.product_1 = self.product_model.create(
            {"name": "Test Product 1", "type": "consu", "is_storable": True}
        )

        # Create quants:
        today = date.today()
        q1 = self.quant_model.create(
            {
                "product_id": self.product_1.id,
                "location_id": self.shelf_A.id,
                "quantity": 5.0,
                "in_date": today,
            }
        )
        q2 = self.quant_model.create(
            {
                "product_id": self.product_1.id,
                "location_id": self.shelf_B.id,
                "quantity": 5.0,
                "in_date": today,
            }
        )
        self.quants = q1 + q2

    def _create_picking(self, picking_type, location, location_dest, qty):
        picking = self.stock_picking_model.create(
            {
                "picking_type_id": picking_type.id,
                "location_id": location.id,
                "location_dest_id": location_dest.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product_1.id,
                            "product_uom": self.product_1.uom_id.id,
                            "product_uom_qty": qty,
                            "location_id": location.id,
                            "location_dest_id": location_dest.id,
                            "price_unit": 2,
                        },
                    )
                ],
            }
        )
        return picking

    def test_01_stock_removal_location_by_priority_fifo(self):
        """Tests removal priority with FIFO strategy."""
        self.stock.removal_strategy_id = self.fifo
        # quants must start unreserved
        for q in self.quants:
            self.assertEqual(q.reserved_quantity, 0.0)
            if q.location_id == self.shelf_A:
                self.assertEqual(q.removal_priority, 10)
            if q.location_id == self.shelf_B:
                self.assertEqual(q.removal_priority, 5)
        self.assertEqual(self.quants[0].in_date, self.quants[1].in_date)
        picking_1 = self._create_picking(
            self.picking_internal, self.stock, self.stock_2, 5
        )
        picking_1.flush_model()
        picking_1.action_confirm()
        picking_1.action_assign()

        # quants must be reserved in Shelf B (lower removal_priority value).
        for q in self.quants:
            if q.location_id == self.shelf_A:
                self.assertEqual(q.reserved_quantity, 0.0)
            if q.location_id == self.shelf_B:
                self.assertEqual(q.reserved_quantity, 5.0)

    def test_02_stock_removal_location_by_priority_lifo(self):
        """Tests removal priority with LIFO strategy."""
        self.stock.removal_strategy_id = self.lifo
        # quants must start unreserved
        for q in self.quants:
            self.assertEqual(q.reserved_quantity, 0.0)
            if q.location_id == self.shelf_A:
                self.assertEqual(q.removal_priority, 10)
            if q.location_id == self.shelf_B:
                self.assertEqual(q.removal_priority, 5)
        self.assertEqual(self.quants[0].in_date, self.quants[1].in_date)
        picking_1 = self._create_picking(
            self.picking_internal, self.stock, self.stock_2, 5
        )
        picking_1.flush_model()
        picking_1.action_confirm()
        picking_1.action_assign()

        # quants must be reserved in Shelf B (lower removal_priority value).
        for q in self.quants:
            if q.location_id == self.shelf_A:
                self.assertEqual(q.reserved_quantity, 0.0)
            if q.location_id == self.shelf_B:
                self.assertEqual(q.reserved_quantity, 5.0)

    def test_03_stock_removal_location_by_priority_least_packages(self):
        """Tests removal priority with Least Packages strategy."""
        self.stock.removal_strategy_id = self.env.ref("stock.removal_least_packages")
        order = self.quant_model._get_removal_strategy_order("least_packages")
        self.assertEqual(order, "in_date ASC, removal_priority ASC, id")

    def test_04_stock_removal_location_by_priority_closest(self):
        """Strategies not handled by this module fall back to the standard ones."""
        self.assertFalse(self.quant_model._get_removal_strategy_order("closest"))

    def _reserve(self, qty):
        picking = self._create_picking(
            self.picking_internal, self.stock, self.stock_2, qty
        )
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _reserved(self):
        return {q.location_id: q.reserved_quantity for q in self.quants}

    def test_05_default_removal_priority(self):
        """New locations get the default priority and quants mirror it."""
        location = self.stock_location_model.create(
            {"name": "Default prio", "usage": "internal"}
        )
        self.assertEqual(location.removal_priority, 10)

    def test_06_quant_priority_follows_location(self):
        """Changing the location priority updates the stored quant field."""
        self.shelf_A.removal_priority = 1
        quant_a = self.quants.filtered(lambda q: q.location_id == self.shelf_A)
        self.assertEqual(quant_a.removal_priority, 1)

    def test_07_removal_order_with_group(self):
        """With the group, the priority is part of the FIFO/LIFO order."""
        self.assertEqual(
            self.quant_model._get_removal_strategy_order("fifo"),
            "in_date ASC, removal_priority ASC, id",
        )
        self.assertEqual(
            self.quant_model._get_removal_strategy_order("lifo"),
            "in_date DESC, removal_priority ASC, id desc",
        )

    def test_08_removal_order_without_group(self):
        """Without the group, the standard Odoo order is used."""
        group = self.env.ref(
            "stock_removal_location_by_priority.group_removal_priority"
        )
        self.env.ref("base.user_root").group_ids = [Command.unlink(group.id)]
        self.assertEqual(
            self.quant_model._get_removal_strategy_order("fifo"), "in_date ASC, id"
        )
        self.assertEqual(
            self.quant_model._get_removal_strategy_order("lifo"),
            "in_date DESC, id DESC",
        )

    def test_09_not_implemented_strategy(self):
        """Unknown strategies still raise, through the standard code."""
        with self.assertRaises(UserError):
            self.quant_model._get_removal_strategy_order("unknown")

    def test_10_fifo_incoming_date_beats_priority(self):
        """FIFO: the oldest quant goes first even with a worse priority."""
        self.stock.removal_strategy_id = self.fifo
        self.quants.filtered(lambda q: q.location_id == self.shelf_A).in_date = (
            date.today() - timedelta(days=5)
        )
        self._reserve(5)
        reserved = self._reserved()
        self.assertEqual(reserved[self.shelf_A], 5.0)
        self.assertEqual(reserved[self.shelf_B], 0.0)

    def test_11_lifo_incoming_date_beats_priority(self):
        """LIFO: the newest quant goes first even with a worse priority."""
        self.stock.removal_strategy_id = self.lifo
        self.quants.filtered(lambda q: q.location_id == self.shelf_A).in_date = (
            date.today() + timedelta(days=5)
        )
        self._reserve(5)
        reserved = self._reserved()
        self.assertEqual(reserved[self.shelf_A], 5.0)
        self.assertEqual(reserved[self.shelf_B], 0.0)

    def test_12_reservation_spans_several_locations(self):
        """When the best location is not enough, the next one is used."""
        self.stock.removal_strategy_id = self.fifo
        self._reserve(8)
        reserved = self._reserved()
        self.assertEqual(reserved[self.shelf_B], 5.0)
        self.assertEqual(reserved[self.shelf_A], 3.0)

    def test_13_priority_change_changes_reservation(self):
        """Swapping the priorities swaps the location that gets reserved."""
        self.stock.removal_strategy_id = self.fifo
        self.shelf_A.removal_priority = 1
        self._reserve(5)
        reserved = self._reserved()
        self.assertEqual(reserved[self.shelf_A], 5.0)
        self.assertEqual(reserved[self.shelf_B], 0.0)
