# odoo-oca

[![Pre-commit Status](https://github.com/wootranslator/odoo-oca/actions/workflows/pre-commit.yml/badge.svg?branch=18.0)](https://github.com/wootranslator/odoo-oca/actions/workflows/pre-commit.yml?query=branch%3A18.0)
[![Build Status](https://github.com/wootranslator/odoo-oca/actions/workflows/test.yml/badge.svg?branch=18.0)](https://github.com/wootranslator/odoo-oca/actions/workflows/test.yml?query=branch%3A18.0)

Personal portfolio of my contributions to the
[Odoo Community Association](https://odoo-community.org/) (OCA) by
[wootranslator](https://github.com/wootranslator). Every module here is
prepared to the OCA standard (module layout, README generation, pre-commit,
official CI image) so it can be proposed to the matching OCA repository
without further changes. This repository is only the workbench: modules are
proposed to OCA from a temporary fork of the target repository, not from here.

## Portfolio

| Module | Type | Target OCA repository | Versions | Original authors | Status |
| ------ | ---- | --------------------- | -------- | ---------------- | ------ |
| [product_pricelist_change_notify](product_pricelist_change_notify/) | New contribution | [OCA/sale-workflow](https://github.com/OCA/sale-workflow) | [17.0](https://github.com/wootranslator/odoo-oca/tree/17.0), [18.0](https://github.com/wootranslator/odoo-oca/tree/18.0), [19.0](https://github.com/wootranslator/odoo-oca/tree/19.0) | Javier Sánchez de Pedro | Ready, not proposed yet |
| [stock_removal_location_by_priority](stock_removal_location_by_priority/) | Version migration (18.0 → 19.0) | [OCA/stock-logistics-warehouse](https://github.com/OCA/stock-logistics-warehouse) | [19.0](https://github.com/wootranslator/odoo-oca/tree/19.0) | ForgeFlow (migrated by Javier Sánchez de Pedro) | Ready, waiting for the OCA CLA acknowledgement |

For migrations, the original authors and contributors are kept untouched in the
manifest and in the readme fragments.

Each Odoo series has its own branch, following the same convention used by
the [Odoo Community Association](https://odoo-community.org/) repositories:

| Branch | Odoo version | Status |
| ------ | ------------ | ------ |
| [17.0](https://github.com/wootranslator/odoo-oca/tree/17.0) | 17.0 | Maintained |
| [18.0](https://github.com/wootranslator/odoo-oca/tree/18.0) | 18.0 | Maintained |
| [19.0](https://github.com/wootranslator/odoo-oca/tree/19.0) | 19.0 | Maintained |
| 20.0 | 20.0 | Planned |

## Modules

<!-- prettier-ignore-start -->
[//]: # (addons)

Available addons
----------------
addon | version | maintainers | summary
--- | --- | --- | ---
[product_pricelist_change_notify](product_pricelist_change_notify/) | 18.0.1.1.0 | <a href='https://github.com/wootranslator'><img src='https://github.com/wootranslator.png' width='32' height='32' style='border-radius:50%;' alt='wootranslator'/></a> | Track price changes on pricelist items and send a daily digest

[//]: # (end addons)
<!-- prettier-ignore-end -->

## Licenses

Modules in this repository are licensed under AGPL-3.
