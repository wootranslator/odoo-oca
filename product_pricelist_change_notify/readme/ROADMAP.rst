* Replace the hardcoded HTML digest body with a ``mail.template`` (QWeb)
  so it can be translated and customized from the UI.
* Make the cron interval and send time configurable instead of the fixed
  daily run at 20:00.
* Add a "no changes today" digest option per pricelist (currently
  pricelists with no changes are simply skipped).
* Port to Odoo 19.0 and 20.0.
