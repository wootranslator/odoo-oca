# Copyright 2026 Javier Sánchez de Pedro <https://www.sanchezdepedro.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Wacom STU Signature",
    "summary": "Capture signatures on a Wacom STU signature pad",
    "version": "18.0.1.0.0",
    "category": "Inventory/Inventory",
    "website": "https://github.com/wootranslator/odoo-oca",
    "author": "Javier Sánchez de Pedro, Odoo Community Association (OCA)",
    "maintainers": ["wootranslator"],
    "license": "AGPL-3",
    "depends": [
        "web",
        "stock",
    ],
    "assets": {
        "web.assets_backend": [
            "wacom_stu_signature/static/src/js/wacom_sigcaptx.esm.js",
            "wacom_stu_signature/static/src/js/wacom_signature_widget.esm.js",
            "wacom_stu_signature/static/src/xml/wacom_signature_dialog.xml",
        ],
    },
    "development_status": "Beta",
}
