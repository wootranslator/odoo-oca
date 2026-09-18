# Copyright 2026 Javier Sánchez de Pedro <https://sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Product Pricelist Change Notify",
    "summary": "Track price changes on pricelist items and send a daily digest",
    "version": "18.0.1.0.0",
    "category": "Sales/Sales",
    "website": "https://github.com/wootranslator/odoo-oca",
    "author": "Javier Sánchez de Pedro, Odoo Community Association (OCA)",
    "maintainers": ["wootranslator"],
    "license": "AGPL-3",
    "depends": [
        "product",
        "mail",
        "sale",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/product_pricelist_views.xml",
        "views/product_pricelist_change_log_views.xml",
        "data/ir_cron_data.xml",
    ],
    "development_status": "Beta",
}
